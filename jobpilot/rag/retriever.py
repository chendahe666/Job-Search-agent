"""Hybrid retrieval (BM25 + dense vectors, fused with Reciprocal Rank Fusion)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from ..storage.db import Database
from ..taxonomy import skill_variants
from .bm25 import BM25
from .chunker import Chunk, chunk_profile
from .embeddings import Embedder


@dataclass
class Hit:
    chunk: Chunk
    score: float
    dense: float
    lexical: float


class HybridIndex:
    def __init__(self, chunks: Sequence[Chunk], embedder: Embedder, vectors: Optional[np.ndarray] = None) -> None:
        self.chunks = list(chunks)
        self.embedder = embedder
        self.bm25 = BM25([c.text + " " + c.label for c in self.chunks])
        if vectors is None and self.chunks:
            vectors = embedder.embed_documents([f"{c.label}: {c.text}" for c in self.chunks])
        self.vectors = vectors if vectors is not None else np.zeros((0, 1), dtype=np.float32)

    @classmethod
    def for_profile(cls, profile, embedder: Embedder, db: Optional[Database] = None, owner: str = "me") -> "HybridIndex":
        chunks = chunk_profile(profile)
        vectors = None
        if db is not None:
            stored = db.load_chunks("resume", owner)
            ids = [c.id for c in chunks]
            if stored and [s["id"] for s in stored] == ids and all(
                s["embed_model"] == embedder.name and s["text"] == c.text for s, c in zip(stored, chunks)
            ):
                vectors = np.vstack([s["embedding"] for s in stored])
        index = cls(chunks, embedder, vectors)
        if db is not None and vectors is None and chunks:
            db.replace_chunks(
                "resume", owner,
                [(c.id, c.text, {"label": c.label, **c.meta}, index.vectors[i], embedder.name) for i, c in enumerate(chunks)],
            )
        return index

    def search(self, query: str, k: int = 3, terms: Sequence[str] = ()) -> list[Hit]:
        return self.search_many([(query, terms)], k=k)[0]

    def search_many(self, queries: Sequence[tuple[str, Sequence[str]]], k: int = 3, dense: bool = True) -> list[list[Hit]]:
        """Batch retrieval: one embedding call for all queries (important for API quota)."""
        if not self.chunks or not queries:
            return [[] for _ in queries]
        expanded = [q + " " + " ".join(v for t in terms for v in skill_variants(t)) for q, terms in queries]
        qvs = self.embedder.embed_queries(expanded) if dense and self.vectors.shape[0] == len(self.chunks) else None
        return [self._rank(e, qvs[i] if qvs is not None else None, k) for i, e in enumerate(expanded)]

    def _rank(self, expanded: str, qv, k: int) -> list[Hit]:
        lex = np.asarray(self.bm25.scores(expanded), dtype=float)
        dense = self.vectors @ qv if qv is not None else np.zeros(len(self.chunks))
        rank_lex = {int(i): r for r, i in enumerate(np.argsort(-lex, kind="stable"), start=1)}
        rank_dense = {int(i): r for r, i in enumerate(np.argsort(-dense, kind="stable"), start=1)}
        fused = []
        for i in range(len(self.chunks)):
            rrf = 1 / (60 + rank_lex[i]) + 1 / (60 + rank_dense[i])
            if lex[i] <= 0:
                rrf *= 0.8  # no lexical overlap at all → mild penalty
            fused.append((rrf, i))
        fused.sort(reverse=True)
        return [Hit(self.chunks[i], s, float(dense[i]), float(lex[i])) for s, i in fused[:k]]

    def get(self, chunk_id: str) -> Optional[Chunk]:
        return next((c for c in self.chunks if c.id == chunk_id), None)
