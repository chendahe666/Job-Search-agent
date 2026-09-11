"""Semantic-matcher specialist powered by Sentence Transformers.

The specialist embeds a structured candidate profile and each job document in
the same vector space, then delegates the comparison to cosine similarity. The
class accepts an injected encoder so unit tests can run without downloading a
large model.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np


class TextEncoder(Protocol):
    """Small interface implemented by SentenceTransformer and test doubles."""

    def encode(self, sentences: Sequence[str] | str, **kwargs: Any) -> np.ndarray:
        """Encode one or more texts into numeric vectors."""


class EmbeddingAgent:
    """Rank job postings by semantic similarity to a candidate profile."""

    DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        *,
        encoder: TextEncoder | None = None,
        local_files_only: bool = False,
    ) -> None:
        self.model_name = model_name
        self._encoder = encoder
        self.local_files_only = local_files_only
        self.backend = "Injected encoder" if encoder is not None else "MiniLM semantic embeddings"

    def _get_encoder(self) -> TextEncoder:
        """Load the Hugging Face model, falling back gracefully to TF-IDF."""

        if self._encoder is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._encoder = SentenceTransformer(self.model_name, local_files_only=self.local_files_only)
            except Exception:  # pragma: no cover - graceful fallback
                from sklearn.feature_extraction.text import TfidfVectorizer

                class TfidfFallbackEncoder:
                    def encode(
                        self, sentences: Sequence[str] | str, **_kwargs: Any
                    ) -> np.ndarray:
                        if isinstance(sentences, str):
                            sentences = [sentences]
                        vec = TfidfVectorizer(
                            ngram_range=(1, 2),
                            sublinear_tf=True,
                            token_pattern=r"(?u)\b[a-zA-Z0-9+#.]+\b",
                        )
                        return vec.fit_transform(sentences).toarray()

                self._encoder = TfidfFallbackEncoder()
                self.backend = "TF-IDF（模型不可用，已使用关键词替代）"
        return self._encoder

    @staticmethod
    def job_to_text(job: dict[str, Any]) -> str:
        """Convert a posting into one labeled document for the embedding model."""

        required = ", ".join(job.get("required_skills", []))
        preferred = ", ".join(job.get("preferred_skills", []))
        responsibilities = "; ".join(job.get("responsibilities", []))
        return " ".join(
            part
            for part in [
                f"Role: {job.get('title', '')}.",
                f"Company: {job.get('company', '')}.",
                f"Level: {job.get('experience_level', '')}.",
                f"Location and work mode: {job.get('location', '')}, "
                f"{job.get('work_mode', '')}.",
                f"Description: {job.get('description', '')}",
                f"Responsibilities: {responsibilities}.",
                f"Required skills: {required}.",
                f"Preferred skills: {preferred}.",
            ]
            if part
        )

    @staticmethod
    def _cosine_scores(profile: np.ndarray, jobs: np.ndarray) -> np.ndarray:
        """Compare vectors with scikit-learn, or NumPy in minimal environments.

        scikit-learn remains the production path declared in ``requirements.txt``.
        The equivalent NumPy calculation keeps injected-encoder tests and the
        local evidence demo usable on hosts where optional wheels are unavailable.
        """

        try:
            from sklearn.metrics.pairwise import cosine_similarity

            return cosine_similarity(profile, jobs).ravel()
        except ImportError:  # pragma: no cover - used only in constrained hosts
            profile_norm = np.linalg.norm(profile, axis=1, keepdims=True)
            job_norms = np.linalg.norm(jobs, axis=1, keepdims=True)
            denominator = profile_norm * job_norms.T
            denominator = np.where(denominator == 0, 1.0, denominator)
            return ((profile @ jobs.T) / denominator).ravel()

    def rank_jobs(
        self,
        profile_text: str,
        jobs: Sequence[dict[str, Any]],
        *,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Return copied postings sorted by cosine similarity, highest first.

        ``match_score`` is the raw cosine similarity clamped to [0, 1]. It is an
        alignment signal—not a probability of receiving an interview or offer.
        """

        if not profile_text.strip():
            raise ValueError("Profile text cannot be empty.")
        if not jobs:
            return []
        if top_k < 1:
            raise ValueError("top_k must be at least 1.")

        encoder = self._get_encoder()
        documents = [profile_text, *(self.job_to_text(job) for job in jobs)]
        embeddings = np.asarray(
            encoder.encode(
                documents,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=float,
        )
        if embeddings.ndim != 2 or embeddings.shape[0] != len(documents):
            raise ValueError("The embedding model returned an unexpected shape.")

        scores = self._cosine_scores(embeddings[:1], embeddings[1:])
        ranked_indices = np.argsort(-scores, kind="stable")[: min(top_k, len(jobs))]

        ranked_jobs: list[dict[str, Any]] = []
        for rank, index in enumerate(ranked_indices, start=1):
            enriched = dict(jobs[int(index)])
            enriched["match_score"] = float(np.clip(scores[int(index)], 0.0, 1.0))
            enriched["match_rank"] = rank
            ranked_jobs.append(enriched)
        return ranked_jobs
