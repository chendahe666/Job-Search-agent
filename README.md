# RoleSignal · Personal Resume Workspace

CS 5588 capstone: a Python / Streamlit job-search application with specialist
agents and explicit human review. The current interface is resume-first and
supports Chinese / English UI switching for users exploring US software, AI/ML,
and data roles. The language selector changes interface labels, not resume text.

## Start locally

Use Python 3.11+ and a virtual environment:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py --server.address=127.0.0.1
```

Open the local URL printed in the terminal (normally http://localhost:8501).
No API key is needed to begin. Keep the server bound to localhost: this is a
single-user tool, not an authenticated multi-user service.

## Everyday workflow

1. **Paste your experience.** An existing resume or a few project notes are
   enough. Only the experience field is required; skills and other details are
   optional. Empty inputs show actionable errors without trapping the user.
2. **Choose one direction.** Software Engineer, AI/ML Engineer, or Data Scientist.
   This labels the version and guides optional AI edits; it does not magically
   rewrite a resume or invent experience.
3. **Edit and save.** Original text is preserved as the initial draft. Save new
   versions, compare source-linked AI suggestions, and download plain-text copies.
   Loading an older version first backs up the current nonempty draft.
4. **Add a real job.** Paste its title and JD, optionally its company, source URL,
   and explicit skill requirements. URL entry stores a link; it does not scrape.
   Repeated links/JDs are deduplicated without overwriting an existing snapshot.
5. **Track the application.** Save progress, next steps, a follow-up date, and
   the exact resume version used. Nothing is submitted automatically.

Navigation preserves experience/editor drafts within the browser session.
Explicitly save before closing the browser. Saved material and versions survive
server restarts. Settings exports all stored business records as JSON.

## Optional AI editing

Open **Settings / 设置**, select Gemini or Groq, and enter an
API key plus a model ID supported by that provider. Keys remain in session
memory and are not written to the database. This UI does not silently use keys
from `.env`; provider modules retain environment configuration for direct use.

The user must consent before sending the current complete draft and associated
JD to the selected provider. Remove unnecessary personal information first.
Suggestions show the exact original excerpt and proposed replacement. Internal
prompts, raw provider errors, and raw response metadata are not displayed.
Recognizable instruction echoes and newly introduced numerical claims are
rejected before rendering; this is defense in depth, not a secrecy guarantee.
The user selects which edits to apply, then separately saves a new version.
Failures preserve the original and allow manual editing. Live API calls are not
part of the automated test suite.

## Architecture and matching methods

```text
app.py                    Streamlit entry point, no eager model load
ui/workspace.py           Guided workflow and explicit approval controls
services/workspace.py     Local SQLite records and immutable resume snapshots
agents/
  profile_analyzer.py     Deterministic normalization of structured profile input
  embedding_agent.py      Sentence Transformers + cosine similarity
  hybrid_matcher.py       Weighted dense and lexical ranking
  resume_agent.py         Optional source-linked LLM editing proposals
  evidence_grounder.py    Conservative explicit skill-declaration reporting
  reasoning_agent.py      Provider adapters and fit-explanation API
  human_matcher.py        Legacy rule-based experiment baseline
  ai_matcher.py           Legacy monolithic AI / simulation baseline
data/                     Original 10 and expanded 40 fictional tech postings
tests/                    Offline unit and Streamlit interaction tests
local_data/               Private local database; excluded from Git
evals/, report/           Historical course experiment artifacts
```

These are specialist responsibilities, not autonomous agents with permission to
submit applications. Deterministic storage and validation enforce workflow
boundaries; language models propose text but cannot directly save a final resume.

Job ranking runs **only when requested**, across the whole selected corpus.
MiniLM embeddings are compared using cosine similarity, with a 60% dense / 40%
lexical weighted score (BM25 when available, token overlap otherwise). RRF is
retained as a diagnostic field, not the final ranking criterion. The UI only
loads an already-cached embedding model; it never downloads model weights on
startup. If unavailable, it displays that TF-IDF replaced semantic embeddings.
To intentionally provision the model ahead of time:

```powershell
.venv\Scripts\python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

Matching and search are distinct: keyword search always covers all selected
postings, not a hidden top-five shortlist. Fictional jobs are an opt-in demo and
cannot enter the real application tracker. Scores indicate text alignment, not
hiring probability, skill verification, or eligibility.

## Honesty and privacy boundaries

- A skill mention is not proof of proficiency. Free-text negations are not
  converted into verified skills. Missing evidence means “needs confirmation.”
- No claim of zero hallucinations or measured ATS performance is made. Legacy
  `hallucination_rate` and `ats_readability_score` now return `None` (unknown).
- Source-linked edits still require human fact checking. An LLM can introduce
  unsupported wording even when it cites a genuine source excerpt.
- Application/visa/authorization answers are not inferred or submitted.
- `local_data/workspace.db` contains unencrypted personal data. Protect the
  computer and any backups. The app has no account isolation or public hosting
  security. `ROLESIGNAL_DB` can select a separate local database for testing.
- Previous `evals/` and `report/` outputs contain illustrative/simulated metrics
  and outdated UI descriptions. They are retained as historical artifacts, NOT
  validated results for this revision. Re-evaluation is needed before academic
  reporting; do not reuse the old zero-hallucination claims.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

Tests use isolated databases, fake provider responses and injected embeddings.
Coverage includes bilingual switching, wizard validation/navigation, draft preservation, job-to-resume
navigation, tracking, immutable saves, duplicate imports, complete-corpus search,
negated skills, and safe application of selected exact-source edits.

## Current scope

Available: paste-based material entry, editable drafts, role-specific version
labels, opt-in AI edits, TXT/JSON downloads, real-JD storage, local ranking,
and durable manual tracking.

Not yet implemented: PDF/Word parsing or formatted export, structured project
interviews, automatic job feeds, authorization/sponsorship screening, browser
autofill, email integration, background reminders, or automatic application
submission. A saved follow-up date is a record, not a scheduled notification.
