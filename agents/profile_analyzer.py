"""Profile-analyzer specialist for converting UI input into structured context.

The Profile Analyzer is intentionally deterministic. In an agentic workflow,
not every specialist needs to be an LLM: this agent owns validation,
normalization, and the hand-off contract used by downstream agents.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class UserProfile:
    """Normalized representation of a job seeker's background and preferences."""

    skills: tuple[str, ...]
    experience_level: str
    years_experience: float
    target_roles: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    work_preferences: tuple[str, ...] = ()
    professional_summary: str = ""

    def to_embedding_text(self) -> str:
        """Create a natural-language document for semantic matching.

        Labels keep unlike concepts (such as skills and locations) separable in
        the embedding while still producing ordinary language for the model.
        """

        parts = [
            f"Candidate skills: {', '.join(self.skills)}.",
            (
                "Experience: "
                f"{self.experience_level}, {self.years_experience:g} years."
            ),
        ]
        if self.target_roles:
            parts.append(f"Target roles: {', '.join(self.target_roles)}.")
        if self.preferred_locations:
            parts.append(
                f"Preferred locations: {', '.join(self.preferred_locations)}."
            )
        if self.work_preferences:
            parts.append(f"Work preferences: {', '.join(self.work_preferences)}.")
        if self.professional_summary:
            parts.append(f"Background and goals: {self.professional_summary.strip()}")
        return " ".join(parts)

    def to_prompt_dict(self) -> dict[str, object]:
        """Return a JSON-serializable payload for the reasoning specialist."""

        payload = asdict(self)
        for key, value in payload.items():
            if isinstance(value, tuple):
                payload[key] = list(value)
        return payload


class ProfileAnalyzer:
    """Parse raw form fields and enforce a stable profile schema."""

    _SPLIT_PATTERN = re.compile(r"[,;\n|]+")

    @classmethod
    def _split_values(cls, raw: str | Iterable[str] | None) -> tuple[str, ...]:
        """Split comma/newline input, remove duplicates, and preserve order."""

        if raw is None:
            return ()
        values = cls._SPLIT_PATTERN.split(raw) if isinstance(raw, str) else raw

        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = re.sub(r"\s+", " ", str(value)).strip()
            key = cleaned.casefold()
            if cleaned and key not in seen:
                normalized.append(cleaned)
                seen.add(key)
        return tuple(normalized)

    def analyze(
        self,
        *,
        skills: str | Iterable[str],
        experience_level: str,
        years_experience: float | int,
        target_roles: str | Iterable[str] | None = None,
        preferred_locations: str | Iterable[str] | None = None,
        work_preferences: str | Iterable[str] | None = None,
        professional_summary: str = "",
    ) -> UserProfile:
        """Validate and normalize raw UI values into a :class:`UserProfile`.

        Raises:
            ValueError: If required skills are absent or years are invalid.
        """

        parsed_skills = self._split_values(skills)
        if not parsed_skills:
            raise ValueError("Add at least one skill before running the match.")

        level = re.sub(r"\s+", " ", experience_level).strip()
        if not level:
            raise ValueError("Choose an experience level.")

        years = float(years_experience)
        if not 0 <= years <= 60:
            raise ValueError("Years of experience must be between 0 and 60.")

        return UserProfile(
            skills=parsed_skills,
            experience_level=level,
            years_experience=years,
            target_roles=self._split_values(target_roles),
            preferred_locations=self._split_values(preferred_locations),
            work_preferences=self._split_values(work_preferences),
            professional_summary=re.sub(
                r"\s+", " ", professional_summary or ""
            ).strip(),
        )
