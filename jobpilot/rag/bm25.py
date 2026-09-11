"""Tiny Okapi BM25 (no external dependency)."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Sequence

from ..taxonomy import canonical_skill

_TOKEN = re.compile(r"[a-z0-9+#]+(?:\.[a-z0-9]+)*")
STOP = {
    "and", "or", "the", "a", "an", "of", "to", "in", "for", "with", "on", "at", "by", "is", "are", "be",
    "as", "you", "we", "our", "your", "will", "this", "that", "from", "have", "has", "it", "etc", "using",
}


def tokenize(text: str) -> list[str]:
    toks = [t for t in _TOKEN.findall((text or "").lower()) if t not in STOP]
    return [canonical_skill(t).replace(" ", "_") for t in toks]


class BM25:
    def __init__(self, docs: Sequence[str], k1: float = 1.4, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs = [tokenize(d) for d in docs]
        self.tf = [Counter(d) for d in self.docs]
        self.lengths = [len(d) for d in self.docs]
        self.avgdl = (sum(self.lengths) / len(self.lengths)) if self.docs else 0.0
        df: Counter[str] = Counter()
        for d in self.docs:
            df.update(set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for tf, dl in zip(self.tf, self.lengths):
            s = 0.0
            for t in q:
                if t not in tf:
                    continue
                f = tf[t]
                s += self.idf.get(t, 0.0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            out.append(s)
        return out
