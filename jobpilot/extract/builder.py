"""WORK stage: turn an untrusted lead into a structured JobPosting plus the raw
evidence (HTTP status, ATS existence, JSON-LD, closed markers) the verifier needs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from ..llm.gemini import GeminiClient, GeminiError
from ..llm.prompts import JD_PROMPT, JD_SYSTEM, JD_URL_PROMPT, JDExtraction
from ..schemas import (
    DegreeLevel, EmploymentType, JobCandidate, JobPosting, Requirement, RequirementCategory, RequirementKind,
    SponsorshipSignal, SponsorshipStatus, WorkMode,
)
from ..search.ats import AtsJob, fetch_ats_job, parse_ats_url
from ..search.fetcher import Fetcher, is_aggregator
from ..taxonomy import CLOSED_POSTING_PATTERNS, canonical_skill, term_in_text
from ..textutils import (
    canonical_url, find_jobposting_jsonld, html_to_text, norm_ws, parse_date, parse_salary, quote_in_source,
    stable_id, truncate,
)
from . import heuristics as H

DEMO_PATH = Path(__file__).resolve().parents[1] / "demo" / "sample_jobs.json"


@dataclass
class WorkEvidence:
    method: str = ""
    http_status: Optional[int] = None
    final_url: str = ""
    page_title: str = ""
    ats: str = ""
    ats_exists: Optional[bool] = None
    closed_marker: str = ""
    jsonld: bool = False
    llm_is_posting: Optional[bool] = None
    llm_title: str = ""
    llm_is_closed: Optional[bool] = None
    aggregator: bool = False
    text_len: int = 0
    notes: list[str] = field(default_factory=list)


def _enum(enum_cls, value: str, default):
    try:
        return enum_cls((value or "").strip().lower())
    except ValueError:
        return default


class JobBuilder:
    def __init__(self, fetcher: Fetcher, llm: Optional[GeminiClient] = None, *, use_llm: bool = True,
                 allow_url_context: bool = True) -> None:
        self.fetcher = fetcher
        self.llm = llm
        self.use_llm = use_llm and llm is not None
        self.allow_url_context = allow_url_context
        self._demo: Optional[dict[str, Any]] = None

    # ------------------------------------------------------------------ #
    def build(self, lead: JobCandidate) -> tuple[JobPosting, WorkEvidence]:
        if lead.url.startswith("demo://"):
            return self._build_demo(lead)
        ev = WorkEvidence()
        cu = canonical_url(lead.url)
        job = JobPosting(
            id=stable_id(cu), url=lead.url, canonical_url=cu, title=lead.title, company=lead.company,
            location_text=lead.location, discovered_by=[lead.task_id] if lead.task_id else [], grounded=lead.grounded,
            date_posted=parse_date(lead.posted), work_mode=_enum(WorkMode, lead.work_mode, WorkMode.UNKNOWN),
        )
        text = ""
        ref = parse_ats_url(lead.url)
        if ref:
            ats_job = fetch_ats_job(ref, self.fetcher)
            if ats_job is not None:
                ev.method, ev.ats, ev.ats_exists, ev.http_status = f"ats:{ref.ats}", ref.ats, ats_job.exists, ats_job.status
                if ats_job.exists:
                    self._apply_ats(job, ats_job)
                    text = ats_job.description_text
                else:
                    ev.closed_marker = f"{ref.ats} API reports posting not found/closed (HTTP {ats_job.status})"
                    return job, ev
        if not text:
            ev.aggregator = is_aggregator(lead.url)
            if not ev.aggregator:
                res = self.fetcher.get(lead.url)
                ev.http_status, ev.final_url = res.status, res.final_url
                if res.ok:
                    text, ev.page_title, jsonld = html_to_text(res.text)
                    posting_ld = find_jobposting_jsonld(jsonld)
                    if posting_ld:
                        ev.jsonld = True
                        self._apply_jsonld(job, posting_ld)
                        ld_text = html_to_text(str(posting_ld.get("description", "")))[0]
                        if len(ld_text) > 200:
                            text = ld_text
                    ev.method = ev.method or ("jsonld" if ev.jsonld else "html")
                    # A redirect to a different ATS URL (e.g. company site → greenhouse) is worth re-checking.
                    if not ref and parse_ats_url(res.final_url):
                        ref2 = parse_ats_url(res.final_url)
                        ats_job = fetch_ats_job(ref2, self.fetcher) if ref2 else None
                        if ats_job and ats_job.exists:
                            ev.ats, ev.ats_exists = ref2.ats, True
                            self._apply_ats(job, ats_job)
                            text = ats_job.description_text or text
            if (not text or ev.aggregator or (ev.http_status or 0) in (0, 401, 403, 429)) and self.use_llm and self.allow_url_context:
                text = self._url_context_extract(job, ev) or text

        low = text.lower()
        for pat in CLOSED_POSTING_PATTERNS:
            m = re.search(pat, low)
            if m:
                ev.closed_marker = norm_ws(text[max(0, m.start() - 40): m.end() + 40])
                break
        ev.text_len = len(text)
        job.description_text = text
        if text:
            self._structure(job, text, ev)
        return job, ev

    # ------------------------------------------------------------------ #
    def _apply_ats(self, job: JobPosting, a: AtsJob) -> None:
        job.source = a.ats
        job.title = a.title or job.title
        job.company = job.company or a.company
        job.location_text = a.location or job.location_text
        job.apply_url = a.apply_url or job.apply_url
        if a.url:
            job.url = a.url
        if a.date_posted:
            job.date_posted = a.date_posted
        if a.date_updated:
            job.date_updated = a.date_updated
        if a.work_mode != WorkMode.UNKNOWN:
            job.work_mode = a.work_mode
        if a.employment_type != EmploymentType.UNKNOWN:
            job.employment_type = a.employment_type
        if a.salary_min or a.salary_max:
            job.salary_min, job.salary_max, job.salary_period = a.salary_min, a.salary_max, a.salary_period

    def _apply_jsonld(self, job: JobPosting, ld: dict[str, Any]) -> None:
        job.source = "jsonld"
        job.title = norm_ws(str(ld.get("title", ""))) or job.title
        org = ld.get("hiringOrganization") or {}
        if isinstance(org, dict) and org.get("name"):
            job.company = job.company or norm_ws(str(org["name"]))
        job.date_posted = parse_date(ld.get("datePosted")) or job.date_posted
        job.valid_through = parse_date(ld.get("validThrough"))
        et = ld.get("employmentType")
        et = et[0] if isinstance(et, list) and et else et
        if isinstance(et, str):
            job.employment_type = H.infer_employment_type(et.replace("_", " ")) if job.employment_type == EmploymentType.UNKNOWN else job.employment_type
        if str(ld.get("jobLocationType", "")).upper() == "TELECOMMUTE":
            job.work_mode = WorkMode.REMOTE
        locs = ld.get("jobLocation")
        locs = locs if isinstance(locs, list) else [locs] if locs else []
        names = []
        for loc in locs:
            addr = (loc or {}).get("address", {}) if isinstance(loc, dict) else {}
            if isinstance(addr, dict):
                names.append(", ".join(x for x in [addr.get("addressLocality"), addr.get("addressRegion")] if x))
        if names and not job.location_text:
            job.location_text = "; ".join(n for n in names if n)
        salary = ld.get("baseSalary") or {}
        if isinstance(salary, dict):
            value = salary.get("value") or {}
            if isinstance(value, dict):
                job.salary_min = _num(value.get("minValue")) or job.salary_min
                job.salary_max = _num(value.get("maxValue")) or job.salary_max
                unit = str(value.get("unitText", "")).lower()
                job.salary_period = {"hour": "hour", "month": "month", "week": "week", "day": "day"}.get(unit, "year")

    def _url_context_extract(self, job: JobPosting, ev: WorkEvidence) -> str:
        try:
            dto, resp = self.llm.generate_json(JD_URL_PROMPT.format(url=job.url), JDExtraction, system=JD_SYSTEM, tools=["url_context"])
        except GeminiError as exc:
            ev.notes.append(f"url_context failed: {str(exc)[:120]}")
            return ""
        statuses = [s for _, s in resp.url_context]
        if statuses and not any("SUCCESS" in s for s in statuses):
            ev.notes.append(f"url_context could not retrieve page: {statuses}")
            return ""
        ev.method = "url_context"
        ev.llm_is_posting, ev.llm_is_closed, ev.llm_title = dto.is_job_posting, dto.is_closed, dto.title
        # Without raw text we cannot verify quotes; keep requirement text as the working text.
        synthetic = "\n".join([dto.title, dto.company, dto.location_text, "Requirements:"] + [f"• {r.text}" for r in dto.requirements]
                              + ([dto.sponsorship_quote] if dto.sponsorship_quote else []))
        self._merge_llm(job, dto, synthetic, verify_quotes=False)
        job.extraction_method = "url_context"
        return synthetic

    def _structure(self, job: JobPosting, text: str, ev: WorkEvidence) -> None:
        # Deterministic pass (always) — also the cross-check for the LLM.
        heuristic_sponsor = H.detect_sponsorship(text)
        job.sponsorship = heuristic_sponsor
        if not (job.salary_min or job.salary_max):
            job.salary_min, job.salary_max, job.salary_period = parse_salary(text)
        if job.work_mode == WorkMode.UNKNOWN:
            job.work_mode = H.infer_work_mode(job.location_text, job.title, text[:3000])
        if job.employment_type == EmploymentType.UNKNOWN:
            job.employment_type = H.infer_employment_type(job.title, text[:2000])
        job.min_years_experience = H.summarize_min_years(text)
        job.degree_required = H.infer_degree(text)
        job.requirements = H.extract_requirements(text)
        job.responsibilities = H.extract_responsibilities(text)
        job.extraction_method = job.extraction_method if job.extraction_method == "url_context" else "heuristic"

        job.seniority = H.infer_seniority(job.title, job.min_years_experience)

    def needs_refinement(self, job: JobPosting) -> bool:
        """LLM extraction is spent only where heuristics are weak (saves quota on well-structured ATS posts)."""
        if not self.use_llm or job.extraction_method in ("url_context", "llm+verified") or not job.description_text:
            return False
        structured = [r for r in job.requirements if r.text.lower() != f"experience with {' '.join(r.terms)}".strip()]
        return len(structured) < 4 or job.min_years_experience is None or not job.title

    def refine(self, job: JobPosting, ev: WorkEvidence) -> bool:
        """Second-pass LLM extraction for postings that already passed cheap hard filters."""
        if not self.needs_refinement(job):
            return False
        text = job.description_text
        heuristic_sponsor = job.sponsorship
        try:
            dto, _ = self.llm.generate_json(JD_PROMPT.format(url=job.url, text=truncate(text, 14000)), JDExtraction, system=JD_SYSTEM)
        except GeminiError as exc:
            ev.notes.append(f"LLM extraction failed, heuristic used: {str(exc)[:120]}")
            return False
        ev.llm_is_posting, ev.llm_is_closed, ev.llm_title = dto.is_job_posting, dto.is_closed, dto.title
        self._merge_llm(job, dto, text, verify_quotes=True)
        job.extraction_method = "llm+verified"
        # Explicit negative language found deterministically always wins over the LLM.
        if heuristic_sponsor.status in (SponsorshipStatus.NO_SPONSORSHIP, SponsorshipStatus.CITIZEN_ONLY, SponsorshipStatus.CLEARANCE):
            job.sponsorship = heuristic_sponsor
        job.seniority = H.infer_seniority(job.title, job.min_years_experience)
        return True

    def _merge_llm(self, job: JobPosting, dto: JDExtraction, text: str, *, verify_quotes: bool) -> None:
        job.title = job.title or dto.title
        job.company = job.company or dto.company
        job.location_text = job.location_text or dto.location_text
        if job.work_mode == WorkMode.UNKNOWN:
            job.work_mode = _enum(WorkMode, dto.work_mode, WorkMode.UNKNOWN)
        if job.employment_type == EmploymentType.UNKNOWN:
            job.employment_type = _enum(EmploymentType, dto.employment_type, EmploymentType.UNKNOWN)
        job.date_posted = job.date_posted or parse_date(dto.date_posted)
        if not (job.salary_min or job.salary_max) and (dto.salary_min or dto.salary_max):
            job.salary_min, job.salary_max, job.salary_period = dto.salary_min, dto.salary_max, dto.salary_period or "year"
        if dto.min_years_experience is not None:
            job.min_years_experience = dto.min_years_experience
        if dto.degree_required:
            job.degree_required = _enum(DegreeLevel, dto.degree_required, job.degree_required)
        job.industry = dto.industry or job.industry
        if dto.responsibilities:
            job.responsibilities = dto.responsibilities[:8]

        reqs: list[Requirement] = []
        for r in dto.requirements[:18]:
            if verify_quotes and not quote_in_source(r.text, text, threshold=0.8):
                # Paraphrased requirement: keep only if its concrete terms are really in the posting.
                if not r.terms or not all(term_in_text(t, text) for t in r.terms):
                    continue
            reqs.append(Requirement(
                id=f"R{len(reqs) + 1}", text=r.text, kind=_enum(RequirementKind, r.kind, RequirementKind.REQUIRED),
                category=_enum(RequirementCategory, r.category, RequirementCategory.SKILL),
                terms=[canonical_skill(t) for t in r.terms][:6], min_years=r.min_years,
            ))
        if reqs:
            job.requirements = reqs
        status = _enum(SponsorshipStatus, dto.sponsorship_status, SponsorshipStatus.UNKNOWN)
        if status != SponsorshipStatus.UNKNOWN and dto.sponsorship_quote:
            if not verify_quotes or quote_in_source(dto.sponsorship_quote, text):
                job.sponsorship = SponsorshipSignal(status=status, quote=dto.sponsorship_quote)

    # ------------------------------------------------------------------ #
    def _build_demo(self, lead: JobCandidate) -> tuple[JobPosting, WorkEvidence]:
        if self._demo is None:
            self._demo = {j["id"]: j for j in json.loads(DEMO_PATH.read_text(encoding="utf-8"))}
        raw = self._demo[lead.url.removeprefix("demo://")]
        today = datetime.now(timezone.utc).date()
        job = JobPosting(
            id=stable_id(lead.url), url=lead.url, canonical_url=lead.url, source="demo", title=raw["title"],
            company=raw["company"], location_text=raw["location"],
            work_mode=H.infer_work_mode(raw["work_mode"]),
            employment_type=H.infer_employment_type(raw.get("employment_type", "")),
            date_posted=today - timedelta(days=int(raw.get("posted_days_ago", 5))),
            discovered_by=[lead.task_id], grounded=True,
        )
        ev = WorkEvidence(method="demo", http_status=200, text_len=len(raw["description"]))
        self._structure_demo(job, raw["description"])
        return job, ev

    def _structure_demo(self, job: JobPosting, text: str) -> None:
        saved = self.use_llm
        self.use_llm = False
        try:
            job.description_text = text
            self._structure(job, text, WorkEvidence())
        finally:
            self.use_llm = saved


def _num(v: Any) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
