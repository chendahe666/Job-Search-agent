"""Live smoke test for your Gemini key: models → grounded search → ATS verification.

Usage:  python scripts/smoke_gemini.py "Machine Learning Engineer" "Austin, TX"
Costs: 1 grounded search call (a few Google queries) + 1 small generation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

from jobpilot.extract.builder import JobBuilder  # noqa: E402
from jobpilot.llm.gemini import GeminiClient, GeminiError  # noqa: E402
from jobpilot.schemas import SearchPreferences, WorkMode  # noqa: E402
from jobpilot.search.fetcher import Fetcher  # noqa: E402
from jobpilot.search.gemini_search import GeminiSearcher  # noqa: E402
from jobpilot.search.planner import SearchTask  # noqa: E402
from jobpilot.verify.verifier import Verifier  # noqa: E402


def main() -> int:
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        print("✗ GEMINI_API_KEY not set (.env)")
        return 1
    title = sys.argv[1] if len(sys.argv) > 1 else "Machine Learning Engineer"
    where = sys.argv[2] if len(sys.argv) > 2 else "Remote United States"
    client = GeminiClient(key, os.getenv("GEMINI_MODEL", "gemini-3.8-flash"), max_retries=2)
    try:
        models = client.generation_models()
        print(f"✓ key ok · {len(models)} generation models · using {client.model}")
        if client.model not in models:
            print(f"  ! {client.model} not in your model list; try one of: {', '.join(m for m in models if 'flash' in m)[:300]}")
    except GeminiError as exc:
        print(f"✗ {exc}")
        return 1

    fetcher = Fetcher()
    prefs = SearchPreferences(target_titles=[title], locations=[] if "remote" in where.lower() else [where],
                              work_modes=[WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE], posted_within_days=14)
    task = SearchTask(id="smoke", titles=[title], locations=[where], site_filter=True)
    out = GeminiSearcher(client, fetcher, results_per_task=8).run(task, prefs, [])
    if out.error:
        print(f"✗ search failed: {out.error}")
        return 1
    print(f"✓ grounded search ran {len(out.queries)} Google queries: {out.queries[:4]}")
    print(f"✓ {len(out.leads)} leads")
    builder, verifier = JobBuilder(fetcher, client, use_llm=False), Verifier()
    for lead in out.leads[:6]:
        job, ev = builder.build(lead)
        v = verifier.verify(job, lead, ev)
        print(f"  [{v.status.value:10}] {lead.title[:45]:45} @ {lead.company[:20]:20} via {ev.method or '-':14} {job.location_text[:25]:25} {lead.url[:70]}")
    u = client.usage.usage
    print(f"usage: {u.llm_calls} LLM calls, {u.search_queries} search queries, {u.prompt_tokens + u.output_tokens} tokens, ≈${u.estimated_cost_usd():.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
