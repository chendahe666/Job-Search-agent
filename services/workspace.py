"""Single-user local workspace; immutable resume versions and explicit saves.

No model calls or network requests occur here. This deterministic boundary keeps
the human-approved document separate from transient agent suggestions.
"""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
ROLES = ("Software Engineer", "AI / ML Engineer", "Data Scientist")


class Workspace:
    """Persist personal data outside tracked source files, for local use only."""

    def __init__(self, path=None):
        self.path = Path(path or os.getenv("ROLESIGNAL_DB", str(ROOT / "local_data" / "workspace.db")))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS records (kind TEXT, id TEXT, payload TEXT NOT NULL, updated TEXT NOT NULL, PRIMARY KEY(kind,id))")

    @contextmanager
    def connect(self):
        """Use short-lived connections; never share a SQLite connection across sessions."""
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, kind, identifier, default=None):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM records WHERE kind=? AND id=?", (kind, identifier)).fetchone()
        return json.loads(row[0]) if row else default

    def all(self, kind):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM records WHERE kind=? ORDER BY updated DESC, rowid DESC", (kind,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def put(self, kind, payload, identifier=None):
        """Save explicit user input using parameterized SQL, returning the saved record."""
        record = dict(payload)
        record["id"] = identifier or record.get("id") or uuid4().hex
        record["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self.connect() as db:
            db.execute("INSERT INTO records VALUES (?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET payload=excluded.payload, updated=excluded.updated", (kind, record["id"], json.dumps(record, ensure_ascii=False), record["updated"]))
        return record

    def save_version(self, text, role, profile, job=None):
        """Append a new immutable version with exact source/profile/JD snapshots."""
        if not text.strip():
            raise ValueError("简历不能为空，请先添加内容。")
        return self.put("resume", {"text": text.strip(), "role": role, "profile_snapshot": profile, "job_snapshot": job, "title": f"{role} · {job['company'] if job else '基础版'}"})

    def save_job(self, title, company, description, url="", skills="", location="United States"):
        """Paste-first import: no scraping or unverifiable inferred requirements."""
        if not title.strip() or not description.strip():
            raise ValueError("请填写岗位名称和职位描述。")
        if url and not url.startswith(("https://", "http://")):
            raise ValueError("来源链接应以 https:// 或 http:// 开头，也可以暂时留空。")
        digest = hashlib.sha256((url.strip() or f"{title.strip().lower()}|{company.strip().lower()}|{description.strip()}").encode()).hexdigest()[:20]
        existing = self.get("job", digest)
        if existing:
            return existing, False
        record = self.put("job", {"title": title.strip(), "company": company.strip() or "未填写公司", "description": description.strip(), "url": url.strip(), "location": location.strip(), "required_skills": split_skills(skills), "responsibilities": [], "source": "用户导入", "work_mode": "待确认", "salary_range": "未提供", "experience_level": "待确认"}, digest)
        return record, True


def split_skills(text):
    """Normalize explicit user declarations; do not infer skills from resume prose."""
    import re
    return list(dict.fromkeys(x.strip() for x in re.split(r"[,，;；\n]", text) if x.strip()))


def filter_jobs(jobs, query="", mode="全部"):
    """Search the complete corpus before rendering; no hidden top-K restriction."""
    needle = query.strip().casefold()
    return [j for j in jobs if (not needle or needle in " ".join(str(j.get(k, "")) for k in ("title", "company", "location", "description", "required_skills")).casefold()) and (mode == "全部" or j.get("work_mode") == mode)]


def source_draft(profile):
    """Return supplied resume text unchanged; never invent achievements or metrics."""
    return profile.get("source", "").strip()


def improvement_questions(text):
    """Offer questions, not fabricated answers, for incomplete experience material."""
    import re
    questions = []
    if not re.search(r"\d", text):
        questions.append("有没有可核实的结果或规模？没有数字也没关系，可以描述测试方式与实际产出。")
    if len(text.split()) < 100:
        questions.append("挑一个最熟悉的项目，补充：解决的问题、你亲自做的部分、使用的方法、实际结果。")
    questions.append("检查每段经历：读者能否分清团队成果和你个人完成的工作？")
    return questions
