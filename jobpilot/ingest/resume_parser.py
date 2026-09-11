"""READ stage: resume file → text → structured CandidateProfile (LLM with verbatim checks, or heuristics)."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import date
from typing import Optional

from ..extract.heuristics import find_terms, infer_degree
from ..taxonomy import canonical_skill
from ..llm.gemini import GeminiClient, GeminiError
from ..llm.prompts import RESUME_PROMPT, RESUME_SYSTEM, ResumeExtraction
from ..schemas import CandidateProfile, DegreeLevel, Education, Experience, Project
from ..textutils import norm_ws, quote_in_source

SECTION_RE = re.compile(
    r"^\s*(professional experience|work experience|experience|employment|research experience|education|"
    r"projects?|technical skills|skills|certifications?|publications|summary|profile|objective|awards|leadership)\s*:?\s*$",
    re.I,
)
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec"
DATE_RANGE = re.compile(
    rf"(?P<m1>{MONTHS})?[a-z]*\.?\s*(?P<y1>(19|20)\d{{2}})\s*(–|-|—|to)\s*(?P<end>present|current|now|((?P<m2>{MONTHS})?[a-z]*\.?\s*(?P<y2>(19|20)\d{{2}})))",
    re.I,
)


def read_upload(filename: str, data: bytes) -> tuple[str, Optional[tuple[bytes, str]]]:
    """Return (extracted_text, inline_file_for_llm)."""
    name = filename.lower()
    if name.endswith(".pdf"):
        text = ""
        try:
            from pypdf import PdfReader  # optional dependency
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            text = ""
        return text, (data, "application/pdf")
    if name.endswith(".docx"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
            xml = re.sub(r"</w:p>", "\n", xml)
            xml = re.sub(r"<w:tab/>", "\t", xml)
            text = re.sub(r"<[^>]+>", "", xml)
            import html
            return html.unescape(text), None
        except (zipfile.BadZipFile, KeyError):
            return "", None
    return data.decode("utf-8", errors="replace"), None


def parse_resume(text: str, llm: Optional[GeminiClient] = None, inline_file: Optional[tuple[bytes, str]] = None) -> tuple[CandidateProfile, list[str]]:
    """Returns (profile, warnings)."""
    warnings: list[str] = []
    if llm is not None:
        try:
            files = [inline_file] if inline_file and not text.strip() else []
            prompt = RESUME_PROMPT.format(resume=text[:30000] if text.strip() else "(see attached PDF)")
            dto, _ = llm.generate_json(prompt, ResumeExtraction, system=RESUME_SYSTEM, inline_files=files)
            profile = _from_dto(dto, text)
            if text.strip():
                dropped = 0
                for exp in profile.experiences:
                    kept = [b for b in exp.bullets if quote_in_source(b, text, threshold=0.8)]
                    dropped += len(exp.bullets) - len(kept)
                    exp.bullets = kept
                profile.skills = [s for s in profile.skills if s.lower() in text.lower() or find_terms(s)]
                if dropped:
                    warnings.append(f"Removed {dropped} bullet(s) the model paraphrased or invented (not found verbatim in the resume).")
            else:
                warnings.append("PDF text could not be extracted locally (install pypdf) — bullets were not verbatim-checked; please review.")
            return profile, warnings
        except GeminiError as exc:
            warnings.append(f"Gemini parsing failed ({str(exc)[:120]}); used the offline parser.")
    if not text.strip():
        return CandidateProfile(), warnings + ["No text could be extracted. Paste the resume text instead."]
    return heuristic_parse(text), warnings


def _from_dto(dto: ResumeExtraction, text: str) -> CandidateProfile:
    try:
        degree = DegreeLevel(dto.highest_degree.strip().lower())
    except ValueError:
        degree = infer_degree(dto.highest_degree) or DegreeLevel.NONE
    return CandidateProfile(
        name=dto.name, headline=dto.headline, summary=dto.summary, current_location=dto.current_location,
        years_experience=dto.years_experience, highest_degree=degree, education=dto.education,
        experiences=dto.experiences, projects=dto.projects, skills=list(dict.fromkeys(dto.skills)),
        certifications=dto.certifications, links=dto.links, resume_text=text,
    )


def heuristic_parse(text: str) -> CandidateProfile:
    lines = [ln.rstrip() for ln in text.replace("\r", "").split("\n")]
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for ln in lines:
        m = SECTION_RE.match(ln.strip())
        if m and len(ln.strip()) < 40:
            key = m.group(1).lower()
            current = ("experience" if "experience" in key or key == "employment" else
                       "education" if key == "education" else "projects" if key.startswith("project") else
                       "skills" if "skill" in key else "certs" if key.startswith("certif") else "summary" if key in ("summary", "profile", "objective") else key)
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(ln)

    header = [norm_ws(x) for x in sections.get("header", []) if norm_ws(x)]
    name = header[0] if header and len(header[0]) < 60 else ""
    links = re.findall(r"(https?://\S+|linkedin\.com/\S+|github\.com/\S+)", text)

    experiences: list[Experience] = []
    exp: Optional[Experience] = None
    years = 0.0
    for ln in sections.get("experience", []):
        clean = norm_ws(ln)
        if not clean:
            continue
        is_bullet = bool(re.match(r"^\s*[•\-\*▪●◦]", ln))
        dr = DATE_RANGE.search(clean)
        if not is_bullet and (dr or (exp is None)):
            title_part = DATE_RANGE.sub("", clean).strip(" |,–-")
            exp = Experience(title=title_part[:120], start=dr.group("y1") if dr else "", end=(dr.group("end") if dr else ""))
            experiences.append(exp)
            if dr:
                years += _span_years(dr) * (0.5 if re.search(r"intern|assistant|research", clean, re.I) else 1.0)
        elif exp is not None:
            if is_bullet or len(clean) > 40:
                exp.bullets.append(clean.lstrip("•-*▪●◦ ").strip())
            elif not exp.company:
                exp.company = clean[:80]

    projects = []
    for ln in sections.get("projects", []):
        clean = norm_ws(ln).lstrip("•-*▪●◦ ")
        if not clean:
            continue
        if re.match(r"^\s*[•\-\*▪●◦]", ln) and projects:
            projects[-1].description = norm_ws(projects[-1].description + " " + clean)
        else:
            projects.append(Project(name=clean[:80], description="" if len(clean) <= 80 else clean))
    for p in projects:
        p.technologies = find_terms(p.name + " " + p.description)

    edu_text = "\n".join(sections.get("education", []))
    education = []
    for ln in sections.get("education", []):
        clean = norm_ws(ln)
        deg = infer_degree(clean)
        if deg or re.search(r"university|college|institute", clean, re.I):
            education.append(Education(school=clean[:100], degree=deg or DegreeLevel.NONE))
    degrees = [e.degree for e in education if e.degree != DegreeLevel.NONE]
    order = [DegreeLevel.NONE, DegreeLevel.ASSOCIATE, DegreeLevel.BACHELOR, DegreeLevel.MASTER, DegreeLevel.PHD]
    highest = max(degrees, key=order.index) if degrees else (infer_degree(edu_text) or DegreeLevel.NONE)

    skills_raw = " , ".join(sections.get("skills", []))
    listed = [norm_ws(re.sub(r"^[A-Za-z &/]+:\s*", "", s)) for s in re.split(r"[,;|•\n]", skills_raw)]
    skills = [s for s in listed if 1 < len(s) < 40]
    have = {canonical_skill(s) for s in skills}
    for t in find_terms(text):
        if canonical_skill(t) not in have:
            skills.append(t)
            have.add(canonical_skill(t))

    summary = norm_ws(" ".join(sections.get("summary", [])))[:600]
    return CandidateProfile(
        name=name, summary=summary, years_experience=round(years, 1), highest_degree=highest, education=education,
        experiences=experiences, projects=projects, skills=list(dict.fromkeys(skills))[:60],
        certifications=[norm_ws(x) for x in sections.get("certs", []) if norm_ws(x)][:10], links=links[:5], resume_text=text,
    )


def _span_years(m: re.Match) -> float:
    y1 = int(m.group("y1"))
    m1 = _month(m.group("m1"))
    end = (m.group("end") or "").lower()
    if end in ("present", "current", "now"):
        today = date.today()
        y2, m2 = today.year, today.month
    else:
        y2, m2 = int(m.group("y2")), _month(m.group("m2")) or 12
    return max(0.0, ((y2 - y1) * 12 + ((m2 or 12) - (m1 or 1))) / 12)


def _month(token: Optional[str]) -> int:
    if not token:
        return 0
    return ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"].index(token.lower()[:3]) + 1
