"""VERIFY stage: is the posting real, open, and the one the search stage claimed?

This is where hallucinated or stale search results are caught. Each check is
recorded so the UI can show *why* a job is trusted or not.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from ..extract.builder import WorkEvidence
from ..schemas import JobCandidate, JobPosting, Verification, VerificationCheck, VerificationStatus
from ..taxonomy import NON_US_REMOTE_MARKERS, US_STATES
from ..textutils import domain_of, norm_key

TITLE_STOP = {"and", "of", "the", "for", "to", "a", "an", "in", "i", "ii", "iii", "remote", "hybrid", "us", "usa", "new", "grad", "sr", "jr"}
COMPANY_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|co|company|technologies|technology|labs|group|holdings|plc|ai)\b")


def title_similarity(a: str, b: str) -> float:
    ta = {t for t in norm_key(a).split() if t not in TITLE_STOP}
    tb = {t for t in norm_key(b).split() if t not in TITLE_STOP}
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def company_core(name: str) -> str:
    return COMPANY_SUFFIX.sub(" ", norm_key(name)).strip()


def company_matches(claimed: str, job: JobPosting, ev: WorkEvidence) -> Optional[bool]:
    core = company_core(claimed)
    if not core:
        return None
    haystacks = [company_core(job.company), norm_key(job.description_text[:6000]), norm_key(ev.page_title),
                 domain_of(job.url).replace(".", " "), domain_of(ev.final_url).replace(".", " "), norm_key(job.url)]
    compact = core.replace(" ", "")
    for h in haystacks:
        if not h:
            continue
        if core in h or compact in h.replace(" ", ""):
            return True
    if not job.description_text and not ev.page_title:
        return None
    return False


def is_us_location(text: str) -> Optional[bool]:
    low = f" {(text or '').lower()} "
    if not low.strip():
        return None
    if re.search(r"\b(united states|usa|u\.s\.|us-remote|remote us|remote - us|remote \(us)", low):
        return True
    for abbr, name in US_STATES.items():
        if re.search(rf"[, ]\s*{abbr}\b", text or "") or name.lower() in low:
            return True
    if any(m in low for m in NON_US_REMOTE_MARKERS):
        return False
    return None


class Verifier:
    def verify(self, job: JobPosting, lead: JobCandidate, ev: WorkEvidence) -> Verification:
        checks: list[VerificationCheck] = []
        if ev.method == "demo":
            job.verification = Verification(status=VerificationStatus.DEMO, http_status=200, checked_at=datetime.now(timezone.utc),
                                             checks=[VerificationCheck(name="demo", passed=None, detail="Offline sample posting")])
            return job.verification

        reachable: Optional[bool]
        if ev.ats_exists is not None:
            reachable = ev.ats_exists
            detail = f"{ev.ats} public API: {'posting exists' if ev.ats_exists else 'not found'}"
        elif ev.method == "url_context":
            reachable, detail = True, "Read via Gemini URL context (page blocked to direct fetch)"
        elif ev.http_status:
            reachable = 200 <= ev.http_status < 300 if ev.http_status not in (401, 403, 429) else None
            detail = f"HTTP {ev.http_status}"
        elif ev.aggregator:
            reachable, detail = None, "Aggregator page (not fetched; prefer the employer posting)"
        else:
            reachable, detail = None, "Network error / timeout"
        checks.append(VerificationCheck(name="reachable", passed=reachable, detail=detail))

        today = datetime.now(timezone.utc).date()
        open_ok: Optional[bool] = True
        open_detail = "No closed/expired markers"
        if ev.closed_marker:
            open_ok, open_detail = False, f"Closed marker: “{ev.closed_marker[:120]}”"
        elif ev.llm_is_closed:
            open_ok, open_detail = False, "Page states the posting is closed"
        elif job.valid_through and job.valid_through < today:
            open_ok, open_detail = False, f"validThrough {job.valid_through} has passed"
        elif ev.http_status in (404, 410):
            open_ok, open_detail = False, f"HTTP {ev.http_status}"
        elif reachable is None:
            open_ok, open_detail = None, "Could not confirm the posting is open"
        checks.append(VerificationCheck(name="open", passed=open_ok, detail=open_detail))

        is_posting: Optional[bool]
        if ev.llm_is_posting is False:
            is_posting = False
        elif ev.text_len >= 400 or ev.ats_exists:
            is_posting = True
        elif ev.text_len:
            is_posting = None
        else:
            is_posting = None if reachable is None else False
        checks.append(VerificationCheck(name="is_job_posting", passed=is_posting,
                                        detail=f"{ev.text_len} chars of description via {ev.method or 'n/a'}"))

        title_ok: Optional[bool] = None
        authoritative = [x for x in [job.title if (ev.ats_exists or ev.jsonld) else "", ev.llm_title] if x]
        if lead.title and (authoritative or ev.page_title or job.description_text):
            claimed_tokens = [w for w in norm_key(lead.title).split() if w not in TITLE_STOP]
            body = f" {norm_key(job.description_text[:5000])} "
            text_share = (sum(1 for w in claimed_tokens if f" {w} " in body) / len(claimed_tokens)) if claimed_tokens else 0.0
            if authoritative:
                observed = max(authoritative, key=lambda x: title_similarity(lead.title, x))
                sim = title_similarity(lead.title, observed)
                title_ok = sim >= 0.5
            elif ev.page_title:
                observed, sim = ev.page_title, title_similarity(lead.title, ev.page_title)
                title_ok = sim >= 0.5 or text_share >= 0.67
            else:
                observed, sim = "(page text)", text_share
                title_ok = True if text_share >= 0.67 else None
            checks.append(VerificationCheck(name="title_consistent", passed=title_ok,
                                            detail=f"claimed “{lead.title}” vs “{observed[:80]}” (overlap {sim:.2f}, in text {text_share:.2f})"))
        company_ok: Optional[bool] = None
        if lead.company and (job.description_text or ev.page_title):
            company_ok = company_matches(lead.company, job, ev)
            checks.append(VerificationCheck(name="company_consistent", passed=company_ok,
                                            detail=f"claimed “{lead.company}”, page company “{job.company or '?'}”"))

        us = is_us_location(job.location_text)
        checks.append(VerificationCheck(name="us_location", passed=us, detail=job.location_text or "location not stated"))
        checks.append(VerificationCheck(name="grounded_in_search", passed=lead.grounded or None,
                                        detail="URL appeared in Google Search grounding sources" if lead.grounded else "URL came from model text only"))

        if open_ok is False or (reachable is False and ev.http_status in (404, 410)) or (ev.ats_exists is False):
            status = VerificationStatus.DEAD
        elif title_ok is False or company_ok is False or is_posting is False:
            status = VerificationStatus.MISMATCH
        elif reachable and open_ok and is_posting:
            status = VerificationStatus.VERIFIED
        else:
            status = VerificationStatus.UNVERIFIED
        job.verification = Verification(status=status, http_status=ev.http_status, final_url=ev.final_url,
                                        checks=checks, checked_at=datetime.now(timezone.utc))
        return job.verification
