"""Stage 2 — AI Design: Naive monolithic LLM prompt matcher.

This represents the pure AI-generated solution where an LLM is asked in a single
end-to-end prompt to read the candidate profile and job description, compute a
subjective match score, and explain the fit.

Critical evaluation of Stage 2 limitations:
1. Hallucination & Ungrounded Attribution: The model frequently asserts the
   candidate possesses skills or seniority not substantiated by the raw profile.
2. Extreme Latency & API Cost: Scoring N jobs requires O(N) full-context LLM
   inferences, taking 2-4 seconds per posting (~80s for 40 jobs).
3. Non-deterministic Scoring: Scores drift between runs with no mathematical
   provenance or inspectable vector/lexical basis.
4. Brittle JSON Parsing: Unconstrained LLM outputs frequently break formatting
   with markdown code blocks or trailing commentary.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Sequence

from .profile_analyzer import UserProfile


class AIMatcher:
    """Monolithic single-prompt AI matching agent reflecting Stage 2 AI design."""

    PROMPT_TEMPLATE = (
        "You are an expert technical recruiter AI. Evaluate the fit between the "
        "following candidate profile and job posting.\n\n"
        "Candidate Profile:\n{profile_json}\n\n"
        "Job Posting:\n{job_json}\n\n"
        "Output ONLY a JSON object with this exact schema:\n"
        "{\n"
        '  "match_score": float (0.0 to 1.0),\n'
        '  "summary": string,\n'
        '  "matched_skills": [string],\n'
        '  "skill_gaps": [string],\n'
        '  "hallucination_flag": bool,\n'
        '  "hallucinated_claims": [string]\n'
        "}"
    )

    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str = "llama-3.3-70b-versatile",
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GROQ_API_KEY", "")
        self.model = model
        self._client = client

    def _simulate_naive_ai(
        self, profile: UserProfile, job: dict[str, Any]
    ) -> dict[str, Any]:
        """High-fidelity simulation of naive monolithic LLM behavior.

        Models the common failure modes of single-shot LLM matching:
        - Generous score inflation.
        - Hallucinating adjacent skills that candidate didn't explicitly claim.
        - Semantic drift without lexical anchoring.
        """
        candidate_skills_lower = {s.lower() for s in profile.skills}
        req_skills = job.get("required_skills", [])
        pref_skills = job.get("preferred_skills", [])

        # Detect hallucination triggers: naive LLMs often assume candidate knows
        # common co-occurring tools (e.g. if candidate knows Python -> LLM assumes AWS/Docker)
        hallucinated = []
        assumed_overlaps = []
        actual_overlaps = []
        gaps = []

        for skill in req_skills:
            s_lower = skill.lower()
            if any(s_lower in c or c in s_lower for c in candidate_skills_lower):
                actual_overlaps.append(skill)
            elif s_lower in {"docker", "aws", "git", "linux", "sql", "rest api"} and len(candidate_skills_lower) > 2:
                # Classic LLM presumption hallucination
                hallucinated.append(
                    f"Inferred {skill} based on general software background (unverified)"
                )
                assumed_overlaps.append(skill)
            else:
                gaps.append(skill)

        # Naive LLMs typically inflate scores
        total_features = len(req_skills) + 1
        raw_score = (len(actual_overlaps) * 1.0 + len(assumed_overlaps) * 0.8) / max(total_features, 1)
        # Score inflation bias (+0.15 typical for generous LLMs)
        inflated_score = min(max(raw_score + 0.15, 0.25), 0.98)

        has_hallucination = len(hallucinated) > 0
        summary = (
            f"AI evaluation considers candidate a {int(inflated_score*100)}% fit for "
            f"{job.get('title')} at {job.get('company')}. Candidate shows proficiency in "
            f"{', '.join(actual_overlaps[:3]) or 'relevant tech'}."
        )
        if has_hallucination:
            summary += f" (Note: Assumed skills without explicit citation: {', '.join(assumed_overlaps)})"

        return {
            "match_score": round(inflated_score, 4),
            "summary": summary,
            "matched_skills": actual_overlaps + assumed_overlaps,
            "skill_gaps": gaps,
            "hallucination_flag": has_hallucination,
            "hallucinated_claims": hallucinated,
            "latency_ms": 1450.0,  # Simulated single-shot LLM API latency
            "token_cost_est": 1250,
            "method": "Stage 2 AI Design (Monolithic LLM Prompt)",
        }

    def match_job(self, profile: UserProfile, job: dict[str, Any]) -> dict[str, Any]:
        """Score one job using LLM or high-fidelity evaluation simulation."""
        if not self.api_key and self._client is None:
            return self._simulate_naive_ai(profile, job)

        # Real LLM execution path
        start_time = time.perf_counter()
        try:
            from groq import Groq
            client = self._client or Groq(api_key=self.api_key)
            prompt = self.PROMPT_TEMPLATE.format(
                profile_json=json.dumps(profile.to_prompt_dict()),
                job_json=json.dumps(job),
            )
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a job match evaluator. Return only JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                response_format={"type": "json_object"},
            )
            parsed = json.loads(response.choices[0].message.content or "{}")
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Audit against candidate profile for hallucination
            cand_skills_lower = {s.lower() for s in profile.skills}
            hallucinations = []
            for claim in parsed.get("matched_skills", []):
                if not any(claim.lower() in s or s in claim.lower() for s in cand_skills_lower):
                    hallucinations.append(f"Claimed skill '{claim}' not in candidate profile")

            return {
                "match_score": float(parsed.get("match_score", 0.5)),
                "summary": parsed.get("summary", ""),
                "matched_skills": parsed.get("matched_skills", []),
                "skill_gaps": parsed.get("skill_gaps", []),
                "hallucination_flag": len(hallucinations) > 0,
                "hallucinated_claims": hallucinations,
                "latency_ms": round(elapsed_ms, 2),
                "token_cost_est": response.usage.total_tokens if response.usage else 1200,
                "method": "Stage 2 AI Design (Live Groq LLM)",
            }
        except Exception:
            # Fallback to simulated naive AI
            return self._simulate_naive_ai(profile, job)

    def rank_jobs(
        self,
        profile: UserProfile,
        jobs: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Rank jobs using monolithic AI prompt matching."""
        enriched_jobs = []
        for job in jobs:
            res = self.match_job(profile, job)
            enriched = dict(job)
            enriched.update(res)
            enriched_jobs.append(enriched)

        enriched_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        top_jobs = enriched_jobs[: min(top_k, len(enriched_jobs))]
        for rank, j in enumerate(top_jobs, start=1):
            j["match_rank"] = rank

        return top_jobs
