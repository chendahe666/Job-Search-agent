"""Conservative evidence reporting, not a qualification-verification service.

Declared skills are self-reports. Free-text mentions (including negations) are
not sufficient evidence of proficiency. No achievement is synthesized here.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import re
from typing import Any
from .profile_analyzer import UserProfile


@dataclass(frozen=True)
class EvidenceNode:
    """A requirement and its explicit, user-reported source, if any."""
    requirement: str
    status: str
    source_type: str
    source_quote: str
    confidence: float | None
    citation_id: str


@dataclass(frozen=True)
class GroundingReport:
    """Compatibility fields retain unknown metrics as None rather than fake zeros."""
    job_id: str
    job_title: str
    company: str
    grounding_coverage: float
    hallucination_rate: float | None
    evidence_tree: list[dict[str, Any]]
    verified_skills: list[str]  # Legacy name: these are self-declared, NOT verified.
    skill_gaps: list[str]  # Legacy name: absent evidence is unknown, not inability.
    tailored_bullets: list[str]
    ats_readability_score: int | None

    def to_dict(self):
        """Return a JSON-compatible report."""
        return asdict(self)


class EvidenceGrounder:
    """Use explicit declarations only; leave unsupported requirements unknown."""
    @staticmethod
    def _normalize(text):
        return re.sub(r"[^a-z0-9+#.]", "", text.casefold())

    @classmethod
    def audit_match(cls, profile: UserProfile, job: dict[str, Any]) -> GroundingReport:
        """Report source coverage without fabricated accomplishments or accuracy metrics."""
        declared = {cls._normalize(s): s for s in profile.skills}
        nodes, matches, unknown = [], [], []
        requirements = list(dict.fromkeys(job.get("required_skills", [])))
        for i, requirement in enumerate(requirements):
            skill = declared.get(cls._normalize(requirement))
            (matches if skill else unknown).append(requirement)
            nodes.append(asdict(EvidenceNode(
                requirement=requirement, status="SELF_REPORTED" if skill else "NEEDS_CONFIRMATION",
                source_type="SKILL_LIST" if skill else "NONE",
                source_quote=skill or "No explicit skill declaration; ask the candidate.",
                confidence=None, citation_id=f"EV-{job.get('id', 'job')}-{i+1}",
            )))
        # A job responsibility is never candidate evidence; preserve supplied text.
        bullets = [f"{profile.professional_summary} [Src: Candidate-Summary; self-reported]"] if profile.professional_summary else []
        return GroundingReport(
            job_id=job.get("id", ""), job_title=job.get("title", ""), company=job.get("company", ""),
            grounding_coverage=len(matches) / max(len(requirements), 1), hallucination_rate=None,
            evidence_tree=nodes, verified_skills=matches, skill_gaps=unknown,
            tailored_bullets=bullets, ats_readability_score=None,
        )
