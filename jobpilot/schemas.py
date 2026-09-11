"""Domain schemas shared by every stage of the agent.

All models are Pydantic v2 so they validate LLM output, serialize to SQLite as
JSON, and render cleanly in the UI.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Msg(BaseModel):
    """A translatable message: template key + parameters (rendered by jobpilot.messages)."""

    key: str
    params: dict[str, Any] = Field(default_factory=dict)


def msg(key: str, **params: Any) -> Msg:
    return Msg(key=key, params=params)


# --------------------------------------------------------------------------- #
# Enumerations (these drive every dropdown in the UI)
# --------------------------------------------------------------------------- #
class Seniority(str, Enum):
    INTERN = "intern"
    ENTRY = "entry"          # new grad / junior / associate
    MID = "mid"
    SENIOR = "senior"
    STAFF = "staff"
    PRINCIPAL = "principal"  # principal / distinguished / architect
    MANAGER = "manager"      # people manager / director track
    UNKNOWN = "unknown"


SENIORITY_BAND: dict[Seniority, int] = {
    Seniority.INTERN: 0,
    Seniority.ENTRY: 1,
    Seniority.MID: 2,
    Seniority.SENIOR: 3,
    Seniority.STAFF: 4,
    Seniority.MANAGER: 4,
    Seniority.PRINCIPAL: 5,
}


class WorkMode(str, Enum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    INTERNSHIP = "internship"
    TEMPORARY = "temporary"
    UNKNOWN = "unknown"


class WorkAuth(str, Enum):
    US_CITIZEN = "us_citizen"
    PERMANENT_RESIDENT = "permanent_resident"
    F1_CPT = "f1_cpt"
    F1_OPT = "f1_opt"
    F1_STEM_OPT = "f1_stem_opt"
    H1B = "h1b"
    OTHER_VISA = "other_visa"


class DegreeLevel(str, Enum):
    NONE = "none"
    ASSOCIATE = "associate"
    BACHELOR = "bachelor"
    MASTER = "master"
    PHD = "phd"


DEGREE_RANK = {
    DegreeLevel.NONE: 0,
    DegreeLevel.ASSOCIATE: 1,
    DegreeLevel.BACHELOR: 2,
    DegreeLevel.MASTER: 3,
    DegreeLevel.PHD: 4,
}


class RequirementKind(str, Enum):
    REQUIRED = "required"
    PREFERRED = "preferred"


class RequirementCategory(str, Enum):
    SKILL = "skill"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    CERTIFICATION = "certification"
    AUTHORIZATION = "authorization"
    OTHER = "other"


class EvidenceStatus(str, Enum):
    MET = "met"
    PARTIAL = "partial"
    GAP = "gap"
    UNVERIFIED = "unverified"   # LLM claimed evidence that could not be found verbatim
    NOT_APPLICABLE = "n/a"


class SponsorshipStatus(str, Enum):
    SPONSORS = "sponsors"                # posting explicitly offers sponsorship
    NO_SPONSORSHIP = "no_sponsorship"    # explicit "no sponsorship now or future"
    CITIZEN_ONLY = "citizen_only"        # US citizen / green card / US person only
    CLEARANCE = "clearance"              # security clearance required
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    VERIFIED = "verified"      # page/API reachable, open, and consistent with claim
    UNVERIFIED = "unverified"  # could not be checked (blocked, aggregator, timeout)
    DEAD = "dead"              # 404/410/closed/expired
    MISMATCH = "mismatch"      # page exists but title/company do not match the claim
    DEMO = "demo"              # offline sample data


class Tier(str, Enum):
    A = "A"   # apply now
    B = "B"   # tailor, then apply
    C = "C"   # stretch
    D = "D"   # low fit
    REJECTED = "rejected"


class GhostRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# --------------------------------------------------------------------------- #
# Candidate side
# --------------------------------------------------------------------------- #
class Education(BaseModel):
    school: str = ""
    degree: DegreeLevel = DegreeLevel.NONE
    field: str = ""
    graduation: str = ""  # free text, e.g. "May 2027"


class Experience(BaseModel):
    title: str = ""
    company: str = ""
    start: str = ""
    end: str = ""
    bullets: list[str] = Field(default_factory=list)


class Project(BaseModel):
    name: str = ""
    description: str = ""
    technologies: list[str] = Field(default_factory=list)


class CandidateProfile(BaseModel):
    """What the agent knows about the candidate — built from the resume, then
    reviewed and edited by the user (human-in-the-loop)."""

    name: str = ""
    headline: str = ""
    summary: str = ""
    current_location: str = ""
    years_experience: float = 0.0
    highest_degree: DegreeLevel = DegreeLevel.NONE
    education: list[Education] = Field(default_factory=list)
    experiences: list[Experience] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    resume_text: str = ""
    updated_at: datetime = Field(default_factory=utcnow)

    @field_validator("years_experience")
    @classmethod
    def _years_range(cls, v: float) -> float:
        return float(min(max(v or 0.0, 0.0), 60.0))

    def is_ready(self) -> bool:
        return bool(self.skills or self.experiences or self.resume_text.strip())


class ScoreWeights(BaseModel):
    skills: float = 0.34
    experience: float = 0.14
    role_alignment: float = 0.14
    location: float = 0.08
    compensation: float = 0.06
    sponsorship: float = 0.12
    company: float = 0.05
    freshness: float = 0.04
    feedback: float = 0.03

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in self.model_dump().items()}


class HardRuleToggles(BaseModel):
    """Which rules are enforced as hard gates. Disabled rules still produce a
    warning and feed the soft score, so the user never loses information."""

    liveness: bool = True
    work_authorization: bool = True
    location: bool = True
    seniority: bool = True
    years_experience: bool = True
    employment_type: bool = True
    posted_age: bool = True
    salary: bool = False
    blocklists: bool = True


class SearchPreferences(BaseModel):
    target_titles: list[str] = Field(default_factory=list)
    role_families: list[str] = Field(default_factory=list)
    seniority: list[Seniority] = Field(default_factory=lambda: [Seniority.ENTRY, Seniority.MID])
    employment_types: list[EmploymentType] = Field(default_factory=lambda: [EmploymentType.FULL_TIME])
    work_modes: list[WorkMode] = Field(
        default_factory=lambda: [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE]
    )
    locations: list[str] = Field(default_factory=list)
    willing_to_relocate: bool = False
    posted_within_days: int = 14
    min_salary: Optional[int] = None
    work_auth: WorkAuth = WorkAuth.F1_OPT
    needs_sponsorship: bool = True
    open_to_clearance_roles: bool = False
    years_tolerance: float = 2.0
    company_blocklist: list[str] = Field(default_factory=list)
    title_exclude_keywords: list[str] = Field(default_factory=list)
    dream_companies: list[str] = Field(default_factory=list)
    industries_prefer: list[str] = Field(default_factory=list)
    industries_avoid: list[str] = Field(default_factory=list)
    extra_keywords: list[str] = Field(default_factory=list)
    weights: ScoreWeights = Field(default_factory=ScoreWeights)
    hard_rules: HardRuleToggles = Field(default_factory=HardRuleToggles)

    def validation_errors(self) -> list[str]:
        errors = []
        if not self.target_titles:
            errors.append("target_titles")
        if not self.seniority:
            errors.append("seniority")
        if not self.work_modes:
            errors.append("work_modes")
        if WorkMode.REMOTE not in self.work_modes and not self.locations and not self.willing_to_relocate:
            errors.append("locations")
        return errors


# --------------------------------------------------------------------------- #
# Job side
# --------------------------------------------------------------------------- #
class Requirement(BaseModel):
    id: str = ""
    text: str
    kind: RequirementKind = RequirementKind.REQUIRED
    category: RequirementCategory = RequirementCategory.SKILL
    terms: list[str] = Field(default_factory=list)
    min_years: Optional[float] = None


class SponsorshipSignal(BaseModel):
    status: SponsorshipStatus = SponsorshipStatus.UNKNOWN
    quote: str = ""


class VerificationCheck(BaseModel):
    name: str
    passed: Optional[bool] = None   # None = could not be evaluated
    detail: str = ""


class Verification(BaseModel):
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    http_status: Optional[int] = None
    final_url: str = ""
    checks: list[VerificationCheck] = Field(default_factory=list)
    checked_at: Optional[datetime] = None


class JobCandidate(BaseModel):
    """A lead produced by the SEARCH stage — not yet trusted."""

    title: str = ""
    company: str = ""
    location: str = ""
    url: str = ""
    posted: str = ""
    work_mode: str = ""
    snippet: str = ""
    source: str = "gemini_search"
    task_id: str = ""
    grounded: bool = False  # URL also appeared among resolved grounding sources


class JobPosting(BaseModel):
    id: str
    url: str
    canonical_url: str = ""
    apply_url: str = ""
    source: str = "web"
    title: str = ""
    company: str = ""
    location_text: str = ""
    work_mode: WorkMode = WorkMode.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    seniority: Seniority = Seniority.UNKNOWN
    date_posted: Optional[date] = None
    date_updated: Optional[date] = None
    valid_through: Optional[date] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_currency: str = "USD"
    salary_period: str = "year"
    description_text: str = ""
    requirements: list[Requirement] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    min_years_experience: Optional[float] = None
    degree_required: Optional[DegreeLevel] = None
    sponsorship: SponsorshipSignal = Field(default_factory=SponsorshipSignal)
    industry: str = ""
    extraction_method: str = "heuristic"
    discovered_by: list[str] = Field(default_factory=list)
    grounded: bool = False
    verification: Verification = Field(default_factory=Verification)
    first_seen: datetime = Field(default_factory=utcnow)
    last_seen: datetime = Field(default_factory=utcnow)

    def age_days(self, today: Optional[date] = None) -> Optional[int]:
        if not self.date_posted:
            return None
        today = today or datetime.now(timezone.utc).date()
        return max((today - self.date_posted).days, 0)

    def annual_salary_range(self) -> tuple[Optional[float], Optional[float]]:
        factor = {"hour": 2080, "day": 260, "week": 52, "month": 12}.get(self.salary_period, 1)
        lo = self.salary_min * factor if self.salary_min else None
        hi = self.salary_max * factor if self.salary_max else None
        return lo, hi


# --------------------------------------------------------------------------- #
# Evaluation side
# --------------------------------------------------------------------------- #
class EvidenceItem(BaseModel):
    requirement_id: str
    requirement_text: str
    kind: RequirementKind = RequirementKind.REQUIRED
    category: RequirementCategory = RequirementCategory.SKILL
    status: EvidenceStatus = EvidenceStatus.GAP
    quote: str = ""
    chunk_id: str = ""
    source_label: str = ""
    rationale: str = ""
    method: str = "lexical"


class HardFilterResult(BaseModel):
    rule: str
    passed: bool
    enforced: bool = True
    known: bool = True
    reason: Msg = Field(default_factory=lambda: Msg(key="hf.ok"))
    evidence: str = ""


class DimensionScore(BaseModel):
    score: float
    weight: float
    known: bool = True
    detail: str = ""


class CompanyIntel(BaseModel):
    company: str
    sponsorship: str = "unknown"  # frequent | occasional | rare | none_found | unknown
    note: str = ""
    source_url: str = ""
    fetched_at: datetime = Field(default_factory=utcnow)


class MatchResult(BaseModel):
    job: JobPosting
    run_id: str = ""
    hard_filters: list[HardFilterResult] = Field(default_factory=list)
    hard_pass: bool = True
    evidence: list[EvidenceItem] = Field(default_factory=list)
    dimensions: dict[str, DimensionScore] = Field(default_factory=dict)
    total_score: float = 0.0
    confidence: float = 0.0
    tier: Tier = Tier.D
    reasons: list[Msg] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    risks: list[Msg] = Field(default_factory=list)
    ghost_risk: GhostRisk = GhostRisk.LOW
    ghost_signals: list[Msg] = Field(default_factory=list)
    company_intel: Optional[CompanyIntel] = None

    @property
    def failed_rules(self) -> list[HardFilterResult]:
        return [r for r in self.hard_filters if r.enforced and not r.passed]


# --------------------------------------------------------------------------- #
# Run / reporting side
# --------------------------------------------------------------------------- #
class RunConfig(BaseModel):
    max_iterations: int = 3
    max_search_calls: int = 10
    max_search_queries: int = 40
    target_shortlist: int = 8
    max_jobs_per_iteration: int = 30
    fetch_concurrency: int = 6
    llm_concurrency: int = 2
    llm_rpm: int = 0  # requests-per-minute cap for Gemini (0 = unlimited; set ~10-15 on the free tier)
    company_intel: bool = True
    max_company_intel_calls: int = 6
    use_llm_extraction: bool = True
    use_llm_evidence: bool = True
    demo_mode: bool = False


class Usage(BaseModel):
    llm_calls: int = 0
    llm_failures: int = 0
    prompt_tokens: int = 0
    output_tokens: int = 0
    search_calls: int = 0
    search_queries: int = 0
    url_context_calls: int = 0
    embed_calls: int = 0
    http_fetches: int = 0

    def estimated_cost_usd(self, input_per_m: float = 0.75, output_per_m: float = 3.75,
                           search_per_k: float = 14.0) -> float:
        tokens = self.prompt_tokens / 1e6 * input_per_m + self.output_tokens / 1e6 * output_per_m
        return round(tokens + self.search_queries / 1000 * search_per_k, 4)


class Issue(BaseModel):
    stage: str
    severity: str = "warning"  # info | warning | error
    message: str
    resolution: str = ""
    ts: datetime = Field(default_factory=utcnow)


class IterationReport(BaseModel):
    number: int
    tasks: list[str] = Field(default_factory=list)
    leads: int = 0
    new_unique: int = 0
    verified: int = 0
    unverified: int = 0
    dead: int = 0
    mismatch: int = 0
    hard_passed: int = 0
    shortlisted: int = 0
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    diagnosis: list[Msg] = Field(default_factory=list)
    actions: list[Msg] = Field(default_factory=list)
    seconds: float = 0.0


class RunReport(BaseModel):
    run_id: str
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: Optional[datetime] = None
    status: str = "running"  # running | completed | failed | stopped
    stop_reason: str = ""
    mode: str = "live"
    iterations: list[IterationReport] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    usage: Usage = Field(default_factory=Usage)
    funnel: dict[str, int] = Field(default_factory=dict)
    tier_counts: dict[str, int] = Field(default_factory=dict)
    suggestions: list[Msg] = Field(default_factory=list)
    top_job_ids: list[str] = Field(default_factory=list)


class AgentEvent(BaseModel):
    stage: str
    message: str
    level: str = "info"
    data: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)
