"""SEARCH stage: live job discovery with Gemini + Google Search grounding."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from ..llm.gemini import GeminiAuthError, GeminiClient, GeminiError, GeminiModelNotFound
from ..llm.prompts import SEARCH_PROMPT, SEARCH_SYSTEM, SearchResults
from ..schemas import EmploymentType, JobCandidate, SearchPreferences
from ..textutils import canonical_url, extract_json_block
from .ats import parse_ats_url
from .fetcher import Fetcher
from .planner import SearchTask

DEMO_PATH = Path(__file__).resolve().parents[1] / "demo" / "sample_jobs.json"


class SearchOutcome:
    def __init__(self, task: SearchTask) -> None:
        self.task = task
        self.leads: list[JobCandidate] = []
        self.queries: list[str] = []
        self.error: str = ""


class GeminiSearcher:
    def __init__(self, client: GeminiClient, fetcher: Fetcher, results_per_task: int = 12) -> None:
        self.client = client
        self.fetcher = fetcher
        self.n = results_per_task

    def _prompt(self, task: SearchTask, prefs: SearchPreferences, exclude: list[str]) -> str:
        where = []
        if "remote" in [m.value for m in prefs.work_modes]:
            where.append("Remote (US-eligible)")
        if prefs.locations:
            where.append("on-site/hybrid in " + "; ".join(prefs.locations))
        extra_lines = []
        if task.company:
            extra_lines.append(f"- Company: {task.company} (search its careers site / ATS board)")
        if prefs.needs_sponsorship:
            extra_lines.append(
                "- Candidate needs US visa sponsorship: skip postings that say no sponsorship, US citizens only, "
                "or security clearance required."
            )
        if prefs.title_exclude_keywords:
            extra_lines.append("- Exclude titles containing: " + ", ".join(prefs.title_exclude_keywords))
        if prefs.company_blocklist:
            extra_lines.append("- Exclude companies: " + ", ".join(prefs.company_blocklist))
        return SEARCH_PROMPT.format(
            n=self.n,
            titles=" | ".join(task.titles),
            seniority=", ".join(s.value for s in prefs.seniority),
            employment=", ".join(e.value for e in prefs.employment_types) or EmploymentType.FULL_TIME.value,
            where="; ".join(where) or "United States",
            days=prefs.posted_within_days,
            extra="\n".join(extra_lines),
            queries="\n".join(f"- {q}" for q in task.queries(prefs)),
            exclude=", ".join(exclude[:25]) or "none",
        )

    def run(self, task: SearchTask, prefs: SearchPreferences, exclude: list[str]) -> SearchOutcome:
        out = SearchOutcome(task)
        prompt = self._prompt(task, prefs, exclude)
        try:
            try:
                parsed, resp = self.client.generate_json(prompt, SearchResults, system=SEARCH_SYSTEM, tools=["google_search"], temperature=0.3)
                leads = parsed.jobs
            except (GeminiAuthError, GeminiModelNotFound):
                raise
            except GeminiError:
                resp = self.client.generate(prompt, system=SEARCH_SYSTEM, tools=["google_search"], temperature=0.3)
                data = extract_json_block(resp.text)
                items = data.get("jobs", []) if isinstance(data, dict) else data
                leads = SearchResults.model_validate({"jobs": items}).jobs
        except (GeminiAuthError, GeminiModelNotFound):
            raise  # configuration problems must stop the run with a clear message
        except (GeminiError, ValueError) as exc:
            out.error = str(exc)[:300]
            return out

        out.queries = resp.search_queries
        resolved = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            resolved = list(pool.map(lambda s: (self.fetcher.resolve_redirect(s.uri), s.title), resp.sources[:20]))
        grounded_urls = {canonical_url(u) for u, _ in resolved}

        seen = set()
        for lead in leads:
            if not lead.url.startswith("http"):
                continue
            cu = canonical_url(lead.url)
            if cu in seen:
                continue
            seen.add(cu)
            out.leads.append(JobCandidate(
                title=lead.title, company=lead.company, location=lead.location, url=lead.url, posted=lead.posted,
                work_mode=lead.work_mode, snippet=lead.snippet, task_id=task.id, grounded=cu in grounded_urls,
            ))
        # Recover individual ATS postings the model saw (grounding sources) but did not list.
        for url, title in resolved:
            cu = canonical_url(url)
            if cu not in seen and parse_ats_url(url):
                seen.add(cu)
                out.leads.append(JobCandidate(url=url, title="", company="", snippet=title, task_id=task.id,
                                              grounded=True, source="grounding_source"))
        return out


class DemoSearcher:
    """Offline mode: serves bundled sample postings so the full UI/agent loop can be tried without a key."""

    def __init__(self, path: Path = DEMO_PATH) -> None:
        self.jobs = json.loads(path.read_text(encoding="utf-8"))

    def run(self, task: SearchTask, prefs: SearchPreferences, exclude: list[str]) -> SearchOutcome:
        out = SearchOutcome(task)
        generic = {"engineer", "developer", "senior", "junior", "specialist", "lead", "staff", "and", "the"}
        words = {w.lower() for t in task.titles for w in t.replace("/", " ").split() if len(w) > 2} - generic
        excluded = set(exclude)
        for job in self.jobs:
            url = f"demo://{job['id']}"
            if url in excluded:
                continue
            title_words = {w.lower().strip("&,") for w in job["title"].replace(",", " ").split()} - generic
            if words & title_words or (task.raw_queries and words & title_words):
                out.leads.append(JobCandidate(title=job["title"], company=job["company"], location=job["location"],
                                              url=url, task_id=task.id, source="demo", grounded=True))
        out.queries = task.queries(prefs)[:1]
        return out


SearchFn = Callable[[SearchTask, SearchPreferences, list[str]], SearchOutcome]
