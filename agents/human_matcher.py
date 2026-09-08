"""Stage 1 — Human Design: Rule-based, exact keyword and regex matcher.

This represents the original baseline before AI intervention. It relies on
deterministic lexical tokenization, case-insensitive keyword sets, and
explicit Jaccard/overlap heuristics.

Limitations observed in practice:
- High false-negative rate due to vocabulary mismatch (e.g., 'ML' vs 'Machine Learning').
- Inability to interpret semantic similarity between related frameworks.
- Zero awareness of domain context or implicit project experience.
"""

from __future__ import annotations

import re
import time
from typing import Any, Sequence

from .profile_analyzer import UserProfile


class HumanMatcher:
    """Deterministic, rule-based job matcher reflecting pure human heuristic design."""

    @staticmethod
    def normalize_token(token: str) -> str:
        """Normalize a skill token for lexical comparison."""
        cleaned = re.sub(r"[^a-z0-9+#.]", "", token.casefold().strip())
        # Basic human alias mapping
        aliases = {
            "js": "javascript",
            "ts": "typescript",
            "py": "python",
            "sklearn": "scikitlearn",
            "k8s": "kubernetes",
            "ml": "machinelearning",
            "ai": "artificialintelligence",
            "dl": "deeplearning",
        }
        return aliases.get(cleaned, cleaned)

    @classmethod
    def extract_tokens(cls, text_or_list: str | Sequence[str]) -> set[str]:
        """Convert comma/space separated text or sequence into normalized token set."""
        if isinstance(text_or_list, str):
            raw_tokens = re.split(r"[,;\s/|]+", text_or_list)
        else:
            raw_tokens = []
            for item in text_or_list:
                raw_tokens.extend(re.split(r"[,;\s/|]+", str(item)))

        return {cls.normalize_token(t) for t in raw_tokens if cls.normalize_token(t)}

    def match_job(self, profile: UserProfile, job: dict[str, Any]) -> dict[str, Any]:
        """Compute deterministic lexical match metrics for a single job."""
        candidate_skills = {self.normalize_token(s) for s in profile.skills}
        job_required = {self.normalize_token(s) for s in job.get("required_skills", [])}
        job_preferred = {self.normalize_token(s) for s in job.get("preferred_skills", [])}

        # Matched and missing required skills
        matched_required = candidate_skills.intersection(job_required)
        missing_required = job_required.difference(candidate_skills)
        matched_preferred = candidate_skills.intersection(job_preferred)

        # Skill coverage calculation
        if job_required:
            required_recall = len(matched_required) / len(job_required)
        else:
            required_recall = 0.5

        # Jaccard similarity over all technical tokens
        all_job_skills = job_required.union(job_preferred)
        union_skills = candidate_skills.union(all_job_skills)
        jaccard = (
            len(candidate_skills.intersection(all_job_skills)) / len(union_skills)
            if union_skills
            else 0.0
        )

        # Title match boost (heuristic human rule)
        title_tokens = self.extract_tokens(job.get("title", ""))
        target_tokens = set()
        for role in profile.target_roles:
            target_tokens.update(self.extract_tokens(role))

        title_overlap = len(title_tokens.intersection(target_tokens)) > 0
        title_boost = 0.15 if title_overlap else 0.0

        # Weighted heuristic score: 65% required recall + 20% Jaccard + 15% title match
        raw_score = (0.65 * required_recall) + (0.20 * jaccard) + title_boost
        final_score = min(max(raw_score, 0.0), 1.0)

        # Map back original skill names for display
        norm_to_orig_job = {self.normalize_token(s): s for s in job.get("required_skills", [])}
        norm_to_orig_pref = {self.normalize_token(s): s for s in job.get("preferred_skills", [])}

        display_matched = [
            norm_to_orig_job.get(m, m) for m in matched_required
        ] + [
            norm_to_orig_pref.get(m, m) for m in matched_preferred
        ]
        display_gaps = [norm_to_orig_job.get(g, g) for g in missing_required]

        return {
            "match_score": round(final_score, 4),
            "required_recall": round(required_recall, 4),
            "jaccard_similarity": round(jaccard, 4),
            "matched_skills": display_matched,
            "skill_gaps": display_gaps,
            "title_matched": title_overlap,
            "method": "Human Baseline (Rule/Lexical Jaccard)",
        }

    def rank_jobs(
        self,
        profile: UserProfile,
        jobs: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Rank job postings using human-engineered rules and sort by score."""
        start_time = time.perf_counter()
        enriched_jobs = []

        for job in jobs:
            match_data = self.match_job(profile, job)
            enriched = dict(job)
            enriched.update(match_data)
            enriched_jobs.append(enriched)

        # Stable sort descending by match_score
        enriched_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        top_jobs = enriched_jobs[: min(top_k, len(enriched_jobs))]

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        for rank, j in enumerate(top_jobs, start=1):
            j["match_rank"] = rank
            j["latency_ms"] = round(elapsed_ms / len(jobs), 3)

        return top_jobs
