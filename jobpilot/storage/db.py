"""SQLite persistence: profile, preferences, jobs, runs, events, pipeline, feedback,
vector chunks and caches. One file, zero servers, safe across Streamlit reruns."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import numpy as np

from ..schemas import (
    CandidateProfile, CompanyIntel, JobPosting, MatchResult, RunConfig, RunReport, SearchPreferences,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY, canonical_url TEXT, company TEXT, title TEXT, dedupe_key TEXT,
    verification TEXT, data TEXT NOT NULL, first_seen TEXT, last_seen TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs(dedupe_key);
CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY, started_at TEXT, finished_at TEXT, status TEXT, report TEXT, prefs TEXT
);
CREATE TABLE IF NOT EXISTS matches (
    run_id TEXT, job_id TEXT, tier TEXT, score REAL, hard_pass INTEGER, data TEXT NOT NULL,
    PRIMARY KEY (run_id, job_id)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ts TEXT, stage TEXT, level TEXT, message TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS pipeline (
    job_id TEXT PRIMARY KEY, status TEXT, notes TEXT, next_action TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
    job_id TEXT PRIMARY KEY, verdict INTEGER, reasons TEXT, ts TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY, corpus TEXT, owner TEXT, text TEXT, meta TEXT, embedding BLOB, embed_model TEXT
);
CREATE INDEX IF NOT EXISTS idx_chunks_corpus ON chunks(corpus, owner);
CREATE TABLE IF NOT EXISTS embed_cache (hash TEXT PRIMARY KEY, model TEXT, vector BLOB);
CREATE TABLE IF NOT EXISTS company_intel (company_key TEXT PRIMARY KEY, data TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS http_cache (url TEXT PRIMARY KEY, status INTEGER, body TEXT, final_url TEXT, fetched_at TEXT);
"""

PIPELINE_STATUSES = ["saved", "applying", "applied", "interview", "offer", "rejected", "archived"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: str | Path = ".jobpilot/jobpilot.db") -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL") if str(path) != ":memory:" else None
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ #
    def execute(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            cur = self._conn.execute(sql, tuple(params))
            rows = cur.fetchall()
            self._conn.commit()
            return rows

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self._conn.executemany(sql, [tuple(x) for x in seq])
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Key-value (profile, preferences, settings)
    # ------------------------------------------------------------------ #
    def kv_set(self, key: str, value: Any) -> None:
        self.execute(
            "INSERT INTO kv(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value, default=str), _now()),
        )

    def kv_get(self, key: str, default: Any = None) -> Any:
        rows = self.execute("SELECT value FROM kv WHERE key=?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def save_profile(self, profile: CandidateProfile) -> None:
        self.kv_set("profile", profile.model_dump(mode="json"))

    def load_profile(self) -> Optional[CandidateProfile]:
        data = self.kv_get("profile")
        return CandidateProfile.model_validate(data) if data else None

    def save_preferences(self, prefs: SearchPreferences) -> None:
        self.kv_set("preferences", prefs.model_dump(mode="json"))

    def load_preferences(self) -> Optional[SearchPreferences]:
        data = self.kv_get("preferences")
        return SearchPreferences.model_validate(data) if data else None

    def save_run_config(self, cfg: RunConfig) -> None:
        self.kv_set("run_config", cfg.model_dump(mode="json"))

    def load_run_config(self) -> RunConfig:
        data = self.kv_get("run_config")
        return RunConfig.model_validate(data) if data else RunConfig()

    # ------------------------------------------------------------------ #
    # Jobs
    # ------------------------------------------------------------------ #
    @staticmethod
    def dedupe_key(company: str, title: str, location: str = "") -> str:
        import re
        norm = lambda s: re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()
        loc = norm(location).split(" ")[0] if location else ""
        return f"{norm(company)}|{norm(title)}|{loc}"

    def upsert_job(self, job: JobPosting) -> None:
        existing = self.get_job(job.id)
        if existing:
            job.first_seen = existing.first_seen
        self.execute(
            """INSERT INTO jobs(id,canonical_url,company,title,dedupe_key,verification,data,first_seen,last_seen)
               VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET canonical_url=excluded.canonical_url,
               company=excluded.company, title=excluded.title, dedupe_key=excluded.dedupe_key,
               verification=excluded.verification, data=excluded.data, last_seen=excluded.last_seen""",
            (
                job.id, job.canonical_url, job.company, job.title,
                self.dedupe_key(job.company, job.title, job.location_text), job.verification.status.value,
                job.model_dump_json(), job.first_seen.isoformat(), _now(),
            ),
        )

    def get_job(self, job_id: str) -> Optional[JobPosting]:
        rows = self.execute("SELECT data FROM jobs WHERE id=?", (job_id,))
        return JobPosting.model_validate_json(rows[0]["data"]) if rows else None

    def find_job_by_key(self, key: str) -> Optional[JobPosting]:
        rows = self.execute("SELECT data FROM jobs WHERE dedupe_key=? LIMIT 1", (key,))
        return JobPosting.model_validate_json(rows[0]["data"]) if rows else None

    def known_urls(self, limit: int = 500) -> list[str]:
        rows = self.execute("SELECT canonical_url FROM jobs ORDER BY last_seen DESC LIMIT ?", (limit,))
        return [r["canonical_url"] for r in rows]

    # ------------------------------------------------------------------ #
    # Runs, matches, events
    # ------------------------------------------------------------------ #
    def save_run(self, report: RunReport, prefs: Optional[SearchPreferences] = None) -> None:
        self.execute(
            """INSERT INTO runs(id,started_at,finished_at,status,report,prefs) VALUES(?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET finished_at=excluded.finished_at, status=excluded.status,
               report=excluded.report""",
            (
                report.run_id, report.started_at.isoformat(),
                report.finished_at.isoformat() if report.finished_at else None, report.status,
                report.model_dump_json(), prefs.model_dump_json() if prefs else None,
            ),
        )

    def list_runs(self, limit: int = 30) -> list[RunReport]:
        rows = self.execute("SELECT report FROM runs ORDER BY started_at DESC LIMIT ?", (limit,))
        return [RunReport.model_validate_json(r["report"]) for r in rows]

    def latest_run(self) -> Optional[RunReport]:
        runs = self.list_runs(1)
        return runs[0] if runs else None

    def save_matches(self, run_id: str, matches: list[MatchResult]) -> None:
        self.executemany(
            """INSERT INTO matches(run_id,job_id,tier,score,hard_pass,data) VALUES(?,?,?,?,?,?)
               ON CONFLICT(run_id,job_id) DO UPDATE SET tier=excluded.tier, score=excluded.score,
               hard_pass=excluded.hard_pass, data=excluded.data""",
            [
                (run_id, m.job.id, m.tier.value, m.total_score, int(m.hard_pass), m.model_dump_json())
                for m in matches
            ],
        )

    def load_matches(self, run_id: str) -> list[MatchResult]:
        rows = self.execute("SELECT data FROM matches WHERE run_id=? ORDER BY hard_pass DESC, score DESC", (run_id,))
        return [MatchResult.model_validate_json(r["data"]) for r in rows]

    def add_event(self, run_id: str, stage: str, level: str, message: str, data: dict | None = None) -> None:
        self.execute(
            "INSERT INTO events(run_id,ts,stage,level,message,data) VALUES(?,?,?,?,?,?)",
            (run_id, _now(), stage, level, message, json.dumps(data or {}, default=str)),
        )

    def events(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.execute("SELECT ts,stage,level,message,data FROM events WHERE run_id=? ORDER BY id", (run_id,))
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ #
    # Pipeline tracker & feedback
    # ------------------------------------------------------------------ #
    def set_pipeline(self, job_id: str, status: str, notes: str = "", next_action: str = "") -> None:
        self.execute(
            """INSERT INTO pipeline(job_id,status,notes,next_action,updated_at) VALUES(?,?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET status=excluded.status, notes=excluded.notes,
               next_action=excluded.next_action, updated_at=excluded.updated_at""",
            (job_id, status, notes, next_action, _now()),
        )

    def pipeline(self) -> dict[str, dict[str, Any]]:
        rows = self.execute("SELECT job_id,status,notes,next_action,updated_at FROM pipeline")
        return {r["job_id"]: dict(r) for r in rows}

    def remove_pipeline(self, job_id: str) -> None:
        self.execute("DELETE FROM pipeline WHERE job_id=?", (job_id,))

    def set_feedback(self, job_id: str, verdict: int, reasons: list[str]) -> None:
        self.execute(
            """INSERT INTO feedback(job_id,verdict,reasons,ts) VALUES(?,?,?,?) ON CONFLICT(job_id)
               DO UPDATE SET verdict=excluded.verdict, reasons=excluded.reasons, ts=excluded.ts""",
            (job_id, int(verdict), json.dumps(reasons), _now()),
        )

    def feedback(self) -> dict[str, dict[str, Any]]:
        rows = self.execute("SELECT job_id,verdict,reasons,ts FROM feedback")
        return {r["job_id"]: {"verdict": r["verdict"], "reasons": json.loads(r["reasons"] or "[]"), "ts": r["ts"]} for r in rows}

    # ------------------------------------------------------------------ #
    # Vector chunks & caches
    # ------------------------------------------------------------------ #
    def replace_chunks(self, corpus: str, owner: str, rows: list[tuple[str, str, dict, Optional[np.ndarray], str]]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM chunks WHERE corpus=? AND owner=?", (corpus, owner))
            self._conn.executemany(
                "INSERT OR REPLACE INTO chunks(id,corpus,owner,text,meta,embedding,embed_model) VALUES(?,?,?,?,?,?,?)",
                [
                    (cid, corpus, owner, text, json.dumps(meta),
                     vec.astype(np.float32).tobytes() if vec is not None else None, model)
                    for cid, text, meta, vec, model in rows
                ],
            )
            self._conn.commit()

    def load_chunks(self, corpus: str, owner: Optional[str] = None) -> list[dict[str, Any]]:
        if owner is None:
            rows = self.execute("SELECT * FROM chunks WHERE corpus=?", (corpus,))
        else:
            rows = self.execute("SELECT * FROM chunks WHERE corpus=? AND owner=?", (corpus, owner))
        out = []
        for r in rows:
            out.append({
                "id": r["id"], "text": r["text"], "meta": json.loads(r["meta"] or "{}"), "owner": r["owner"],
                "embedding": np.frombuffer(r["embedding"], dtype=np.float32) if r["embedding"] else None,
                "embed_model": r["embed_model"],
            })
        return out

    def cache_get_vectors(self, hashes: list[str], model: str) -> dict[str, np.ndarray]:
        if not hashes:
            return {}
        out: dict[str, np.ndarray] = {}
        for i in range(0, len(hashes), 500):
            part = hashes[i:i + 500]
            marks = ",".join("?" * len(part))
            rows = self.execute(f"SELECT hash,vector FROM embed_cache WHERE model=? AND hash IN ({marks})", [model, *part])
            out.update({r["hash"]: np.frombuffer(r["vector"], dtype=np.float32) for r in rows})
        return out

    def cache_put_vectors(self, items: dict[str, np.ndarray], model: str) -> None:
        self.executemany(
            "INSERT OR REPLACE INTO embed_cache(hash,model,vector) VALUES(?,?,?)",
            [(h, model, v.astype(np.float32).tobytes()) for h, v in items.items()],
        )

    def get_company_intel(self, company_key: str, max_age_days: int = 90) -> Optional[CompanyIntel]:
        rows = self.execute("SELECT data,fetched_at FROM company_intel WHERE company_key=?", (company_key,))
        if not rows:
            return None
        fetched = datetime.fromisoformat(rows[0]["fetched_at"])
        if datetime.now(timezone.utc) - fetched > timedelta(days=max_age_days):
            return None
        return CompanyIntel.model_validate_json(rows[0]["data"])

    def put_company_intel(self, company_key: str, intel: CompanyIntel) -> None:
        self.execute(
            "INSERT OR REPLACE INTO company_intel(company_key,data,fetched_at) VALUES(?,?,?)",
            (company_key, intel.model_dump_json(), _now()),
        )

    def http_cache_get(self, url: str, max_age_hours: int = 12) -> Optional[dict[str, Any]]:
        rows = self.execute("SELECT status,body,final_url,fetched_at FROM http_cache WHERE url=?", (url,))
        if not rows:
            return None
        if datetime.now(timezone.utc) - datetime.fromisoformat(rows[0]["fetched_at"]) > timedelta(hours=max_age_hours):
            return None
        return dict(rows[0])

    def http_cache_put(self, url: str, status: int, body: str, final_url: str) -> None:
        self.execute(
            "INSERT OR REPLACE INTO http_cache(url,status,body,final_url,fetched_at) VALUES(?,?,?,?,?)",
            (url, status, body[:400_000], final_url, _now()),
        )

    def reset(self, what: str = "all") -> None:
        tables = {
            "jobs": ["jobs", "matches", "runs", "events", "http_cache"],
            "profile": ["kv", "chunks"],
            "all": ["kv", "jobs", "runs", "matches", "events", "pipeline", "feedback", "chunks", "embed_cache", "company_intel", "http_cache"],
        }[what]
        with self._lock:
            for t in tables:
                self._conn.execute(f"DELETE FROM {t}")
            self._conn.commit()
