"""Polite HTTP fetching with caching, redirect resolution and aggregator awareness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import requests

from ..storage.db import Database
from ..textutils import domain_of
from ..taxonomy import AGGREGATOR_DOMAINS

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0 Safari/537.36 JobPilot/2.0 (personal job search assistant)"
)


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    text: str
    error: str = ""
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def is_aggregator(url: str) -> bool:
    d = domain_of(url)
    return any(d == a or d.endswith("." + a) for a in AGGREGATOR_DOMAINS)


class Fetcher:
    def __init__(self, db: Optional[Database] = None, timeout: float = 20.0, session: Optional[requests.Session] = None,
                 on_fetch: Optional[Any] = None) -> None:
        self.db = db
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})
        self.on_fetch = on_fetch

    def get(self, url: str, *, use_cache: bool = True, accept_json: bool = False) -> FetchResult:
        if use_cache and self.db:
            cached = self.db.http_cache_get(url)
            if cached:
                return FetchResult(url, cached["final_url"], cached["status"], cached["body"], from_cache=True)
        headers = {"Accept": "application/json" if accept_json else "text/html,application/xhtml+xml,*/*;q=0.8"}
        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout, allow_redirects=True)
            text = resp.text if len(resp.content) < 3_000_000 else resp.text[:3_000_000]
            result = FetchResult(url, resp.url, resp.status_code, text)
        except requests.RequestException as exc:
            result = FetchResult(url, url, 0, "", error=type(exc).__name__ + ": " + str(exc)[:200])
        if self.on_fetch:
            self.on_fetch()
        if self.db and result.status and result.status != 429:
            self.db.http_cache_put(url, result.status, result.text, result.final_url)
        return result

    def get_json(self, url: str) -> tuple[int, Any]:
        res = self.get(url, accept_json=True)
        if not res.ok:
            return res.status, None
        try:
            import json
            return res.status, json.loads(res.text)
        except ValueError:
            return res.status, None

    def resolve_redirect(self, url: str) -> str:
        """Gemini grounding URIs are vertexaisearch redirect links; follow them to the real page."""
        if "grounding-api-redirect" not in url:
            return url
        try:
            resp = self.session.head(url, allow_redirects=False, timeout=10)
            loc = resp.headers.get("Location")
            if loc:
                return loc
            resp = self.session.get(url, allow_redirects=True, timeout=15, stream=True)
            final = resp.url
            resp.close()
            return final
        except requests.RequestException:
            return url
