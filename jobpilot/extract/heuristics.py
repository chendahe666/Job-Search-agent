"""Deterministic JD analysis. Used as the offline path and as a cross-check on LLM output."""

from __future__ import annotations

import re
from typing import Optional

from ..schemas import (
    DegreeLevel, EmploymentType, Requirement, RequirementCategory, RequirementKind, Seniority,
    SponsorshipSignal, SponsorshipStatus, WorkMode,
)
from ..taxonomy import (
    DEGREE_PATTERNS, KNOWN_SKILLS, SKILL_SYNONYMS, SENIORITY_TITLE_PATTERNS, SPONSORSHIP_PATTERNS, canonical_skill, term_in_text,
)
from ..textutils import norm_ws, parse_min_years, split_sentences

ALL_SKILL_SURFACES = sorted(set(KNOWN_SKILLS) | {a for alts in SKILL_SYNONYMS.values() for a in alts if len(a) > 1})

REQ_HEADINGS = re.compile(
    r"^(requirements|qualifications|minimum qualifications|basic qualifications|required qualifications|"
    r"what you('|’)ll need|what you bring|what we('|’)re looking for|you have|must have|who you are|"
    r"skills (and|&) experience|about you|your background|you might be a fit|you may be a good fit|"
    r"what we look for|key qualifications|the ideal candidate|you should have|must-haves|requirements and qualifications|"
    r"minimum requirements|required skills|your qualifications|what you need)\b",
    re.I,
)
PREF_HEADINGS = re.compile(
    r"^(preferred|preferred qualifications|nice to have|bonus( points)?|pluses|it('|’)s a plus|"
    r"additional qualifications|even better|ideal(ly)?|strong candidates may also|bonus if|nice-to-haves|"
    r"preferred skills|you might also have|extra credit|we('|’)d love)\b",
    re.I,
)
STOP_HEADINGS = re.compile(
    r"^(responsibilities|what you('|’)ll do|about (us|the team|the role)|benefits|perks|compensation|"
    r"salary|pay range|equal opportunity|eeo|how to apply|our values|location|why join|the expected|annual salary|"
    r"logistics|visa sponsorship|how we('|’)re different|come work with us|role specific policy)\b",
    re.I,
)


def detect_sponsorship(text: str) -> SponsorshipSignal:
    low = (text or "").lower()
    for status in ("citizen_only", "clearance", "no_sponsorship", "sponsors"):
        for pat in SPONSORSHIP_PATTERNS[status]:
            m = re.search(pat, low)
            if m:
                quote = _sentence_around(text, m.start(), m.end())
                return SponsorshipSignal(status=SponsorshipStatus(status), quote=quote)
    return SponsorshipSignal()


def _sentence_around(text: str, start: int, end: int) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), text.rfind("•", 0, start))
    right_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return norm_ws(text[left + 1: right + 1])[:400]


def infer_seniority(title: str, min_years: Optional[float] = None) -> Seniority:
    low = (title or "").lower()
    for level, pat in SENIORITY_TITLE_PATTERNS:
        if re.search(pat, low):
            return Seniority(level)
    if min_years is not None:
        if min_years >= 8:
            return Seniority.STAFF
        if min_years >= 5:
            return Seniority.SENIOR
        if min_years >= 2:
            return Seniority.MID
        return Seniority.ENTRY
    return Seniority.UNKNOWN


def infer_work_mode(*texts: str) -> WorkMode:
    joined = " ".join(t or "" for t in texts).lower()
    if re.search(r"\bhybrid\b", joined):
        return WorkMode.HYBRID
    if re.search(r"\b(fully remote|100% remote|remote[- ]first|remote \(us|remote - us|remote, us|us[- ]remote|remote in the (us|united states)|work from home|\bremote\b)", joined):
        if re.search(r"\b(not remote|no remote|non-remote)\b", joined):
            return WorkMode.ONSITE
        return WorkMode.REMOTE
    if re.search(r"\b(on-?site|in[- ]office|in person)\b", joined):
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def infer_employment_type(*texts: str) -> EmploymentType:
    joined = " ".join(t or "" for t in texts).lower()
    if re.search(r"\b(intern|internship|co-?op)\b", joined):
        return EmploymentType.INTERNSHIP
    if re.search(r"\b(contract|contractor|c2c|1099|w2 contract)\b", joined):
        return EmploymentType.CONTRACT
    if re.search(r"\bpart[- ]time\b", joined):
        return EmploymentType.PART_TIME
    if re.search(r"\bfull[- ]time\b", joined):
        return EmploymentType.FULL_TIME
    return EmploymentType.UNKNOWN


def infer_degree(text: str) -> Optional[DegreeLevel]:
    low = (text or "").lower()
    found = [DegreeLevel(level) for level, pat in DEGREE_PATTERNS if re.search(pat, low)]
    if not found:
        return None
    # "Bachelor's or Master's" → the minimum mentioned is the requirement
    order = [DegreeLevel.ASSOCIATE, DegreeLevel.BACHELOR, DegreeLevel.MASTER, DegreeLevel.PHD]
    return min(found, key=order.index)


def find_terms(text: str) -> list[str]:
    terms = []
    for skill in ALL_SKILL_SURFACES:
        if term_in_text(skill, text):
            terms.append(canonical_skill(skill))
    return list(dict.fromkeys(terms))


def categorize(line: str) -> RequirementCategory:
    low = line.lower()
    if re.search(r"(authorized to work|sponsorship|citizen|clearance|green card|work authorization)", low):
        return RequirementCategory.AUTHORIZATION
    if re.search(r"(bachelor|master|ph\.?d|degree|b\.s\.|m\.s\.)", low):
        return RequirementCategory.EDUCATION
    if re.search(r"(certif|license)", low):
        return RequirementCategory.CERTIFICATION
    if re.search(r"\d+\+?\s*(-\s*\d+\s*)?years?", low):
        return RequirementCategory.EXPERIENCE
    return RequirementCategory.SKILL


def extract_requirements(text: str, max_items: int = 18) -> list[Requirement]:
    lines = [norm_ws(ln.strip(" •-*·\t")) for ln in (text or "").split("\n")]
    reqs: list[Requirement] = []
    mode: Optional[RequirementKind] = None
    for ln in lines:
        if not ln:
            continue
        heading = ln.rstrip(":").strip()
        if len(heading) < 60 and REQ_HEADINGS.match(heading):
            mode = RequirementKind.REQUIRED
            continue
        if len(heading) < 60 and PREF_HEADINGS.match(heading):
            mode = RequirementKind.PREFERRED
            continue
        if len(heading) < 60 and STOP_HEADINGS.match(heading):
            mode = None
            continue
        if mode is None or len(ln) < 4 or len(ln) > 400:
            continue
        kind = mode
        if re.search(r"\b(preferred|nice to have|a plus|bonus)\b", ln.lower()):
            kind = RequirementKind.PREFERRED
        cat = categorize(ln)
        reqs.append(Requirement(
            id=f"R{len(reqs) + 1}", text=ln, kind=kind, category=cat, terms=find_terms(ln),
            min_years=parse_min_years(ln) if cat == RequirementCategory.EXPERIENCE else None,
        ))
        if len(reqs) >= max_items:
            break
    if not reqs:  # unstructured posting → one requirement per detected skill
        terms = find_terms(text)[:12]
        for t in terms:
            reqs.append(Requirement(id=f"R{len(reqs) + 1}", text=f"Experience with {t}", terms=[t],
                                    kind=RequirementKind.REQUIRED, category=RequirementCategory.SKILL))
    return reqs


def extract_responsibilities(text: str, max_items: int = 8) -> list[str]:
    out, active = [], False
    for ln in (text or "").split("\n"):
        clean = norm_ws(ln.strip(" •-*·\t"))
        if not clean:
            continue
        if re.match(r"^(responsibilities|what you('|’)ll do|the role|in this role|your impact)\b", clean.rstrip(":"), re.I):
            active = True
            continue
        if active and (REQ_HEADINGS.match(clean) or PREF_HEADINGS.match(clean) or STOP_HEADINGS.match(clean)):
            break
        if active and 10 < len(clean) < 300:
            out.append(clean)
            if len(out) >= max_items:
                break
    return out


def summarize_min_years(text: str) -> Optional[float]:
    candidates = [parse_min_years(s) for s in split_sentences(text) if re.search(r"years?", s, re.I)]
    values = [c for c in candidates if c is not None]
    return min(values) if values else None
