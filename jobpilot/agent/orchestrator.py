"""The agent loop: READ → PLAN → [SEARCH → WORK → VERIFY → EVALUATE → REFLECT]* → REPORT."""

from __future__ import annotations

import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable, Optional

import numpy as np

from ..evaluate.evidence import EvidenceMatcher
from ..evaluate.hard_filters import evaluate_hard_filters
from ..evaluate.scoring import Scorer
from ..extract.builder import JobBuilder
from ..llm.gemini import GeminiAuthError, GeminiClient, GeminiModelNotFound, UsageTracker
from ..rag.embeddings import GeminiEmbedder, HashingEmbedder, ResilientEmbedder
from ..rag.retriever import HybridIndex
from ..schemas import (
    AgentEvent, CandidateProfile, Issue, IterationReport, JobCandidate, JobPosting, MatchResult, RunConfig, RunReport,
    SearchPreferences, SponsorshipStatus, Tier, VerificationStatus,
)
from ..search.fetcher import Fetcher
from ..search.gemini_search import DemoSearcher, GeminiSearcher, SearchOutcome
from ..search.planner import SearchPlan
from ..storage.db import Database
from ..textutils import canonical_url
from ..verify.verifier import Verifier
from .critic import Critic, user_suggestions
from .intel import CompanyIntelService

EventSink = Callable[[AgentEvent], None]


class RunAborted(RuntimeError):
    pass


class JobPilotAgent:
    def __init__(
        self,
        db: Database,
        *,
        api_key: str = "",
        model: str = "",
        embed_model: str = "gemini-embedding-001",
        config: Optional[RunConfig] = None,
        on_event: Optional[EventSink] = None,
        should_stop: Optional[Callable[[], bool]] = None,
        llm: Optional[GeminiClient] = None,
        fetcher: Optional[Fetcher] = None,
        searcher=None,
    ) -> None:
        self.db = db
        self.config = config or RunConfig()
        self.tracker = UsageTracker()
        self.on_event = on_event
        self.should_stop = should_stop or (lambda: False)
        demo = self.config.demo_mode or (not api_key and llm is None)
        self.config.demo_mode = demo
        if llm is not None:
            llm.usage = self.tracker
            if self.config.llm_rpm:
                llm.min_interval_s = 60.0 / self.config.llm_rpm
        self.llm = None if demo else (llm or GeminiClient(api_key, model or "gemini-3.8-flash", embed_model=embed_model,
                                                          usage=self.tracker, max_concurrent=self.config.llm_concurrency,
                                                          min_interval_s=(60.0 / self.config.llm_rpm) if self.config.llm_rpm else 0.0))
        self.fetcher = fetcher or Fetcher(db, on_fetch=lambda: self.tracker.add(http_fetches=1))
        self.searcher = searcher or (DemoSearcher() if demo else GeminiSearcher(self.llm, self.fetcher))
        self.embedder = ResilientEmbedder(GeminiEmbedder(self.llm, db) if self.llm else None, HashingEmbedder())
        self.run_id = ""
        self.report: Optional[RunReport] = None

    # ------------------------------------------------------------------ #
    def emit(self, stage: str, message: str, level: str = "info", **data) -> None:
        event = AgentEvent(stage=stage, message=message, level=level, data=data)
        if self.run_id:
            try:
                self.db.add_event(self.run_id, stage, level, message, data)
            except Exception:  # never let logging kill the run
                pass
        if self.on_event:
            self.on_event(event)

    def issue(self, stage: str, message: str, resolution: str = "", severity: str = "warning") -> None:
        if self.report is not None:
            self.report.issues.append(Issue(stage=stage, severity=severity, message=message[:400], resolution=resolution))
        self.emit(stage, f"{message} → {resolution}" if resolution else message, level="warning" if severity != "error" else "error")

    def _check_stop(self) -> None:
        if self.should_stop():
            raise RunAborted("stopped by user")

    # ------------------------------------------------------------------ #
    def run(self, profile: CandidateProfile, prefs: SearchPreferences) -> tuple[RunReport, list[MatchResult]]:
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        report = RunReport(run_id=self.run_id, mode="demo" if self.config.demo_mode else "live")
        self.report = report
        self.db.save_run(report, prefs)
        matches: dict[str, MatchResult] = {}
        try:
            self._run_loop(profile, prefs, report, matches)
            report.status = "completed"
        except RunAborted as exc:
            report.status, report.stop_reason = "stopped", str(exc)
            self.emit("report", "Run stopped by user", level="warning")
        except (GeminiAuthError, GeminiModelNotFound) as exc:
            report.status, report.stop_reason = "failed", type(exc).__name__
            self.issue("search", str(exc), "Check the API key / model in Settings, then re-run", severity="error")
        except Exception as exc:  # last-resort guard: keep partial results and explain
            report.status, report.stop_reason = "failed", f"{type(exc).__name__}: {exc}"
            self.issue("agent", f"Unexpected error: {type(exc).__name__}: {exc}", "Partial results kept; see events log", severity="error")
        finally:
            self._finalize(report, prefs, list(matches.values()))
        return report, sorted(matches.values(), key=_rank_key)

    # ------------------------------------------------------------------ #
    def _run_loop(self, profile: CandidateProfile, prefs: SearchPreferences, report: RunReport, matches: dict[str, MatchResult]) -> None:
        cfg = self.config
        # READ ------------------------------------------------------------
        self.emit("read", "Indexing resume evidence for RAG")
        index = HybridIndex.for_profile(profile, self.embedder, self.db)
        if self.embedder.error:
            self.issue("read", f"Gemini embeddings unavailable ({self.embedder.error[:120]})", "Using local hashing embeddings")
        self.emit("read", f"Indexed {len(index.chunks)} evidence chunks", chunks=len(index.chunks), embedder=self.embedder.name)
        matcher = EvidenceMatcher(index, profile, self.llm, use_llm=cfg.use_llm_evidence)
        builder = JobBuilder(self.fetcher, self.llm, use_llm=cfg.use_llm_extraction)
        verifier = Verifier()
        scorer = Scorer(prefs, profile)
        intel_service = CompanyIntelService(self.db, self.llm if cfg.company_intel else None)
        critic = Critic(cfg, prefs, self.llm)
        profile_vec = self.embedder.embed_queries([
            " | ".join(prefs.target_titles) + ". " + profile.headline + ". " + ", ".join(profile.skills[:20])
        ])[0]
        feedback_vecs = self._feedback_vectors()

        # PLAN ------------------------------------------------------------
        plan = SearchPlan(profile, prefs)
        self.emit("plan", f"Initial plan with {len(plan.tasks)} search tasks", tasks=[t.describe() for t in plan.tasks])
        seen_urls: set[str] = set()
        seen_keys: set[str] = set()
        intel_calls = 0

        for number in range(1, cfg.max_iterations + 1):
            self._check_stop()
            t0 = time.monotonic()
            it = IterationReport(number=number)
            remaining_calls = cfg.max_search_calls - self.tracker.usage.search_calls
            batch = plan.next_batch(min(4, max(remaining_calls, 0)) if not cfg.demo_mode else 4)
            if not batch:
                report.stop_reason = report.stop_reason or "saturated"
                break
            it.tasks = [t.describe() for t in batch]

            # SEARCH ------------------------------------------------------
            self.emit("search", f"Iteration {number}: running {len(batch)} search tasks", iteration=number, tasks=it.tasks)
            exclude = list(seen_urls)[:40]
            with ThreadPoolExecutor(max_workers=max(1, cfg.llm_concurrency)) as pool:
                outcomes: list[SearchOutcome] = list(pool.map(lambda t: self.searcher.run(t, prefs, exclude), batch))
            errors = 0
            leads: list[JobCandidate] = []
            for out in outcomes:
                out.task.done = True
                if out.error:
                    errors += 1
                    self.issue("search", f"Task {out.task.id} failed: {out.error[:160]}", "Skipped task; critic may re-plan")
                self.emit("search", f"{out.task.describe()} → {len(out.leads)} leads", queries=out.queries[:6])
                leads.extend(out.leads)
            it.leads = len(leads)

            fresh: list[JobCandidate] = []
            for lead in leads:
                cu = canonical_url(lead.url)
                key = self.db.dedupe_key(lead.company, lead.title, lead.location) if lead.company and lead.title else ""
                if cu in seen_urls or (key and key in seen_keys):
                    continue
                seen_urls.add(cu)
                if key:
                    seen_keys.add(key)
                fresh.append(lead)
            fresh = fresh[: cfg.max_jobs_per_iteration]
            self._check_stop()

            # WORK + VERIFY ---------------------------------------------------
            self.emit("work", f"Fetching and structuring {len(fresh)} new postings")
            built: list[tuple[JobPosting, JobCandidate]] = []
            built_ev: list[tuple[JobPosting, JobCandidate, object]] = []

            def _work(lead: JobCandidate):
                try:
                    job, ev = builder.build(lead)
                    verifier.verify(job, lead, ev)
                    return job, lead, ev, None
                except Exception as exc:  # isolate per-job failures
                    return None, lead, None, exc

            with ThreadPoolExecutor(max_workers=max(1, cfg.fetch_concurrency)) as pool:
                for job, lead, ev, exc in pool.map(_work, fresh):
                    if exc is not None or job is None:
                        self.issue("work", f"Could not process {lead.url[:90]}: {type(exc).__name__}: {str(exc)[:100]}", "Skipped this lead")
                        continue
                    for note in ev.notes:
                        self.issue("work", f"{job.company or lead.company} · {job.title or lead.title}: {note}", "Fell back to deterministic extraction", severity="info")
                    ev.notes.clear()
                    key = self.db.dedupe_key(job.company, job.title, job.location_text)
                    if job.title and job.company and key in seen_keys and key != self.db.dedupe_key(lead.company, lead.title, lead.location):
                        continue
                    seen_keys.add(key)
                    built.append((job, lead))
                    built_ev.append((job, lead, ev))
            it.new_unique = len(built)
            status_counts = Counter(j.verification.status for j, _ in built)
            it.verified = status_counts[VerificationStatus.VERIFIED] + status_counts[VerificationStatus.DEMO]
            it.unverified = status_counts[VerificationStatus.UNVERIFIED]
            it.dead = status_counts[VerificationStatus.DEAD]
            it.mismatch = status_counts[VerificationStatus.MISMATCH]
            self.emit("verify", f"Verified {it.verified}, unverified {it.unverified}, dead {it.dead}, mismatched {it.mismatch}",
                      verified=it.verified, unverified=it.unverified, dead=it.dead, mismatch=it.mismatch)
            self._check_stop()

            # EVALUATE ------------------------------------------------------
            self.emit("evaluate", f"Applying hard filters and RAG evidence to {len(built)} postings")
            job_texts = [f"{j.title}. {j.company}. {j.description_text[:1500]}" for j, _ in built]
            job_vecs = self.embedder.embed_documents(job_texts) if built else np.zeros((0, 1))
            # Cheap deterministic gate first; spend LLM extraction only on survivors, then re-check.
            survivors = [(job, lead, ev) for job, lead, ev in built_ev
                         if all(h.passed or not h.enforced for h in evaluate_hard_filters(job, prefs, profile))]
            refine_targets = [x for x in survivors if builder.needs_refinement(x[0])]
            if refine_targets:
                self.emit("work", f"LLM-refining {len(refine_targets)} postings that passed the cheap filters")

                def _refine(item):
                    job, lead, ev = item
                    if builder.refine(job, ev):
                        verifier.verify(job, lead, ev)
                    return ev

                with ThreadPoolExecutor(max_workers=max(1, cfg.llm_concurrency)) as pool:
                    for ev in pool.map(_refine, refine_targets):
                        for note in ev.notes:
                            self.issue("work", note, "Kept deterministic extraction", severity="info")
                        ev.notes.clear()
            prelim: list[tuple[JobPosting, list, int]] = []
            for i, (job, _) in enumerate(built):
                hard = evaluate_hard_filters(job, prefs, profile)
                prelim.append((job, hard, i))
                failed = [h.rule for h in hard if h.enforced and not h.passed]
                for rule in failed[:1]:
                    it.rejection_reasons[rule] = it.rejection_reasons.get(rule, 0) + 1
            status_counts = Counter(j.verification.status for j, _ in built)
            it.verified = status_counts[VerificationStatus.VERIFIED] + status_counts[VerificationStatus.DEMO]
            it.unverified = status_counts[VerificationStatus.UNVERIFIED]
            it.dead = status_counts[VerificationStatus.DEAD]
            it.mismatch = status_counts[VerificationStatus.MISMATCH]

            passed = [(j, h, i) for j, h, i in prelim if all(x.passed or not x.enforced for x in h)]
            it.hard_passed = len(passed)
            # Company sponsorship intel for surviving postings with silent JDs.
            if prefs.needs_sponsorship:
                silent = [j for j, _, _ in passed if j.sponsorship.status == SponsorshipStatus.UNKNOWN and j.company]
                if silent and cfg.company_intel and self.llm is not None:
                    self.emit("evaluate", f"Checking employer H-1B history for up to {min(len(silent), max(cfg.max_company_intel_calls - intel_calls, 0))} companies (cached 90 days)")
                for job, _, _ in passed:
                    if job.sponsorship.status != SponsorshipStatus.UNKNOWN or not job.company:
                        continue
                    if intel_service.cached(job.company) is None and (intel_calls >= cfg.max_company_intel_calls or self.llm is None or not cfg.company_intel):
                        continue
                    if intel_service.cached(job.company) is None:
                        intel_calls += 1
                    intel_service.lookup(job.company, job.title)

            def _evaluate(item):
                job, hard, i = item
                is_pass = all(x.passed or not x.enforced for x in hard)
                evidence = matcher.match(job, dense=True, allow_llm=True) if is_pass else matcher.match(job, dense=False, allow_llm=False)
                dense = float(job_vecs[i] @ profile_vec) if len(job_vecs) else None
                affinity = self._affinity(job_vecs[i], feedback_vecs) if len(job_vecs) and feedback_vecs else None
                intel = intel_service.cached(job.company) if prefs.needs_sponsorship else None
                return scorer.score(job, hard, evidence, dense_alignment=dense, feedback_affinity=affinity, intel=intel, run_id=self.run_id)

            with ThreadPoolExecutor(max_workers=max(1, cfg.llm_concurrency)) as pool:
                results = list(pool.map(_evaluate, prelim))
            if matcher.last_error:
                self.issue("evaluate", f"LLM evidence judging failed: {matcher.last_error}", "Used lexical evidence matching")
                matcher.last_error = ""
            if matcher.downgraded:
                self.emit("verify", f"Discarded {matcher.downgraded} LLM evidence claims whose quotes were not in the resume", level="warning")
                matcher.downgraded = 0
            for res in results:
                matches[res.job.id] = res
                self.db.upsert_job(res.job)
            self.db.save_matches(self.run_id, results)
            it.shortlisted = sum(1 for r in results if r.tier in (Tier.A, Tier.B))
            shortlist_total = sum(1 for r in matches.values() if r.tier in (Tier.A, Tier.B))
            self.emit("evaluate", f"{it.hard_passed} passed hard filters · {it.shortlisted} shortlisted (A/B) this iteration",
                      passed=it.hard_passed, shortlisted=it.shortlisted, total_shortlist=shortlist_total)

            # REFLECT -------------------------------------------------------
            decision = critic.assess(it, report.iterations + [it], shortlist_total, self.tracker.usage, plan, errors, len(batch))
            it.diagnosis, it.actions = decision.diagnosis, decision.actions
            it.seconds = round(time.monotonic() - t0, 1)
            report.iterations.append(it)
            report.usage = self.tracker.usage.model_copy()
            self.db.save_run(report, prefs)
            self.emit("reflect", f"Iteration {number} review: " + ("stop — " + decision.reason if decision.stop else f"continue with {len(decision.actions)} strategy changes"),
                      diagnosis=[d.model_dump() for d in decision.diagnosis], actions=[a.model_dump() for a in decision.actions])
            if decision.stop:
                report.stop_reason = decision.reason
                break

    # ------------------------------------------------------------------ #
    def _feedback_vectors(self) -> dict[int, np.ndarray]:
        fb = self.db.feedback()
        groups: dict[int, list[str]] = {1: [], -1: []}
        for job_id, item in fb.items():
            job = self.db.get_job(job_id)
            if job and item["verdict"] in groups:
                groups[item["verdict"]].append(f"{job.title}. {job.company}. {job.description_text[:1500]}")
        out = {}
        for verdict, texts in groups.items():
            if texts:
                out[verdict] = self.embedder.embed_documents(texts)
        return out

    @staticmethod
    def _affinity(vec: np.ndarray, groups: dict[int, np.ndarray]) -> float:
        pos = float(np.max(groups[1] @ vec)) if 1 in groups else 0.0
        neg = float(np.max(groups[-1] @ vec)) if -1 in groups else 0.0
        return float(np.clip((pos - neg) * 2.0, -1.0, 1.0))

    def _finalize(self, report: RunReport, prefs: SearchPreferences, results: list[MatchResult]) -> None:
        if report.status == "running":  # interrupted by a BaseException (e.g. app shutdown / rerun)
            report.status, report.stop_reason = "stopped", report.stop_reason or "interrupted"
        report.finished_at = datetime.now(timezone.utc)
        report.usage = self.tracker.usage.model_copy()
        report.funnel = {
            "leads": sum(i.leads for i in report.iterations),
            "unique": sum(i.new_unique for i in report.iterations),
            "verified": sum(i.verified for i in report.iterations),
            "hard_passed": sum(i.hard_passed for i in report.iterations),
            "shortlisted": sum(1 for r in results if r.tier in (Tier.A, Tier.B)),
        }
        tiers = Counter(r.tier.value for r in results)
        report.tier_counts = {t.value: tiers.get(t.value, 0) for t in Tier}
        report.top_job_ids = [r.job.id for r in sorted(results, key=_rank_key)[:20]]
        report.suggestions = user_suggestions(report.iterations, prefs, report.funnel["shortlisted"], self.config.target_shortlist)
        if not report.stop_reason and report.status == "completed":
            report.stop_reason = "max_iterations"
        self.db.save_run(report, prefs)
        self.emit("report", f"Run {report.status}: {report.funnel.get('shortlisted', 0)} shortlisted from {report.funnel.get('unique', 0)} unique postings",
                  funnel=report.funnel, tiers=report.tier_counts, cost=report.usage.estimated_cost_usd())


TIER_ORDER = {Tier.A: 0, Tier.B: 1, Tier.C: 2, Tier.D: 3, Tier.REJECTED: 4}


def _rank_key(r: MatchResult):
    return (TIER_ORDER[r.tier], -r.total_score)
