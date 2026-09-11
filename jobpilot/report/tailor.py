"""Evidence-constrained application tailoring with post-generation fact checks."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from ..extract.heuristics import find_terms
from ..llm.gemini import GeminiClient, GeminiError
from ..llm.prompts import TAILOR_PROMPT, TAILOR_SYSTEM, TailorDTO
from ..rag.retriever import HybridIndex
from ..schemas import CandidateProfile, EvidenceStatus, MatchResult, RequirementKind
from ..taxonomy import canonical_skill


@dataclass
class CheckedBullet:
    text: str
    chunk_ids: list[str]
    verified: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class TailorResult:
    bullets: list[CheckedBullet]
    pitch: str
    keywords: list[str]
    method: str


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*(?:\.\d+)?", text)}


def check_bullet(text: str, chunk_ids: list[str], index: HybridIndex) -> CheckedBullet:
    chunks = [index.get(c) for c in chunk_ids]
    chunks = [c for c in chunks if c is not None]
    problems = []
    if not chunks:
        return CheckedBullet(text, chunk_ids, False, ["no valid evidence chunk cited"])
    source = " ".join(c.text + " " + c.label for c in chunks)
    extra_numbers = _numbers(text) - _numbers(source)
    if extra_numbers:
        problems.append("numbers not in evidence: " + ", ".join(sorted(extra_numbers)))
    src_terms = {canonical_skill(t) for t in find_terms(source)}
    extra_terms = [t for t in find_terms(text) if canonical_skill(t) not in src_terms]
    if extra_terms:
        problems.append("skills not in evidence: " + ", ".join(extra_terms))
    return CheckedBullet(text, [c.id for c in chunks], not problems, problems)


def tailor_application(match: MatchResult, index: HybridIndex, profile: CandidateProfile, llm: Optional[GeminiClient] = None,
                       lang: str = "en") -> TailorResult:
    supported = [e for e in match.evidence if e.status in (EvidenceStatus.MET, EvidenceStatus.PARTIAL) and e.chunk_id]
    supported.sort(key=lambda e: (e.kind != RequirementKind.REQUIRED, e.status != EvidenceStatus.MET))
    keywords = list(dict.fromkeys(
        t for e in supported if e.status == EvidenceStatus.MET
        for r in match.job.requirements if r.id == e.requirement_id for t in r.terms
    ))[:12]
    if llm is not None and supported:
        chunk_ids = list(dict.fromkeys(e.chunk_id for e in supported))[:12]
        chunks_txt = "\n".join(f'<chunk id="{c.id}" source="{c.label}">{c.text}</chunk>' for c in (index.get(i) for i in chunk_ids) if c)
        reqs = "; ".join(r.text for r in match.job.requirements if r.kind == RequirementKind.REQUIRED)[:1500]
        try:
            dto, _ = llm.generate_json(
                TAILOR_PROMPT.format(title=match.job.title, company=match.job.company, requirements=reqs, chunks=chunks_txt,
                                     language="Chinese" if lang == "zh" else "English"),
                TailorDTO, system=TAILOR_SYSTEM, temperature=0.3,
            )
            bullets = [check_bullet(b.text, b.chunk_ids, index) for b in dto.bullets[:6]]
            kw = [k for k in dto.keywords_to_mirror if canonical_skill(k) in {canonical_skill(x) for x in keywords} or k in keywords] or keywords
            return TailorResult(bullets, dto.pitch, kw, "llm+fact-checked")
        except GeminiError:
            pass
    # Offline: reorder the candidate's own verbatim evidence (never fabricate).
    seen, bullets = set(), []
    for e in supported:
        chunk = index.get(e.chunk_id)
        if chunk and chunk.id not in seen and chunk.meta.get("section") in ("experience", "project", "raw"):
            seen.add(chunk.id)
            bullets.append(CheckedBullet(chunk.text, [chunk.id], True, []))
    met = [e for e in supported if e.status == EvidenceStatus.MET]
    if lang == "zh":
        pitch = (f"我对 {match.job.company} 的 {match.job.title} 职位很感兴趣。我的经历与该职位的 {len(met)} 项要求直接相关"
                 + (f"，包括 {', '.join(keywords[:3])}" if keywords else "") + "。期待有机会进一步交流。")
    else:
        pitch = (f"I'm excited about the {match.job.title} role at {match.job.company}. My background directly covers {len(met)} of the "
                 f"posted requirements" + (f", including {', '.join(keywords[:3])}" if keywords else "") + ". I'd welcome the chance to talk.")
    return TailorResult(bullets[:5], pitch, keywords, "offline-verbatim")
