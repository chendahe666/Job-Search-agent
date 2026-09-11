"""EVALUATE part 1 — hard gates. Deterministic, explainable, evidence-quoted.

Policy: a rule rejects only on *known* conflicting facts. Unknown facts pass with
a warning (so a missing salary or date never silently hides a good job).
Rules the user disabled become warnings that still feed the soft score.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from ..schemas import (
    SENIORITY_BAND, CandidateProfile, EmploymentType, HardFilterResult, JobPosting, SearchPreferences, Seniority,
    SponsorshipStatus, VerificationStatus, WorkMode, msg,
)
from ..taxonomy import STATE_NAME_TO_ABBR, US_METROS, US_STATES
from ..textutils import norm_key
from ..verify.verifier import is_us_location


def _parse_user_location(loc: str) -> tuple[str, str]:
    parts = [p.strip() for p in loc.split(",")]
    city = parts[0].lower() if parts else ""
    state = ""
    if len(parts) > 1:
        s = parts[1].strip()
        state = s.upper() if s.upper() in US_STATES else STATE_NAME_TO_ABBR.get(s.lower(), "")
    elif city.upper() in US_STATES:
        state, city = city.upper(), ""
    elif city in STATE_NAME_TO_ABBR:
        state, city = STATE_NAME_TO_ABBR[city], ""
    return city, state


def location_matches(job_location: str, user_locations: list[str]) -> Optional[str]:
    """Return the user location that matches the job location, else None."""
    text = f" {norm_key(job_location)} "
    raw = job_location or ""
    for loc in user_locations:
        metro = next((m for m in US_METROS if norm_key(m) == norm_key(loc)), None)
        city, state = _parse_user_location(loc)
        cities = list(US_METROS.get(metro, [])) if metro else []
        if city:
            cities.append(city)
            for mname, members in US_METROS.items():
                if city in [m.lower() for m in members]:
                    cities += members
        for c in dict.fromkeys(x.lower() for x in cities):
            if f" {norm_key(c)} " in text:
                return loc
        if state and not city and not metro:
            if re.search(rf"(,|\s)\s*{state}\b", raw) or US_STATES[state].lower() in raw.lower():
                return loc
    return None


def evaluate_hard_filters(job: JobPosting, prefs: SearchPreferences, profile: CandidateProfile) -> list[HardFilterResult]:
    rules = prefs.hard_rules
    out: list[HardFilterResult] = []

    # 1. Liveness / verification
    v = job.verification.status
    if v == VerificationStatus.DEAD:
        detail = next((c.detail for c in job.verification.checks if c.passed is False), "")
        out.append(HardFilterResult(rule="liveness", passed=False, enforced=rules.liveness, reason=msg("hf.liveness.dead", detail=detail)))
    elif v == VerificationStatus.MISMATCH:
        detail = next((c.detail for c in job.verification.checks if c.passed is False), "")
        out.append(HardFilterResult(rule="liveness", passed=False, enforced=rules.liveness, reason=msg("hf.liveness.mismatch", detail=detail)))
    elif v == VerificationStatus.UNVERIFIED:
        out.append(HardFilterResult(rule="liveness", passed=True, known=False, reason=msg("hf.liveness.unverified")))
    else:
        out.append(HardFilterResult(rule="liveness", passed=True, reason=msg("hf.liveness.ok")))

    # 2. Work authorization
    sp = job.sponsorship
    if sp.status in (SponsorshipStatus.NO_SPONSORSHIP, SponsorshipStatus.CITIZEN_ONLY) and prefs.needs_sponsorship:
        key = "hf.auth.citizen" if sp.status == SponsorshipStatus.CITIZEN_ONLY else "hf.auth.no_sponsorship"
        out.append(HardFilterResult(rule="work_authorization", passed=False, enforced=rules.work_authorization,
                                    reason=msg(key), evidence=sp.quote))
    elif sp.status == SponsorshipStatus.CLEARANCE and (prefs.needs_sponsorship or not prefs.open_to_clearance_roles):
        out.append(HardFilterResult(rule="work_authorization", passed=False, enforced=rules.work_authorization,
                                    reason=msg("hf.auth.clearance"), evidence=sp.quote))
    elif sp.status == SponsorshipStatus.SPONSORS:
        out.append(HardFilterResult(rule="work_authorization", passed=True, reason=msg("hf.auth.sponsors"), evidence=sp.quote))
    else:
        out.append(HardFilterResult(rule="work_authorization", passed=True, known=not prefs.needs_sponsorship,
                                    reason=msg("hf.auth.unknown" if prefs.needs_sponsorship else "hf.auth.not_needed")))

    # 3. Location & work mode
    mode = job.work_mode
    us = is_us_location(job.location_text)
    if mode == WorkMode.REMOTE:
        if us is False:
            out.append(HardFilterResult(rule="location", passed=False, enforced=rules.location, reason=msg("hf.location.remote_non_us", location=job.location_text)))
        elif WorkMode.REMOTE in prefs.work_modes:
            out.append(HardFilterResult(rule="location", passed=True, known=us is not None, reason=msg("hf.location.remote_ok")))
        else:
            out.append(HardFilterResult(rule="location", passed=False, enforced=rules.location, reason=msg("hf.location.mode_excluded", mode="remote")))
    else:
        matched = location_matches(job.location_text, prefs.locations)
        mode_ok = mode == WorkMode.UNKNOWN or mode in prefs.work_modes
        if not mode_ok:
            out.append(HardFilterResult(rule="location", passed=False, enforced=rules.location, reason=msg("hf.location.mode_excluded", mode=mode.value)))
        elif matched:
            out.append(HardFilterResult(rule="location", passed=True, known=mode != WorkMode.UNKNOWN, reason=msg("hf.location.ok", location=matched)))
        elif us is False:
            out.append(HardFilterResult(rule="location", passed=False, enforced=rules.location, reason=msg("hf.location.non_us", location=job.location_text)))
        elif prefs.willing_to_relocate and us is not False:
            out.append(HardFilterResult(rule="location", passed=True, known=bool(job.location_text), reason=msg("hf.location.relocate", location=job.location_text or "?")))
        elif not job.location_text:
            out.append(HardFilterResult(rule="location", passed=True, known=False, reason=msg("hf.location.unknown")))
        else:
            out.append(HardFilterResult(rule="location", passed=False, enforced=rules.location, reason=msg("hf.location.outside", location=job.location_text)))

    # 4. Seniority
    if job.seniority == Seniority.UNKNOWN or not prefs.seniority:
        out.append(HardFilterResult(rule="seniority", passed=True, known=False, reason=msg("hf.seniority.unknown")))
    else:
        band = SENIORITY_BAND[job.seniority]
        distance = min(abs(band - SENIORITY_BAND.get(s, band)) for s in prefs.seniority if s != Seniority.UNKNOWN)
        if distance >= 2:
            out.append(HardFilterResult(rule="seniority", passed=False, enforced=rules.seniority,
                                        reason=msg("hf.seniority.too_far", level=job.seniority.value)))
        elif distance == 1:
            out.append(HardFilterResult(rule="seniority", passed=True, reason=msg("hf.seniority.adjacent", level=job.seniority.value)))
        else:
            out.append(HardFilterResult(rule="seniority", passed=True, reason=msg("hf.seniority.ok", level=job.seniority.value)))

    # 5. Years of experience
    need = job.min_years_experience
    if need is None:
        out.append(HardFilterResult(rule="years_experience", passed=True, known=False, reason=msg("hf.years.unknown")))
    elif need > profile.years_experience + prefs.years_tolerance:
        out.append(HardFilterResult(rule="years_experience", passed=False, enforced=rules.years_experience,
                                    reason=msg("hf.years.too_many", need=f"{need:g}", have=f"{profile.years_experience:g}")))
    else:
        out.append(HardFilterResult(rule="years_experience", passed=True,
                                    reason=msg("hf.years.ok", need=f"{need:g}", have=f"{profile.years_experience:g}")))

    # 6. Employment type
    et = job.employment_type
    if et == EmploymentType.UNKNOWN or not prefs.employment_types:
        out.append(HardFilterResult(rule="employment_type", passed=True, known=False, reason=msg("hf.etype.unknown")))
    elif et not in prefs.employment_types:
        out.append(HardFilterResult(rule="employment_type", passed=False, enforced=rules.employment_type, reason=msg("hf.etype.mismatch", etype=et.value)))
    else:
        out.append(HardFilterResult(rule="employment_type", passed=True, reason=msg("hf.etype.ok", etype=et.value)))

    # 7. Posting age
    age = job.age_days()
    if age is None:
        out.append(HardFilterResult(rule="posted_age", passed=True, known=False, reason=msg("hf.age.unknown")))
    elif age > prefs.posted_within_days and job.date_updated and (date.today() - job.date_updated).days <= prefs.posted_within_days:
        # Evergreen/reposted requisition: originally old but recently updated → keep, but warn.
        out.append(HardFilterResult(rule="posted_age", passed=True, known=False,
                                    reason=msg("hf.age.updated", days=age, updated=(date.today() - job.date_updated).days)))
    elif age > prefs.posted_within_days:
        out.append(HardFilterResult(rule="posted_age", passed=False, enforced=rules.posted_age, reason=msg("hf.age.too_old", days=age, limit=prefs.posted_within_days)))
    else:
        out.append(HardFilterResult(rule="posted_age", passed=True, reason=msg("hf.age.ok", days=age)))

    # 8. Salary floor
    lo, hi = job.annual_salary_range()
    if not prefs.min_salary:
        pass
    elif hi is None:
        out.append(HardFilterResult(rule="salary", passed=True, known=False, reason=msg("hf.salary.unknown")))
    elif hi < prefs.min_salary:
        out.append(HardFilterResult(rule="salary", passed=False, enforced=rules.salary, reason=msg("hf.salary.below", max=f"{hi:,.0f}", min=f"{prefs.min_salary:,.0f}")))
    else:
        out.append(HardFilterResult(rule="salary", passed=True, reason=msg("hf.salary.ok", max=f"{hi:,.0f}")))

    # 9. Blocklists
    company = norm_key(job.company)
    blocked = next((c for c in prefs.company_blocklist if norm_key(c) and norm_key(c) in company), None)
    title_kw = next((k for k in prefs.title_exclude_keywords if k.strip() and re.search(rf"\b{re.escape(k.strip().lower())}\b", job.title.lower())), None)
    if blocked:
        out.append(HardFilterResult(rule="blocklists", passed=False, enforced=rules.blocklists, reason=msg("hf.block.company", company=blocked)))
    elif title_kw:
        out.append(HardFilterResult(rule="blocklists", passed=False, enforced=rules.blocklists, reason=msg("hf.block.title", keyword=title_kw)))
    return out
