"""Embedding back-ends: Gemini (cached in SQLite) with a zero-dependency local fallback."""

from __future__ import annotations

import hashlib
import re
from typing import Optional, Protocol, Sequence

import numpy as np

from ..llm.gemini import GeminiClient, GeminiError
from ..storage.db import Database


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray: ...

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray: ...


def _l2(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


class HashingEmbedder:
    """Deterministic word + char-trigram hashing vectors. Not semantic like a neural
    model, but robust, instant, offline, and good enough as a fallback."""

    def __init__(self, dim: int = 1024) -> None:
        self.dim = dim
        self.name = f"hashing-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        tokens = re.findall(r"[a-z0-9+#.]+", (text or "").lower())
        feats = list(tokens)
        feats += [f"{a}_{b}" for a, b in zip(tokens, tokens[1:])]
        for tok in tokens:
            padded = f"#{tok}#"
            feats += [padded[i:i + 3] for i in range(max(1, len(padded) - 2))]
        for f in feats:
            h = int.from_bytes(hashlib.md5(f.encode()).digest()[:4], "little")
            v[h % self.dim] += 1.0 if (h >> 31) & 1 else -1.0
        return np.sign(v) * np.log1p(np.abs(v))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _l2(np.vstack([self._vec(t) for t in texts]))

    embed_queries = embed_documents


class GeminiEmbedder:
    def __init__(self, client: GeminiClient, db: Optional[Database] = None, dim: int = 768,
                 fallback: Optional[HashingEmbedder] = None) -> None:
        self.client = client
        self.db = db
        self.dim = dim
        self.name = f"{client.embed_model}-{dim}"
        self.fallback = fallback
        self.degraded = False

    def _embed(self, texts: Sequence[str], task: str) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        keys = [hashlib.sha1(f"{task}|{t}".encode()).hexdigest() for t in texts]
        cached = self.db.cache_get_vectors(keys, self.name) if self.db else {}
        missing = [i for i, k in enumerate(keys) if k not in cached]
        if missing:
            vectors = self.client.embed([texts[i] for i in missing], task_type=task, dimensions=self.dim)
            new = {keys[i]: np.asarray(vec, dtype=np.float32) for i, vec in zip(missing, vectors)}
            cached.update(new)
            if self.db:
                self.db.cache_put_vectors(new, self.name)
        return _l2(np.vstack([cached[k] for k in keys]))

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_DOCUMENT")

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._embed(texts, "RETRIEVAL_QUERY")


class ResilientEmbedder:
    """Tries the primary embedder; on any API error permanently switches to the fallback
    for the rest of the session (so vectors stay in one space)."""

    def __init__(self, primary: Optional[Embedder], fallback: Embedder) -> None:
        self.primary = primary
        self.fallback = fallback
        self.active: Embedder = primary or fallback
        self.error: str = ""

    @property
    def name(self) -> str:
        return self.active.name

    def _call(self, method: str, texts: Sequence[str]) -> np.ndarray:
        try:
            return getattr(self.active, method)(texts)
        except (GeminiError, ValueError, KeyError) as exc:
            if self.active is self.fallback:
                raise
            self.error = str(exc)
            self.active = self.fallback
            return getattr(self.active, method)(texts)

    def embed_documents(self, texts: Sequence[str]) -> np.ndarray:
        return self._call("embed_documents", texts)

    def embed_queries(self, texts: Sequence[str]) -> np.ndarray:
        return self._call("embed_queries", texts)
