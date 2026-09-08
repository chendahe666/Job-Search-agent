"""Stage 3 — Human-AI Co-Design: Hybrid Retrieval Engine (BM25 + Dense Embeddings).

Combines:
1. BM25 Lexical Search: Guarantees exact matches for specific programming languages,
   frameworks, and tools (e.g., 'Kubernetes', 'PyTorch', 'Go').
2. Dense Semantic Embeddings (Sentence Transformers): Captures abstract domain fit,
   career level, and conceptual alignment even without exact keyword overlap.
3. Reciprocal Rank Fusion (RRF) & Weighted Score Normalization: Merges lexical and
   semantic signals into a robust, high-recall ranking.
"""

from __future__ import annotations

import re
import time
from typing import Any, Sequence

import numpy as np

from .embedding_agent import EmbeddingAgent
from .profile_analyzer import UserProfile


class HybridMatcher:
    """Production-grade hybrid retriever combining BM25 and dense embeddings."""

    def __init__(
        self,
        dense_agent: EmbeddingAgent | None = None,
        *,
        dense_weight: float = 0.60,
        lexical_weight: float = 0.40,
    ) -> None:
        self.dense_agent = dense_agent or EmbeddingAgent()
        self.dense_weight = dense_weight
        self.lexical_weight = lexical_weight

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Tokenize text into cleaned lowercase tokens for BM25."""
        return [
            token
            for token in re.findall(r"[a-z0-9+#.]+", text.lower())
            if len(token) > 1 or token in {"c", "r"}
        ]

    def _build_bm25_corpus(self, jobs: Sequence[dict[str, Any]]) -> list[list[str]]:
        """Extract tokenized representation for each job."""
        corpus = []
        for job in jobs:
            text = EmbeddingAgent.job_to_text(job)
            # Extra weighting for required skills
            skills_text = " ".join(job.get("required_skills", []) * 3)
            combined = f"{text} {skills_text}"
            corpus.append(self._tokenize(combined))
        return corpus

    def rank_jobs(
        self,
        profile: UserProfile,
        jobs: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Execute two-stage hybrid retrieval with Reciprocal Rank Fusion (RRF)."""
        if not jobs:
            return []

        start_time = time.perf_counter()
        profile_text = profile.to_embedding_text()
        query_tokens = self._tokenize(
            f"{' '.join(profile.skills * 2)} {' '.join(profile.target_roles)} {profile.professional_summary}"
        )

        # 1. Dense Semantic Scoring
        dense_results = self.dense_agent.rank_jobs(
            profile_text, jobs, top_k=len(jobs)
        )
        dense_scores_by_id = {j["id"]: j["match_score"] for j in dense_results}
        dense_rank_by_id = {j["id"]: idx for idx, j in enumerate(dense_results, 1)}

        # 2. BM25 Lexical Scoring
        try:
            from rank_bm25 import BM25Okapi

            tokenized_corpus = self._build_bm25_corpus(jobs)
            bm25 = BM25Okapi(tokenized_corpus)
            bm25_scores = bm25.get_scores(query_tokens)
            # Min-Max normalize BM25 scores to [0, 1]
            max_s = float(np.max(bm25_scores)) if len(bm25_scores) else 1.0
            min_s = float(np.min(bm25_scores)) if len(bm25_scores) else 0.0
            range_s = max(max_s - min_s, 1e-6)
            norm_bm25 = [(s - min_s) / range_s for s in bm25_scores]
        except Exception:
            # Fallback: token overlap ratio if rank_bm25 unavailable
            norm_bm25 = []
            query_set = set(query_tokens)
            for j in jobs:
                j_tokens = set(self._tokenize(EmbeddingAgent.job_to_text(j)))
                overlap = len(query_set.intersection(j_tokens)) / max(len(query_set), 1)
                norm_bm25.append(overlap)

        bm25_scores_by_id = {jobs[i]["id"]: norm_bm25[i] for i in range(len(jobs))}
        bm25_sorted_ids = [
            jobs[i]["id"]
            for i in np.argsort(-np.array(norm_bm25), kind="stable")
        ]
        bm25_rank_by_id = {
            job_id: idx for idx, job_id in enumerate(bm25_sorted_ids, 1)
        }

        # 3. Reciprocal Rank Fusion (RRF) & Weighted Score Combination
        # RRF formula: Score(d) = sum(1 / (k + rank)) with standard k = 60
        k_rrf = 60.0
        hybrid_jobs: list[dict[str, Any]] = []

        for job in jobs:
            j_id = job["id"]
            dense_s = dense_scores_by_id.get(j_id, 0.0)
            bm25_s = bm25_scores_by_id.get(j_id, 0.0)
            dense_r = dense_rank_by_id.get(j_id, len(jobs))
            bm25_r = bm25_rank_by_id.get(j_id, len(jobs))

            # Weighted normalized score
            combined_score = (self.dense_weight * dense_s) + (
                self.lexical_weight * bm25_s
            )

            # RRF score
            rrf_score = (1.0 / (k_rrf + dense_r)) + (1.0 / (k_rrf + bm25_r))

            enriched = dict(job)
            enriched["match_score"] = round(float(combined_score), 4)
            enriched["dense_score"] = round(float(dense_s), 4)
            enriched["bm25_score"] = round(float(bm25_s), 4)
            enriched["rrf_score"] = round(float(rrf_score), 6)
            enriched["method"] = "Stage 3 Co-Design (Hybrid BM25 + Dense RRF)"
            hybrid_jobs.append(enriched)

        # Sort descending by hybrid combined score
        hybrid_jobs.sort(key=lambda j: j["match_score"], reverse=True)
        top_results = hybrid_jobs[: min(top_k, len(hybrid_jobs))]

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        for rank, j in enumerate(top_results, start=1):
            j["match_rank"] = rank
            j["latency_ms"] = round(elapsed_ms / len(jobs), 3)

        return top_results
