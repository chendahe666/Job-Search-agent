"""REFLECT stage: judge iteration quality, diagnose problems, choose the next strategy."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from ..llm.gemini import GeminiClient, GeminiError
from ..llm.prompts import CRITIC_PROMPT, CRITIC_SYSTEM, CriticDTO
from ..schemas import IterationReport, Msg, RunConfig, SearchPreferences, Usage, msg
from ..search.planner import SearchPlan, location_phrases


@dataclass
class Decision:
    stop: bool
    reason: str = ""
    diagnosis: list[Msg] = field(default_factory=list)
    actions: list[Msg] = field(default_factory=list)


class Critic:
    def __init__(self, config: RunConfig, prefs: SearchPreferences, llm: Optional[GeminiClient] = None) -> None:
        self.config = config
        self.prefs = prefs
        self.llm = llm

    def assess(self, it: IterationReport, history: list[IterationReport], shortlist_total: int, usage: Usage,
               plan: SearchPlan, search_errors: int, tasks_run: int) -> Decision:
        d = Decision(stop=False)
        # --- diagnosis ---------------------------------------------------
        if tasks_run and search_errors == tasks_run:
            d.diagnosis.append(msg("diag.search_failed"))
            if len(history) >= 2 and all(h.leads == 0 for h in history[-2:]):
                d.stop, d.reason = True, "search_failed"
                return d
        new = max(it.new_unique, 1)
        bad = it.dead + it.mismatch
        if it.new_unique and bad / new > 0.35:
            d.diagnosis.append(msg("diag.dead_rate", pct=round(100 * bad / new)))
        if it.new_unique and it.unverified / new > 0.5:
            d.diagnosis.append(msg("diag.unverified_rate", pct=round(100 * it.unverified / new)))
        if it.leads == 0:
            d.diagnosis.append(msg("diag.no_leads"))
        elif it.new_unique < 5:
            d.diagnosis.append(msg("diag.few_new", n=it.new_unique))
        rejects = Counter(it.rejection_reasons)
        total_rejects = sum(rejects.values())
        top_rule, top_n = (rejects.most_common(1)[0] if rejects else ("", 0))
        if total_rejects and top_n / max(it.new_unique, 1) >= 0.3:
            d.diagnosis.append(msg("diag.top_reject", rule=top_rule, pct=round(100 * top_n / max(it.new_unique, 1))))
        if it.hard_passed and it.shortlisted / it.hard_passed < 0.3:
            d.diagnosis.append(msg("diag.low_fit", passed=it.hard_passed, shortlisted=it.shortlisted))

        # --- stop conditions --------------------------------------------
        if shortlist_total >= self.config.target_shortlist:
            d.stop, d.reason = True, "target_reached"
        elif it.number >= self.config.max_iterations:
            d.stop, d.reason = True, "max_iterations"
        elif usage.search_calls >= self.config.max_search_calls or usage.search_queries >= self.config.max_search_queries:
            d.stop, d.reason = True, "budget"
        if d.stop:
            return d

        # --- strategy selection -----------------------------------------
        strategies: list[str] = []
        if it.new_unique and (bad / new > 0.35 or it.unverified / new > 0.5):
            strategies.append("ats_sites")
        rule_to_strategy = {
            "work_authorization": "sponsor_focus", "seniority": "seniority_terms", "years_experience": "seniority_terms",
            "posted_age": "recency", "location": "metro_expansion", "liveness": "ats_sites",
        }
        for rule, _ in rejects.most_common(2):
            if rule in rule_to_strategy:
                strategies.append(rule_to_strategy[rule])
        if it.hard_passed and it.shortlisted / it.hard_passed < 0.3:
            strategies.append("skill_focus")
        if it.new_unique < 5 or it.leads == 0:
            strategies += ["title_synonyms", "metro_expansion"]
        if not plan.pending():
            strategies += ["title_synonyms", "skill_focus", "recency"]

        for s in dict.fromkeys(strategies):
            action = plan.apply(s)
            if action:
                d.actions.append(action)

        if self.llm is not None and (not d.actions or it.shortlisted == 0):
            new_queries = self._llm_queries(it, plan)
            if new_queries:
                action = plan.apply("llm_queries", new_queries)
                if action:
                    d.actions.append(action)

        if not plan.pending():
            d.stop, d.reason = True, "saturated"
        return d

    def _llm_queries(self, it: IterationReport, plan: SearchPlan) -> list[str]:
        stats = it.model_dump(include={"leads", "new_unique", "verified", "unverified", "dead", "mismatch", "hard_passed", "shortlisted", "rejection_reasons"})
        try:
            dto, _ = self.llm.generate_json(
                CRITIC_PROMPT.format(stats=json.dumps(stats), titles=", ".join(self.prefs.target_titles),
                                     where="; ".join(location_phrases(self.prefs)), skills=", ".join(plan.profile.skills[:8]),
                                     tried=json.dumps(plan.tried_queries()[:12])),
                CriticDTO, system=CRITIC_SYSTEM,
            )
        except GeminiError:
            return []
        return [q.strip() for q in dto.new_queries if q.strip()][:3]


def user_suggestions(history: list[IterationReport], prefs: SearchPreferences, shortlist_total: int, target: int) -> list[Msg]:
    """Constraint changes only the USER may make — surfaced in the report, never auto-applied."""
    rejects = Counter()
    seen = 0
    for it in history:
        rejects.update(it.rejection_reasons)
        seen += it.new_unique
    out: list[Msg] = []
    if not seen:
        return [msg("sugg.no_results")]
    share = lambda rule: rejects.get(rule, 0) / seen
    if share("location") >= 0.3:
        out.append(msg("sugg.locations", pct=round(100 * share("location"))))
    if share("seniority") + share("years_experience") >= 0.3:
        out.append(msg("sugg.seniority", pct=round(100 * (share("seniority") + share("years_experience")))))
    if share("posted_age") >= 0.25:
        out.append(msg("sugg.window", days=prefs.posted_within_days, pct=round(100 * share("posted_age"))))
    if share("work_authorization") >= 0.25:
        out.append(msg("sugg.sponsorship", pct=round(100 * share("work_authorization"))))
    if share("salary") >= 0.2:
        out.append(msg("sugg.salary"))
    if shortlist_total < target:
        out.append(msg("sugg.more_titles", n=shortlist_total, target=target))
    return out
