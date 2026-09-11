"""Search planning and plan mutation (the REFLECT stage edits the plan, never the user's constraints)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..schemas import CandidateProfile, Msg, SearchPreferences, Seniority, WorkMode, msg
from ..taxonomy import ATS_SITE_FILTER, ROLE_FAMILIES, US_METROS

SENIORITY_WORDS = {
    Seniority.INTERN: "intern",
    Seniority.ENTRY: "new grad OR entry level OR junior",
    Seniority.MID: "",
    Seniority.SENIOR: "senior",
    Seniority.STAFF: "staff",
    Seniority.PRINCIPAL: "principal",
    Seniority.MANAGER: "manager",
}


@dataclass
class SearchTask:
    id: str
    titles: list[str]
    locations: list[str]
    site_filter: bool = True
    extra_terms: list[str] = field(default_factory=list)
    company: str = ""
    raw_queries: list[str] = field(default_factory=list)
    strategy: str = "initial"
    done: bool = False

    def queries(self, prefs: SearchPreferences) -> list[str]:
        if self.raw_queries:
            return self.raw_queries
        sen = " OR ".join(dict.fromkeys(filter(None, (SENIORITY_WORDS.get(s, "") for s in prefs.seniority))))
        extra = " ".join(self.extra_terms)
        out = []
        for title in self.titles[:3]:
            base = f'"{title}"'
            if self.company:
                base += f' "{self.company}" careers'
            for loc in (self.locations or ["United States"])[:3]:
                q = " ".join(x for x in [base, sen if not self.company else "", loc, extra, ATS_SITE_FILTER if self.site_filter else ""] if x)
                out.append(q)
        return out[:6]

    def describe(self) -> str:
        parts = [", ".join(self.titles[:3])]
        if self.company:
            parts.append(f"@{self.company}")
        if self.locations:
            parts.append(" / ".join(self.locations[:3]))
        if self.site_filter:
            parts.append("ATS sites")
        if self.extra_terms:
            parts.append("+" + " ".join(self.extra_terms))
        if self.raw_queries:
            parts = ["critic: " + self.raw_queries[0][:60]]
        return " · ".join(parts)


def location_phrases(prefs: SearchPreferences) -> list[str]:
    locs = list(prefs.locations)
    if WorkMode.REMOTE in prefs.work_modes:
        locs.append("Remote United States")
    if not locs:
        locs = ["United States"]
    return locs


class SearchPlan:
    def __init__(self, profile: CandidateProfile, prefs: SearchPreferences) -> None:
        self.profile = profile
        self.prefs = prefs
        self.tasks: list[SearchTask] = []
        self.strategies: set[str] = set()
        self._n = 0
        self._build_initial()

    def _new_id(self) -> str:
        self._n += 1
        return f"T{self._n}"

    def _add(self, **kwargs) -> SearchTask:
        task = SearchTask(id=self._new_id(), **kwargs)
        sig = (tuple(task.titles), tuple(task.locations), task.site_filter, tuple(task.extra_terms), task.company, tuple(task.raw_queries))
        for t in self.tasks:
            if (tuple(t.titles), tuple(t.locations), t.site_filter, tuple(t.extra_terms), t.company, tuple(t.raw_queries)) == sig:
                return t
        self.tasks.append(task)
        return task

    def _build_initial(self) -> None:
        locs = location_phrases(self.prefs)
        for title in self.prefs.target_titles[:4]:
            self._add(titles=[title], locations=locs, site_filter=True, extra_terms=list(self.prefs.extra_keywords[:2]))
        if len(self.prefs.target_titles) > 1:
            self._add(titles=self.prefs.target_titles[:3], locations=locs, site_filter=False, strategy="broad")
        for company in self.prefs.dream_companies[:3]:
            self._add(titles=self.prefs.target_titles[:2], locations=locs, site_filter=False, company=company, strategy="dream_company")

    # ------------------------------------------------------------------ #
    def pending(self) -> list[SearchTask]:
        return [t for t in self.tasks if not t.done]

    def next_batch(self, max_calls: int) -> list[SearchTask]:
        return self.pending()[:max(0, max_calls)]

    def tried_queries(self) -> list[str]:
        out = []
        for t in self.tasks:
            if t.done:
                out.extend(t.queries(self.prefs)[:2])
        return out

    # ------------------------------------------------------------------ #
    # Mutation strategies (called by the critic)
    # ------------------------------------------------------------------ #
    def apply(self, strategy: str, payload: Optional[list[str]] = None) -> Optional[Msg]:
        """Apply a strategy once; returns a human-readable action or None if not applicable."""
        if strategy in self.strategies and strategy != "llm_queries":
            return None
        locs = location_phrases(self.prefs)
        titles = self.prefs.target_titles
        action: Optional[Msg] = None
        if strategy == "ats_sites":
            changed = 0
            for t in self.pending():
                if not t.site_filter and not t.company:
                    t.site_filter = True
                    changed += 1
            for title in titles[:3]:
                self._add(titles=[title], locations=locs, site_filter=True, extra_terms=["hiring"], strategy=strategy)
            action = msg("act.ats_sites", n=changed)
        elif strategy == "title_synonyms":
            synonyms: list[str] = []
            families = self.prefs.role_families or [
                fam for fam, names in ROLE_FAMILIES.items() if any(n.lower() in " ".join(titles).lower() or " ".join(titles).lower() in n.lower() for n in names)
            ]
            for fam in families:
                synonyms += [n for n in ROLE_FAMILIES.get(fam, []) if n.lower() not in {t.lower() for t in titles}]
            synonyms = list(dict.fromkeys(synonyms))[:4]
            if synonyms:
                for i in range(0, len(synonyms), 2):
                    self._add(titles=synonyms[i:i + 2], locations=locs, site_filter=True, strategy=strategy)
                action = msg("act.title_synonyms", titles=", ".join(synonyms))
        elif strategy == "skill_focus":
            skills = self.profile.skills[:3]
            if skills:
                for title in titles[:2]:
                    self._add(titles=[title], locations=locs, site_filter=True, extra_terms=skills, strategy=strategy)
                action = msg("act.skill_focus", skills=", ".join(skills))
        elif strategy == "sponsor_focus":
            for title in titles[:2]:
                self._add(titles=[title], locations=locs, site_filter=False, extra_terms=['"visa sponsorship"'], strategy=strategy)
            action = msg("act.sponsor_focus")
        elif strategy == "seniority_terms":
            neg = []
            if all(s in (Seniority.INTERN, Seniority.ENTRY) for s in self.prefs.seniority):
                neg = ["-senior", "-staff", "-principal", "-lead"]
            for title in titles[:2]:
                self._add(titles=[title], locations=locs, site_filter=True, extra_terms=neg, strategy=strategy)
            action = msg("act.seniority_terms", exclude=" ".join(neg))
        elif strategy == "metro_expansion":
            cities = []
            for loc in self.prefs.locations:
                for metro, members in US_METROS.items():
                    if loc.split(",")[0].strip().lower() in [m.lower() for m in members] or loc.lower() in metro.lower():
                        cities += [f"{m}" for m in members[:4] if m.lower() != loc.split(',')[0].strip().lower()]
            cities = list(dict.fromkeys(cities))[:6]
            if cities:
                for title in titles[:2]:
                    self._add(titles=[title], locations=cities[:3], site_filter=True, strategy=strategy)
                action = msg("act.metro_expansion", cities=", ".join(cities[:6]))
        elif strategy == "recency":
            for title in titles[:2]:
                self._add(titles=[title], locations=locs, site_filter=False, extra_terms=['"posted this week"'], strategy=strategy)
            action = msg("act.recency")
        elif strategy == "llm_queries" and payload:
            for q in payload[:3]:
                self._add(titles=titles[:1], locations=[], site_filter=False, raw_queries=[q], strategy=strategy)
            action = msg("act.llm_queries", queries=" | ".join(payload[:3]))
        if action:
            self.strategies.add(strategy)
        return action
