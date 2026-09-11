"""RAG evidence: map each job requirement to verbatim resume evidence.

retrieve (hybrid BM25+dense over resume chunks) → judge (LLM or lexical) →
verify (quote must exist in the cited chunk, else downgraded to UNVERIFIED).
"""

from __future__ import annotations

import re
from typing import Optional

from ..extract.heuristics import infer_degree
from ..llm.gemini import GeminiClient, GeminiError
from ..llm.prompts import EVIDENCE_PROMPT, EVIDENCE_SYSTEM, EvidenceJudgments
from ..rag.retriever import Hit, HybridIndex
from ..schemas import (
    DEGREE_RANK, CandidateProfile, EvidenceItem, EvidenceStatus, JobPosting, Requirement, RequirementCategory,
)
from ..taxonomy import RELATED_SKILLS, canonical_skill, skill_variants, term_in_text
from ..textutils import quote_in_source, split_sentences

GENERIC_WORDS = {
    "experience", "with", "and", "the", "for", "strong", "solid", "knowledge", "understanding", "ability", "skills",
    "skill", "years", "year", "professional", "proficiency", "proficient", "familiarity", "familiar", "working",
    "excellent", "good", "great", "plus", "preferred", "required", "including", "such", "using", "use", "tools",
    "related", "relevant", "field", "similar", "equivalent", "demonstrated", "proven", "track", "record", "hands",
    "least", "minimum", "one", "more", "other", "etc", "you", "your", "our", "have", "has", "are", "who", "can",
}
SECTION_PRIORITY = {"experience": 0, "project": 1, "raw": 2, "summary": 3, "certs": 3, "education": 4, "skills": 4}
RANK = {EvidenceStatus.GAP: 0, EvidenceStatus.UNVERIFIED: 0, EvidenceStatus.PARTIAL: 1, EvidenceStatus.MET: 2}


class EvidenceMatcher:
    def __init__(self, index: HybridIndex, profile: CandidateProfile, llm: Optional[GeminiClient] = None,
                 use_llm: bool = True) -> None:
        self.index = index
        self.profile = profile
        self.llm = llm
        self.use_llm = use_llm and llm is not None
        self.last_error = ""
        self.downgraded = 0

    # ------------------------------------------------------------------ #
    def match(self, job: JobPosting, *, dense: bool = True, allow_llm: bool = True) -> list[EvidenceItem]:
        items: dict[str, EvidenceItem] = {}
        needs_judgment: list[tuple[Requirement, list[Hit]]] = []
        retrievable = [r for r in job.requirements if r.category not in (RequirementCategory.AUTHORIZATION, RequirementCategory.EDUCATION)]
        all_hits = dict(zip([r.id for r in retrievable], self.index.search_many([(r.text, r.terms) for r in retrievable], k=3, dense=dense)))
        for req in job.requirements:
            base = EvidenceItem(requirement_id=req.id, requirement_text=req.text, kind=req.kind, category=req.category)
            if req.category == RequirementCategory.AUTHORIZATION:
                items[req.id] = base.model_copy(update={"status": EvidenceStatus.NOT_APPLICABLE, "method": "hard_filter",
                                                        "rationale": "Handled by work-authorization hard filter"})
                continue
            if req.category == RequirementCategory.EDUCATION:
                items[req.id] = self._education(req, base)
                continue
            years_item = self._years(req, base) if (req.min_years or req.category == RequirementCategory.EXPERIENCE) else None
            if years_item and not req.terms:
                items[req.id] = years_item
                continue
            hits = all_hits.get(req.id, [])
            lexical = self._lexical(req, hits, base)
            if years_item:
                lexical = _combine(years_item, lexical)
            items[req.id] = lexical
            needs_judgment.append((req, hits))

        if self.use_llm and allow_llm and needs_judgment:
            try:
                self._llm_judge(needs_judgment, items)
            except GeminiError as exc:
                self.last_error = str(exc)[:200]
        return [items[r.id] for r in job.requirements if r.id in items]

    # ------------------------------------------------------------------ #
    def _education(self, req: Requirement, base: EvidenceItem) -> EvidenceItem:
        needed = infer_degree(req.text)
        have = self.profile.highest_degree
        if needed is None:
            return base.model_copy(update={"status": EvidenceStatus.NOT_APPLICABLE, "method": "rule",
                                           "rationale": "No specific degree level stated"})
        label = f"Education · {self.profile.education[0].school}" if self.profile.education else "Profile"
        if DEGREE_RANK[have] >= DEGREE_RANK[needed]:
            status, why = EvidenceStatus.MET, f"{have.value} ≥ {needed.value}"
        elif DEGREE_RANK[have] == DEGREE_RANK[needed] - 1 and re.search(r"equivalent|or related experience", req.text, re.I):
            status, why = EvidenceStatus.PARTIAL, f"{have.value} + equivalent experience clause"
        else:
            status, why = EvidenceStatus.GAP, f"has {have.value}, needs {needed.value}"
        edu_chunk = next((c for c in self.index.chunks if c.id.startswith("EDU")), None)
        return base.model_copy(update={
            "status": status, "method": "rule", "rationale": why, "chunk_id": edu_chunk.id if edu_chunk and status != EvidenceStatus.GAP else "",
            "quote": edu_chunk.text if edu_chunk and status != EvidenceStatus.GAP else "", "source_label": label,
        })

    def _years(self, req: Requirement, base: EvidenceItem) -> EvidenceItem:
        from ..textutils import parse_min_years
        need = req.min_years if req.min_years is not None else parse_min_years(req.text)
        have = self.profile.years_experience
        if need is None:
            return base.model_copy(update={"status": EvidenceStatus.PARTIAL, "method": "rule", "rationale": "Experience depth not quantified"})
        if have >= need:
            status = EvidenceStatus.MET
        elif have >= need - 1:
            status = EvidenceStatus.PARTIAL
        else:
            status = EvidenceStatus.GAP
        return base.model_copy(update={"status": status, "method": "rule", "source_label": "Profile",
                                       "quote": f"{have:g} years of experience" if status != EvidenceStatus.GAP else "",
                                       "rationale": f"needs {need:g}y, profile shows {have:g}y"})

    def _lexical(self, req: Requirement, hits: list[Hit], base: EvidenceItem) -> EvidenceItem:
        terms = [canonical_skill(t) for t in req.terms]
        if not terms:
            return self._token_overlap(req, hits, base)
        # Search all chunks for literal evidence (retrieval hits first).
        hit_ids = [h.chunk.id for h in hits]
        ordered = sorted(
            self.index.chunks,
            key=lambda c: (SECTION_PRIORITY.get(c.meta.get("section", ""), 5), hit_ids.index(c.id) if c.id in hit_ids else 99),
        )
        met_terms, partial_terms = {}, {}
        for term in terms:
            for chunk in ordered:
                v = next((v for v in skill_variants(term) if term_in_text(v, chunk.text)), None)
                if v:
                    met_terms[term] = (chunk, v)
                    break
            if term not in met_terms:
                for rel in RELATED_SKILLS.get(term, []):
                    chunk = next((c for c in ordered for v in skill_variants(rel) if term_in_text(v, c.text)), None)
                    if chunk:
                        partial_terms[term] = (chunk, rel)
                        break
        any_of = bool(re.search(r"\b(or|either|one of|such as|e\.g\.|like)\b|/", req.text.lower()))
        if met_terms and (len(met_terms) == len(terms) or any_of):
            status = EvidenceStatus.MET
        elif met_terms or partial_terms:
            status = EvidenceStatus.PARTIAL
        else:
            return base.model_copy(update={"status": EvidenceStatus.GAP, "method": "lexical",
                                           "rationale": "No resume evidence for " + ", ".join(terms)})
        chunk, variant = next(iter(met_terms.values())) if met_terms else next(iter(partial_terms.values()))
        sentence = next((s for s in split_sentences(chunk.text) if term_in_text(variant, s)), chunk.text)
        why = ("mentions " + ", ".join(met_terms)) if met_terms else ("related: " + ", ".join(f"{k}≈{v[1]}" for k, v in partial_terms.items()))
        return base.model_copy(update={"status": status, "quote": sentence[:300], "chunk_id": chunk.id,
                                       "source_label": chunk.label, "method": "lexical", "rationale": why})

    def _token_overlap(self, req: Requirement, hits: list[Hit], base: EvidenceItem) -> EvidenceItem:
        """Offline judgment for requirements without known skill terms (e.g. 'Experience with Cloud Security')."""
        content = [t for t in re.findall(r"[a-z0-9+#]+", req.text.lower()) if t not in GENERIC_WORDS and len(t) > 2]
        if not content:
            return base.model_copy(update={"status": EvidenceStatus.NOT_APPLICABLE, "method": "lexical",
                                           "rationale": "Generic requirement — needs LLM or human judgment"})
        best, best_share = None, 0.0
        for chunk in [h.chunk for h in hits] + list(self.index.chunks):
            low = chunk.text.lower()
            share = sum(1 for t in content if re.search(rf"(?<![a-z0-9]){re.escape(t)}", low)) / len(content)
            if share > best_share:
                best, best_share = chunk, share
        if best is None or best_share < 0.5:
            return base.model_copy(update={"status": EvidenceStatus.GAP, "method": "lexical",
                                           "rationale": "No resume text overlaps this requirement"})
        status = EvidenceStatus.MET if best_share == 1.0 and len(content) >= 2 else EvidenceStatus.PARTIAL
        sentence = max(split_sentences(best.text) or [best.text], key=lambda s: sum(t in s.lower() for t in content))
        return base.model_copy(update={"status": status, "quote": sentence[:300], "chunk_id": best.id, "source_label": best.label,
                                       "method": "lexical", "rationale": f"{best_share:.0%} of key words found"})

    def _llm_judge(self, pending: list[tuple[Requirement, list[Hit]]], items: dict[str, EvidenceItem]) -> None:
        blocks = []
        for req, hits in pending[:20]:
            lines = [f"[{req.id}] ({req.kind.value}) {req.text}"]
            for h in hits:
                lines.append(f"    <chunk id=\"{h.chunk.id}\" source=\"{h.chunk.label}\">{h.chunk.text}</chunk>")
            blocks.append("\n".join(lines))
        prompt = EVIDENCE_PROMPT.format(years=f"{self.profile.years_experience:g}", degree=self.profile.highest_degree.value,
                                        blocks="\n\n".join(blocks))
        dto, _ = self.llm.generate_json(prompt, EvidenceJudgments, system=EVIDENCE_SYSTEM)
        allowed = {req.id: {h.chunk.id for h in hits} for req, hits in pending}
        for j in dto.items:
            if j.requirement_id not in items or j.requirement_id not in allowed:
                continue
            current = items[j.requirement_id]
            status = {"met": EvidenceStatus.MET, "partial": EvidenceStatus.PARTIAL, "gap": EvidenceStatus.GAP}.get(j.status.lower().strip())
            if status is None:
                continue
            if status == EvidenceStatus.GAP:
                if current.status == EvidenceStatus.MET and current.method == "lexical":
                    # literal skill mention exists but the LLM judged depth insufficient
                    items[j.requirement_id] = current.model_copy(update={"status": EvidenceStatus.PARTIAL, "method": "llm+lexical",
                                                                        "rationale": j.rationale or current.rationale})
                elif current.method != "rule":
                    items[j.requirement_id] = current.model_copy(update={"status": EvidenceStatus.GAP, "quote": "", "chunk_id": "",
                                                                        "method": "llm", "rationale": j.rationale})
                continue
            chunk = self.index.get(j.chunk_id)
            if chunk is None or j.chunk_id not in allowed[j.requirement_id] or not quote_in_source(j.quote, chunk.text):
                self.downgraded += 1
                if RANK.get(current.status, 0) > 0 and current.method in ("lexical", "rule", "llm+lexical"):
                    continue  # keep verifiable lexical evidence
                items[j.requirement_id] = current.model_copy(update={
                    "status": EvidenceStatus.UNVERIFIED, "method": "llm", "quote": j.quote[:300], "chunk_id": j.chunk_id,
                    "rationale": "LLM quote not found in resume — not counted",
                })
                continue
            if current.method == "rule" and RANK.get(current.status, 0) < RANK[status]:
                status = current.status  # years rule caps the LLM
            items[j.requirement_id] = current.model_copy(update={
                "status": status, "quote": j.quote[:300], "chunk_id": chunk.id, "source_label": chunk.label,
                "method": "llm+verified", "rationale": j.rationale,
            })


def _combine(years: EvidenceItem, skill: EvidenceItem) -> EvidenceItem:
    if skill.status == EvidenceStatus.NOT_APPLICABLE:
        return years
    worst = min(years, skill, key=lambda it: RANK.get(it.status, 0))
    best = max(years, skill, key=lambda it: RANK.get(it.status, 0))
    status = worst.status if RANK.get(worst.status, 0) == RANK.get(best.status, 0) else EvidenceStatus.PARTIAL
    if RANK.get(best.status, 0) == 0:
        status = EvidenceStatus.GAP
    return skill.model_copy(update={"status": status, "rationale": f"{skill.rationale}; {years.rationale}", "method": "rule+lexical"})
