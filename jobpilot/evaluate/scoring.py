"""EVALUATE part 2 — weighted soft scoring, tiers, reasons, risks, ghost-job signals."""

from __future__ import annotations

import re
from typing import Optional

import numpy as np

from ..schemas import (
    SENIORITY_BAND, CandidateProfile, CompanyIntel, DimensionScore, EvidenceItem, EvidenceStatus, GhostRisk,
    HardFilterResult, JobPosting, MatchResult, RequirementCategory, RequirementKind, SearchPreferences, Seniority,
    SponsorshipStatus, Tier, VerificationStatus, WorkMode, msg,
)
from ..taxonomy import PAY_TRANSPARENCY_STATES, ROLE_FAMILIES
from ..textutils import norm_key
from ..verify.verifier import title_similarity

STATUS_VALUE = {EvidenceStatus.MET: 1.0, EvidenceStatus.PARTIAL: 0.5, EvidenceStatus.GAP: 0.0, EvidenceStatus.UNVERIFIED: 0.0}
TIER_THRESHOLDS = {"A": 75.0, "B": 62.0, "C": 48.0}


def skills_dimension(evidence: list[EvidenceItem]) -> DimensionScore:
    total = got = 0.0
    met = req_total = 0
    for e in evidence:
        if e.status == EvidenceStatus.NOT_APPLICABLE or e.category == RequirementCategory.AUTHORIZATION:
            continue
        w = 1.0 if e.kind == RequirementKind.REQUIRED else 0.35
        total += w
        got += w * STATUS_VALUE.get(e.status, 0.0)
        if e.kind == RequirementKind.REQUIRED:
            req_total += 1
            met += e.status == EvidenceStatus.MET
    if total == 0:
        return DimensionScore(score=50, weight=0, known=False, detail="no scorable requirements")
    return DimensionScore(score=round(100 * got / total, 1), weight=0, detail=f"{met}/{req_total} required met")


def experience_dimension(job: JobPosting, prefs: SearchPreferences, profile: CandidateProfile) -> DimensionScore:
    parts, known = [], True
    if job.seniority == Seniority.UNKNOWN:
        parts.append(60.0)
        known = False
    else:
        band = SENIORITY_BAND[job.seniority]
        dist = min((abs(band - SENIORITY_BAND[s]) for s in prefs.seniority if s in SENIORITY_BAND), default=1)
        parts.append({0: 100.0, 1: 60.0}.get(dist, 20.0))
    need = job.min_years_experience
    if need is None:
        parts.append(70.0)
        known = known and False
    else:
        gap = need - profile.years_experience
        parts.append(100.0 if gap <= 0 else max(0.0, 100 - 30 * gap))
    return DimensionScore(score=round(sum(parts) / len(parts), 1), weight=0, known=known,
                          detail=f"level={job.seniority.value}, min_years={need if need is not None else '?'}")


def title_alignment(job_title: str, prefs: SearchPreferences) -> float:
    targets = list(prefs.target_titles)
    for fam in prefs.role_families:
        targets += ROLE_FAMILIES.get(fam, [])
    best = max((title_similarity(job_title, t) for t in targets), default=0.0)
    return min(best, 1.0)


def location_dimension(job: JobPosting, prefs: SearchPreferences, hard: list[HardFilterResult]) -> DimensionScore:
    order = {m: i for i, m in enumerate(prefs.work_modes)}
    loc_rule = next((h for h in hard if h.rule == "location"), None)
    if loc_rule and not loc_rule.passed:
        return DimensionScore(score=10, weight=0, detail="outside preferences")
    if job.work_mode == WorkMode.UNKNOWN:
        return DimensionScore(score=60, weight=0, known=False, detail="work mode unknown")
    rank = order.get(job.work_mode, len(order))
    base = 100 - 12 * rank
    if loc_rule and loc_rule.reason.key == "hf.location.relocate":
        base = min(base, 55)
    return DimensionScore(score=float(max(base, 30)), weight=0, detail=f"{job.work_mode.value} (preference #{rank + 1})")


def compensation_dimension(job: JobPosting, prefs: SearchPreferences) -> DimensionScore:
    lo, hi = job.annual_salary_range()
    if hi is None and lo is None:
        return DimensionScore(score=50, weight=0, known=False, detail="salary not posted")
    top = hi or lo or 0
    if not prefs.min_salary:
        return DimensionScore(score=65, weight=0, detail=f"up to ${top:,.0f}")
    if top >= prefs.min_salary * 1.15:
        score = 100.0
    elif top >= prefs.min_salary:
        score = 80.0
    else:
        score = max(10.0, 80 * top / prefs.min_salary - 20)
    return DimensionScore(score=round(score, 1), weight=0, detail=f"up to ${top:,.0f} vs floor ${prefs.min_salary:,.0f}")


def sponsorship_dimension(job: JobPosting, prefs: SearchPreferences, intel: Optional[CompanyIntel]) -> Optional[DimensionScore]:
    if not prefs.needs_sponsorship:
        return None
    if job.sponsorship.status == SponsorshipStatus.SPONSORS:
        return DimensionScore(score=100, weight=0, detail="posting offers sponsorship")
    if job.sponsorship.status != SponsorshipStatus.UNKNOWN:
        return DimensionScore(score=0, weight=0, detail=job.sponsorship.status.value)
    if intel and intel.sponsorship != "unknown":
        score = {"frequent": 85, "occasional": 68, "rare": 40, "none_found": 25}.get(intel.sponsorship, 50)
        return DimensionScore(score=score, weight=0, detail=f"employer history: {intel.sponsorship}")
    return DimensionScore(score=50, weight=0, known=False, detail="not stated")


def company_dimension(job: JobPosting, prefs: SearchPreferences) -> DimensionScore:
    company = norm_key(job.company)
    if any(norm_key(c) and norm_key(c) in company for c in prefs.dream_companies):
        return DimensionScore(score=100, weight=0, detail="dream company")
    industry = (job.industry or "").lower()
    if industry and any(i.lower().split(" /")[0] in industry for i in prefs.industries_avoid):
        return DimensionScore(score=20, weight=0, detail=f"industry to avoid: {job.industry}")
    if industry and any(i.lower().split(" /")[0] in industry for i in prefs.industries_prefer):
        return DimensionScore(score=80, weight=0, detail=f"preferred industry: {job.industry}")
    return DimensionScore(score=55, weight=0, known=bool(industry), detail=job.industry or "no preference signal")


def freshness_dimension(job: JobPosting) -> DimensionScore:
    age = job.age_days()
    if age is None:
        return DimensionScore(score=55, weight=0, known=False, detail="date unknown")
    score = 100 if age <= 2 else 85 if age <= 7 else 70 if age <= 14 else 50 if age <= 30 else 30
    return DimensionScore(score=float(score), weight=0, detail=f"{age} days old")


def ghost_signals(job: JobPosting) -> tuple[GhostRisk, list]:
    signals = []
    strong = 0
    age = job.age_days()
    if age is not None and age > 45:
        signals.append(msg("ghost.old", days=age))
        strong += 1 if age > 60 else 0
    if job.date_posted is None:
        signals.append(msg("ghost.no_date"))
    lo, hi = job.annual_salary_range()
    state = next((s for s in PAY_TRANSPARENCY_STATES if re.search(rf"(,|\s){s}\b", job.location_text or "")), None)
    if hi is None and lo is None and state:
        signals.append(msg("ghost.no_salary_transparency", state=state))
    if 0 < len(job.description_text) < 700:
        signals.append(msg("ghost.thin_description"))
    if job.verification.status == VerificationStatus.UNVERIFIED:
        signals.append(msg("ghost.unverified"))
    if strong or len(signals) >= 3:
        risk = GhostRisk.HIGH
    elif len(signals) >= 2:
        risk = GhostRisk.MEDIUM
    else:
        risk = GhostRisk.LOW
    return risk, signals


class Scorer:
    def __init__(self, prefs: SearchPreferences, profile: CandidateProfile) -> None:
        self.prefs = prefs
        self.profile = profile

    def score(
        self,
        job: JobPosting,
        hard: list[HardFilterResult],
        evidence: list[EvidenceItem],
        *,
        dense_alignment: Optional[float] = None,
        feedback_affinity: Optional[float] = None,
        intel: Optional[CompanyIntel] = None,
        run_id: str = "",
    ) -> MatchResult:
        w = self.prefs.weights.as_dict()
        dims: dict[str, DimensionScore] = {
            "skills": skills_dimension(evidence),
            "experience": experience_dimension(job, self.prefs, self.profile),
            "location": location_dimension(job, self.prefs, hard),
            "compensation": compensation_dimension(job, self.prefs),
            "company": company_dimension(job, self.prefs),
            "freshness": freshness_dimension(job),
        }
        title_part = title_alignment(job.title, self.prefs)
        dense_part = float(np.clip(((dense_alignment or 0.0) - 0.2) / 0.55, 0, 1)) if dense_alignment is not None else title_part
        dims["role_alignment"] = DimensionScore(score=round(100 * (0.65 * title_part + 0.35 * dense_part), 1), weight=0,
                                                detail=f"title overlap {title_part:.2f}, semantic {dense_part:.2f}")
        sp = sponsorship_dimension(job, self.prefs, intel)
        if sp is not None:
            dims["sponsorship"] = sp
        if feedback_affinity is not None:
            dims["feedback"] = DimensionScore(score=round(50 + 50 * float(np.clip(feedback_affinity, -1, 1)), 1), weight=0,
                                              detail=f"similarity to your 👍/👎 history {feedback_affinity:+.2f}")
        weight_sum = sum(w.get(k, 0) for k in dims) or 1.0
        for k, d in dims.items():
            d.weight = round(w.get(k, 0) / weight_sum, 4)
        total = sum(d.score * d.weight for d in dims.values())
        known_weight = sum(d.weight for d in dims.values() if d.known)
        v = job.verification.status
        confidence = known_weight * (1.0 if v in (VerificationStatus.VERIFIED, VerificationStatus.DEMO) else 0.7)

        hard_pass = all(h.passed or not h.enforced for h in hard)
        if not hard_pass:
            tier = Tier.REJECTED
        elif total >= TIER_THRESHOLDS["A"] and v in (VerificationStatus.VERIFIED, VerificationStatus.DEMO):
            tier = Tier.A
        elif total >= TIER_THRESHOLDS["B"] - (0 if v != VerificationStatus.UNVERIFIED else -5):
            tier = Tier.B
        elif total >= TIER_THRESHOLDS["C"]:
            tier = Tier.C
        else:
            tier = Tier.D
        # Relevance gate: a role that matches neither the target titles nor the skills is never a "stretch".
        if tier in (Tier.A, Tier.B, Tier.C) and dims["role_alignment"].score < 35 and dims["skills"].score < 45:
            tier = Tier.D

        risk, ghost = ghost_signals(job)
        result = MatchResult(job=job, run_id=run_id, hard_filters=hard, hard_pass=hard_pass, evidence=evidence,
                             dimensions=dims, total_score=round(total, 1), confidence=round(confidence, 2), tier=tier,
                             ghost_risk=risk, ghost_signals=ghost, company_intel=intel)
        result.reasons = self._reasons(result)
        result.gaps = [e.requirement_text for e in evidence
                       if e.kind == RequirementKind.REQUIRED and e.status in (EvidenceStatus.GAP, EvidenceStatus.UNVERIFIED)][:5]
        result.risks = self._risks(result)
        return result

    # ------------------------------------------------------------------ #
    def _reasons(self, r: MatchResult) -> list:
        out = []
        required = [e for e in r.evidence if e.kind == RequirementKind.REQUIRED and e.status != EvidenceStatus.NOT_APPLICABLE]
        met = [e for e in required if e.status == EvidenceStatus.MET]
        if required:
            out.append((r.dimensions["skills"].score, msg("r.skills", met=len(met), total=len(required),
                                                          examples=", ".join(_short(e.requirement_text) for e in met[:3]))))
        if r.job.sponsorship.status == SponsorshipStatus.SPONSORS:
            out.append((100, msg("r.sponsors")))
        elif r.company_intel and r.company_intel.sponsorship in ("frequent", "occasional"):
            out.append((80, msg("r.intel", level=r.company_intel.sponsorship)))
        age = r.job.age_days()
        if age is not None and age <= 7:
            out.append((85, msg("r.fresh", days=age)))
        if r.job.work_mode == WorkMode.REMOTE:
            out.append((r.dimensions["location"].score, msg("r.remote")))
        else:
            loc = next((h for h in r.hard_filters if h.rule == "location" and h.reason.key == "hf.location.ok"), None)
            if loc:
                out.append((r.dimensions["location"].score, msg("r.location", location=loc.reason.params.get("location", ""))))
        if r.dimensions["role_alignment"].score >= 70:
            out.append((r.dimensions["role_alignment"].score, msg("r.title")))
        if r.dimensions["company"].score >= 100:
            out.append((100, msg("r.dream", company=r.job.company)))
        lo, hi = r.job.annual_salary_range()
        if hi:
            out.append((r.dimensions["compensation"].score, msg("r.salary", range=f"${(lo or hi):,.0f}–${hi:,.0f}")))
        out.sort(key=lambda x: -x[0])
        return [m for _, m in out[:4]]

    def _risks(self, r: MatchResult) -> list:
        risks = []
        if r.job.verification.status == VerificationStatus.UNVERIFIED:
            risks.append(msg("risk.unverified"))
        for h in r.hard_filters:
            if not h.passed and not h.enforced:
                risks.append(msg("risk.disabled_rule", rule=h.rule, reason_key=h.reason.key, **h.reason.params))
        if self.prefs.needs_sponsorship and r.job.sponsorship.status == SponsorshipStatus.UNKNOWN and not (
            r.company_intel and r.company_intel.sponsorship in ("frequent", "occasional")
        ):
            risks.append(msg("risk.sponsor_unknown"))
        yrs = next((h for h in r.hard_filters if h.rule == "years_experience" and h.passed and h.known), None)
        if yrs and r.job.min_years_experience and r.job.min_years_experience > self.profile.years_experience:
            risks.append(msg("risk.stretch_years", need=f"{r.job.min_years_experience:g}", have=f"{self.profile.years_experience:g}"))
        if r.ghost_risk != GhostRisk.LOW:
            risks.append(msg("risk.ghost", level=r.ghost_risk.value))
        return risks


def _short(text: str, n: int = 28) -> str:
    t = re.sub(r"^(experience (with|in)|proficiency (with|in)|knowledge of|strong|solid)\s+", "", text.strip(), flags=re.I)
    return t if len(t) <= n else t[: n - 1] + "…"
