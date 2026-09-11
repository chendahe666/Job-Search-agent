"""Offline doubles for Gemini REST and HTTP so the live pipeline can be tested without network."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

GREENHOUSE_JD = """
<p>Acme AI builds retrieval systems for hospitals.</p>
<h3>What you'll do</h3><ul><li>Ship RAG services in Python</li><li>Deploy models on AWS</li></ul>
<h3>Requirements</h3>
<ul><li>2+ years of professional experience building ML systems</li>
<li>Strong Python and PyTorch skills</li>
<li>Experience deploying models on AWS with Docker</li>
<li>Experience with Kubernetes</li></ul>
<h3>Nice to have</h3><ul><li>Experience with LLM evaluation</li></ul>
<p>Salary range: $120,000 - $150,000 per year.</p>
<p>Visa sponsorship is available for this role.</p>
"""

LEVER_JD_NO_SPONSOR = {
    "id": "abc-123", "text": "Machine Learning Engineer", "categories": {"location": "Chicago, IL", "commitment": "Full-time"},
    "descriptionPlain": "Build ML platforms. We are unable to sponsor visas now or in the future.",
    "lists": [{"text": "Requirements", "content": "<li>3+ years of experience with Python</li><li>Experience with SQL</li>"}],
    "hostedUrl": "https://jobs.lever.co/beta/abc-123", "applyUrl": "https://jobs.lever.co/beta/abc-123/apply",
    "createdAt": 0, "workplaceType": "hybrid",
}


class FakeResponse:
    def __init__(self, status: int, text: str = "", url: str = "", headers: dict | None = None) -> None:
        self.status_code = status
        self.text = text
        self.content = text.encode()
        self.url = url
        self.headers = headers or {}

    def json(self) -> Any:
        return json.loads(self.text)

    def close(self) -> None:
        pass


class FakeSession:
    """Routes URLs to canned responses."""

    def __init__(self, routes: dict[str, Callable[[str], FakeResponse] | FakeResponse]) -> None:
        self.routes = routes
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []

    def _resolve(self, url: str) -> FakeResponse:
        self.calls.append(url)
        for pattern, resp in self.routes.items():
            if re.search(pattern, url):
                r = resp(url) if callable(resp) else resp
                if not r.url:
                    r.url = url
                return r
        return FakeResponse(404, "not found", url)

    def get(self, url: str, **kwargs) -> FakeResponse:
        return self._resolve(url)

    def head(self, url: str, **kwargs) -> FakeResponse:
        if "grounding-api-redirect" in url:
            target = url.split("/")[-1].replace("__", "/").replace("~", ":")
            return FakeResponse(302, "", url, {"Location": target})
        return self._resolve(url)


def gemini_payload(text: str, *, queries: list[str] | None = None, sources: list[str] | None = None) -> dict:
    return {
        "candidates": [{
            "content": {"parts": [{"text": text}]},
            "finishReason": "STOP",
            "groundingMetadata": {
                "webSearchQueries": queries or [],
                "groundingChunks": [{"web": {"uri": s, "title": "site"}} for s in (sources or [])],
            },
        }],
        "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 200},
    }


def redirect(url: str) -> str:
    return "https://vertexaisearch.cloud.google.com/grounding-api-redirect/" + url.replace(":", "~").replace("/", "__")


class FakeGemini:
    """Transport for GeminiClient: answers by prompt type."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.search_round = 0

    def __call__(self, method: str, url: str, body: dict | None, headers: dict, timeout: float):
        if method == "GET":
            return 200, {"models": [{"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]}]}, {}
        if url.endswith(":batchEmbedContents"):
            vecs = []
            for req in body["requests"]:
                txt = req["content"]["parts"][0]["text"].lower()
                v = [float(txt.count(w)) + 0.01 for w in ("python", "pytorch", "aws", "sql", "machine", "learning", "data", "docker")]
                vecs.append({"values": v})
            return 200, {"embeddings": vecs}, {}
        prompt = body["contents"][0]["parts"][-1]["text"]
        self.prompts.append(prompt)
        tools = [list(t)[0] for t in body.get("tools", [])]
        if "find up to" in prompt and "google_search" in tools:
            self.search_round += 1
            jobs = [
                {"title": "Machine Learning Engineer", "company": "Acme AI", "location": "Austin, TX",
                 "url": "https://boards.greenhouse.io/acmeai/jobs/1001", "posted": "2 days ago"},
                {"title": "Machine Learning Engineer", "company": "Beta Corp", "location": "Chicago, IL",
                 "url": "https://jobs.lever.co/beta/abc-123"},
                {"title": "Data Scientist", "company": "Gamma", "location": "Austin, TX",
                 "url": "https://boards.greenhouse.io/gamma/jobs/404404"},  # closed → DEAD
                {"title": "ML Engineer", "company": "Delta", "location": "Remote",
                 "url": "https://careers.delta.example/jobs/77"},  # page is a different job → MISMATCH
                {"title": "Machine Learning Engineer", "company": "Epsilon", "location": "Austin, TX",
                 "url": "https://www.linkedin.com/jobs/view/999"},  # aggregator → url_context
            ]
            if self.search_round > 1:
                jobs = [{"title": "Applied Scientist", "company": "Zeta", "location": "Remote (US)",
                         "url": "https://jobs.ashbyhq.com/zeta/5f2c-11"}]
            sources = [redirect(j["url"]) for j in jobs[:2]]
            return 200, gemini_payload(json.dumps({"jobs": jobs}), queries=["q1", "q2", "q3"], sources=sources), {}
        if "URL context tool" in prompt:
            return 200, gemini_payload(json.dumps({
                "is_job_posting": True, "is_closed": False, "title": "Machine Learning Engineer", "company": "Epsilon",
                "location_text": "Austin, TX", "work_mode": "onsite", "employment_type": "full_time",
                "requirements": [{"text": "Python experience", "kind": "required", "category": "skill", "terms": ["python"]}],
                "sponsorship_status": "unknown",
            })), {}
        if "Extract the job posting" in prompt:
            if "Acme AI" in prompt:
                data = {
                    "is_job_posting": True, "title": "Machine Learning Engineer", "company": "Acme AI",
                    "requirements": [
                        {"text": "2+ years of professional experience building ML systems", "kind": "required", "category": "experience", "terms": [], "min_years": 2},
                        {"text": "Strong Python and PyTorch skills", "kind": "required", "category": "skill", "terms": ["python", "pytorch"]},
                        {"text": "Experience deploying models on AWS with Docker", "kind": "required", "category": "skill", "terms": ["aws", "docker"]},
                        {"text": "Experience with Kubernetes", "kind": "required", "category": "skill", "terms": ["kubernetes"]},
                        {"text": "Experience with LLM evaluation", "kind": "preferred", "category": "skill", "terms": ["llm"]},
                        {"text": "PhD in machine learning required", "kind": "required", "category": "education", "terms": []},  # invented → dropped
                    ],
                    "sponsorship_status": "sponsors", "sponsorship_quote": "Visa sponsorship is available for this role.",
                    "min_years_experience": 2, "industry": "Healthcare / Biotech",
                }
            else:
                data = {"is_job_posting": True, "requirements": [], "sponsorship_status": "unknown"}
            return 200, gemini_payload(json.dumps(data)), {}
        if "For each requirement, use ONLY" in prompt:
            ids = re.findall(r"\[(R\d+)\]", prompt)
            items = []
            for rid in ids:
                if rid == "R2":
                    items.append({"requirement_id": rid, "status": "met", "chunk_id": "EXP1.2", "quote": "Deployed PyTorch models on AWS with Docker and FastAPI"})
                elif rid == "R3":
                    # hallucinated quote → must be downgraded / not counted
                    items.append({"requirement_id": rid, "status": "met", "chunk_id": "EXP1.1", "quote": "Managed Kubernetes clusters for 200 services"})
                elif rid == "R4":
                    items.append({"requirement_id": rid, "status": "met", "chunk_id": "EXP1.1", "quote": "Orchestrated Kubernetes deployments at scale"})
                else:
                    items.append({"requirement_id": rid, "status": "gap"})
            return 200, gemini_payload(json.dumps({"items": items})), {}
        if "H-1B" in prompt and "google_search" in tools:
            return 200, gemini_payload(json.dumps({"sponsorship": "occasional", "note": "12 LCAs in FY2025", "source_url": "https://example.org/h1b"}), queries=["h1b"]), {}
        if "quality critic" in json.dumps(body.get("systemInstruction", {})):
            return 200, gemini_payload(json.dumps({"diagnosis": ["few results"], "new_queries": ['"Applied Scientist" Austin']})), {}
        if "Write 3-5 resume bullets" in prompt:
            return 200, gemini_payload(json.dumps({
                "bullets": [
                    {"text": "Deployed PyTorch models on AWS with Docker and FastAPI", "chunk_ids": ["EXP1.2"]},
                    {"text": "Cut inference latency 40% on Kubernetes", "chunk_ids": ["EXP1.2"]},
                ],
                "pitch": "I build and deploy ML systems.", "keywords_to_mirror": ["pytorch", "kubernetes"],
            })), {}
        return 200, gemini_payload("{}"), {}


def fake_routes() -> dict:
    return {
        r"boards-api\.greenhouse\.io/v1/boards/acmeai/jobs/1001": FakeResponse(200, json.dumps({
            "id": 1001, "title": "Machine Learning Engineer", "absolute_url": "https://boards.greenhouse.io/acmeai/jobs/1001",
            "location": {"name": "Austin, TX"}, "first_published": "2026-09-09T12:00:00Z", "content": GREENHOUSE_JD,
            "company_name": "Acme AI",
        })),
        r"boards-api\.greenhouse\.io/v1/boards/gamma/jobs/404404": FakeResponse(404, "{}"),
        r"api\.lever\.co/v0/postings/beta/abc-123": FakeResponse(200, json.dumps(LEVER_JD_NO_SPONSOR)),
        r"careers\.delta\.example/jobs/77": FakeResponse(200, "<html><title>Senior Accountant</title><body><h1>Senior Accountant</h1>"
                                                               "<p>Delta Finance is hiring an accountant to manage ledgers and taxes." + " Details." * 80 + "</p></body></html>"),
        r"api\.ashbyhq\.com/posting-api/job-board/zeta": FakeResponse(200, json.dumps({"jobs": [{
            "id": "5f2c-11", "title": "Applied Scientist", "location": "Remote (US)", "isRemote": True, "workplaceType": "Remote",
            "employmentType": "FullTime", "publishedAt": "2026-09-10T00:00:00Z", "jobUrl": "https://jobs.ashbyhq.com/zeta/5f2c-11",
            "applyUrl": "https://jobs.ashbyhq.com/zeta/5f2c-11/application", "isListed": True,
            "descriptionPlain": "Requirements:\n• Python and PyTorch\n• 1+ years of experience in machine learning\n" + "Zeta builds AI. " * 40,
        }]})),
    }
