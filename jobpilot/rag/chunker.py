"""Turn a candidate profile into retrievable, citable evidence chunks."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..schemas import CandidateProfile
from ..textutils import norm_ws, split_sentences


@dataclass
class Chunk:
    id: str
    text: str
    label: str
    meta: dict = field(default_factory=dict)


def chunk_profile(profile: CandidateProfile) -> list[Chunk]:
    chunks: list[Chunk] = []
    for i, exp in enumerate(profile.experiences, start=1):
        header = f"{exp.title} @ {exp.company}".strip(" @")
        dates = f"{exp.start}–{exp.end}".strip("–")
        label = f"{header} ({dates})" if dates else header
        bullets = [b for b in exp.bullets if norm_ws(b)]
        if not bullets:
            chunks.append(Chunk(f"EXP{i}", label, label, {"section": "experience"}))
        for j, bullet in enumerate(bullets, start=1):
            chunks.append(Chunk(f"EXP{i}.{j}", norm_ws(bullet), label, {"section": "experience", "role": header}))
    for i, proj in enumerate(profile.projects, start=1):
        tech = f" Technologies: {', '.join(proj.technologies)}." if proj.technologies else ""
        text = norm_ws(f"{proj.name}: {proj.description}{tech}")
        chunks.append(Chunk(f"PRJ{i}", text, f"Project · {proj.name}", {"section": "project"}))
    for i, edu in enumerate(profile.education, start=1):
        text = norm_ws(f"{edu.degree.value.title()} {edu.field} — {edu.school} {edu.graduation}")
        chunks.append(Chunk(f"EDU{i}", text, f"Education · {edu.school}", {"section": "education"}))
    if profile.skills:
        chunks.append(Chunk("SKILLS", "Skills: " + ", ".join(profile.skills), "Skills section", {"section": "skills"}))
    if profile.certifications:
        chunks.append(Chunk("CERTS", "Certifications: " + ", ".join(profile.certifications), "Certifications", {"section": "certs"}))
    if profile.summary:
        chunks.append(Chunk("SUMMARY", norm_ws(profile.summary), "Summary", {"section": "summary"}))

    # If structured parsing was thin, fall back to sentence windows over raw resume text.
    if len(chunks) < 4 and profile.resume_text.strip():
        sentences = split_sentences(profile.resume_text)
        window: list[str] = []
        n = 0
        for s in sentences:
            window.append(s)
            if sum(len(x) for x in window) > 350:
                n += 1
                chunks.append(Chunk(f"RAW{n}", " ".join(window), f"Resume excerpt {n}", {"section": "raw"}))
                window = []
        if window:
            n += 1
            chunks.append(Chunk(f"RAW{n}", " ".join(window), f"Resume excerpt {n}", {"section": "raw"}))
    return chunks
