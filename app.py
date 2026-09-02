"""RoleSignal: Agentic AI-guided job matching Streamlit application.

The UI acts as the workflow orchestrator. It collects human-provided context,
hands it to independent specialist agents, and returns ranked, inspectable
recommendations. The user remains responsible for deciding whether to apply.
"""

from __future__ import annotations

from html import escape
import os
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

try:
    from dotenv import load_dotenv
except ImportError:  # The declared dependency is optional for keyless local demos.
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        """No-op fallback when python-dotenv is not installed."""

        return False

from agents import EmbeddingAgent, FitExplanation, ProfileAnalyzer, ReasoningAgent
from data import JobRepository


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

st.set_page_config(
    page_title="RoleSignal · Agentic Job Match",
    page_icon="◎",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    """Apply the app's editorial control-room visual system."""

    st.markdown(
        """
        <style>
        :root {
            --paper: #f4f1e8;
            --paper-deep: #e9e4d7;
            --ink: #18231d;
            --muted: #667068;
            --rule: #cfc9b9;
            --signal: #d45738;
            --signal-dark: #963923;
            --sage: #2f5f4b;
            --lime: #cadd74;
        }

        .stApp {
            color: var(--ink);
            background:
                radial-gradient(circle at 82% 5%, rgba(202, 221, 116, .22), transparent 24rem),
                linear-gradient(rgba(24, 35, 29, .025) 1px, transparent 1px),
                var(--paper);
            background-size: auto, 100% 32px, auto;
        }

        html, body, [class*="css"] {
            font-family: "Aptos", "Trebuchet MS", sans-serif;
        }

        h1, h2, h3, h4 {
            color: var(--ink) !important;
            font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif !important;
            letter-spacing: -0.025em;
        }

        [data-testid="stSidebar"] {
            background: var(--ink);
            border-right: 1px solid rgba(244, 241, 232, .14);
        }

        [data-testid="stSidebar"] * {
            color: #f5f1e7;
        }

        [data-testid="stSidebar"] h1,
        [data-testid="stSidebar"] h2,
        [data-testid="stSidebar"] h3 {
            color: #ffffff !important;
        }

        [data-testid="stSidebar"] .stCaptionContainer p {
            color: #bfc9c1;
        }

        [data-testid="stSidebar"] hr {
            border-color: rgba(244, 241, 232, .15);
        }

        [data-testid="stSidebar"] input,
        [data-testid="stSidebar"] textarea,
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            color: #17221c !important;
            background: #fbf8ef !important;
            border-color: transparent !important;
        }

        [data-testid="stSidebar"] [data-testid="stWidgetLabel"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] label {
            color: #e9eee9 !important;
            font-weight: 650;
        }

        .block-container {
            max-width: 1180px;
            padding-top: 2.2rem;
            padding-bottom: 4rem;
        }

        .hero {
            position: relative;
            overflow: hidden;
            padding: 1.2rem 0 2rem;
            border-bottom: 1px solid var(--rule);
            margin-bottom: 1.7rem;
            animation: rise-in .55s ease-out both;
        }

        .hero::after {
            content: "◎";
            position: absolute;
            right: .5rem;
            top: -4.6rem;
            color: rgba(47, 95, 75, .09);
            font-family: Georgia, serif;
            font-size: 15rem;
            line-height: 1;
            pointer-events: none;
        }

        .eyebrow, .section-kicker {
            color: var(--signal-dark);
            font-size: .73rem;
            font-weight: 800;
            letter-spacing: .17em;
            text-transform: uppercase;
        }

        .hero h1 {
            max-width: 780px;
            margin: .25rem 0 .65rem;
            font-size: clamp(3rem, 7vw, 5.7rem);
            font-weight: 500;
            line-height: .92;
        }

        .hero-copy {
            max-width: 690px;
            color: #48554d;
            font-family: "Iowan Old Style", Georgia, serif;
            font-size: 1.15rem;
            line-height: 1.55;
        }

        .proof-strip {
            display: flex;
            flex-wrap: wrap;
            gap: .55rem;
            margin-top: 1.25rem;
        }

        .proof-chip {
            padding: .38rem .68rem;
            border: 1px solid var(--rule);
            border-radius: 999px;
            background: rgba(255,255,255,.28);
            color: #4b594f;
            font-size: .77rem;
            font-weight: 700;
        }

        .agent-step {
            min-height: 148px;
            padding: 1rem 1.05rem;
            border-top: 3px solid var(--ink);
            background: rgba(255,255,255,.34);
        }

        .agent-number {
            display: block;
            color: var(--signal);
            font-family: "Courier New", monospace;
            font-size: .78rem;
            font-weight: 800;
            margin-bottom: .8rem;
        }

        .agent-step strong {
            display: block;
            color: var(--ink);
            font-family: "Iowan Old Style", Georgia, serif;
            font-size: 1.18rem;
            margin-bottom: .35rem;
        }

        .agent-step p {
            color: var(--muted);
            font-size: .88rem;
            line-height: 1.45;
            margin: 0;
        }

        div.stButton > button[kind="primary"] {
            min-height: 3.3rem;
            border: 0;
            border-radius: 2px;
            background: var(--signal);
            box-shadow: 5px 5px 0 var(--ink);
            color: white;
            font-size: .92rem;
            font-weight: 800;
            letter-spacing: .06em;
            text-transform: uppercase;
            transition: transform .14s ease, box-shadow .14s ease, background .14s ease;
        }

        div.stButton > button[kind="primary"]:hover {
            background: var(--signal-dark);
            color: white;
            transform: translate(2px, 2px);
            box-shadow: 3px 3px 0 var(--ink);
        }

        [data-testid="stMetric"] {
            padding: .8rem 1rem;
            border-left: 1px solid var(--rule);
            background: rgba(255,255,255,.24);
        }

        [data-testid="stMetricValue"] {
            font-family: "Iowan Old Style", Georgia, serif;
            color: var(--sage);
        }

        [data-testid="stVerticalBlockBorderWrapper"] {
            border: 1px solid var(--rule) !important;
            border-radius: 3px !important;
            background: rgba(255, 253, 247, .68);
            box-shadow: 0 14px 36px rgba(49, 56, 49, .06);
            animation: rise-in .42s ease-out both;
        }

        [data-testid="stProgress"] > div > div > div > div {
            background: var(--signal);
        }

        .score-label {
            color: var(--muted);
            font-size: .7rem;
            font-weight: 800;
            letter-spacing: .12em;
            text-align: right;
            text-transform: uppercase;
        }

        .score-number {
            color: var(--sage);
            font-family: "Iowan Old Style", Georgia, serif;
            font-size: 2.8rem;
            line-height: 1;
            text-align: right;
        }

        .rank-stamp {
            display: inline-block;
            margin-bottom: .45rem;
            color: var(--signal-dark);
            font-family: "Courier New", monospace;
            font-size: .73rem;
            font-weight: 800;
            letter-spacing: .1em;
            text-transform: uppercase;
        }

        .source-note {
            display: inline-block;
            padding: .2rem .48rem;
            border-radius: 2px;
            background: #dfe7d8;
            color: #294d3e;
            font-size: .72rem;
            font-weight: 750;
        }

        .fine-print {
            margin-top: 2rem;
            padding-top: 1rem;
            border-top: 1px solid var(--rule);
            color: var(--muted);
            font-size: .78rem;
        }

        @keyframes rise-in {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 760px) {
            .hero h1 { font-size: 3.3rem; }
            .hero::after { display: none; }
            .block-container { padding-top: 1rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def load_jobs() -> list[dict[str, Any]]:
    """Cache the validated local dataset across Streamlit reruns."""

    return JobRepository(BASE_DIR / "data" / "jobs.json").load_jobs()


@st.cache_resource(show_spinner=False)
def get_embedding_agent(model_name: str) -> EmbeddingAgent:
    """Reuse the downloaded embedding model instead of loading it per click."""

    return EmbeddingAgent(model_name=model_name)


def seed_sample_profile() -> None:
    """Populate an intentionally plausible capstone demo persona."""

    st.session_state.profile_skills = (
        "Python, SQL, scikit-learn, pandas, Streamlit, Git, Docker, Tableau"
    )
    st.session_state.target_roles = "Data Scientist, Machine Learning Engineer"
    st.session_state.preferred_locations = "Chicago, Remote"
    st.session_state.work_preferences = ["Hybrid", "Remote"]
    st.session_state.experience_level = "Entry-level"
    st.session_state.years_experience = 1.0
    st.session_state.professional_summary = (
        "Computer science graduate who built end-to-end analytics and machine "
        "learning projects, enjoys explaining model results, and wants a role "
        "with mentorship and measurable user impact."
    )


def initialize_state() -> None:
    """Set widget defaults once while preserving the user's current session."""

    defaults = {
        "profile_skills": "Python, SQL, pandas, Git",
        "target_roles": "Data Analyst, Python Developer",
        "preferred_locations": "Chicago, Remote",
        "work_preferences": ["Hybrid", "Remote"],
        "experience_level": "Entry-level",
        "years_experience": 1.0,
        "professional_summary": "",
        "match_results": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def render_sidebar() -> dict[str, Any]:
    """Render configuration and human-owned profile inputs."""

    with st.sidebar:
        st.markdown("# ◎ RoleSignal")
        st.caption("Candidate control panel · CS 5588 MVP")
        st.button(
            "Load sample profile",
            on_click=seed_sample_profile,
            use_container_width=True,
        )
        st.divider()

        st.markdown("### Your profile")
        st.text_area(
            "Skills",
            key="profile_skills",
            height=105,
            placeholder="Python, SQL, React, AWS…",
            help="Comma- or line-separated technical and professional skills.",
        )
        st.selectbox(
            "Experience level",
            ["Student", "Entry-level", "Mid-level", "Senior"],
            key="experience_level",
        )
        st.slider(
            "Years of relevant experience",
            min_value=0.0,
            max_value=20.0,
            step=0.5,
            key="years_experience",
        )
        st.text_input(
            "Target roles",
            key="target_roles",
            placeholder="Data Scientist, ML Engineer",
        )
        st.text_input(
            "Preferred locations",
            key="preferred_locations",
            placeholder="Chicago, Remote",
        )
        st.multiselect(
            "Work style",
            ["On-site", "Hybrid", "Remote"],
            key="work_preferences",
        )
        st.text_area(
            "Background & goals (optional)",
            key="professional_summary",
            height=105,
            placeholder="What have you built, and what do you want next?",
        )

        st.divider()
        st.markdown("### Agent settings")
        top_k = st.slider("Results to return", 1, 7, 4)
        embedding_model = st.text_input(
            "Embedding model",
            value=EmbeddingAgent.DEFAULT_MODEL,
            help="A Hugging Face Sentence Transformers model identifier.",
        )
        use_groq = st.toggle(
            "Use Groq explanations",
            value=bool(os.getenv("GROQ_API_KEY")),
            help="Off uses an explainable local skill-overlap fallback.",
        )
        groq_key = st.text_input(
            "Groq API key",
            value=os.getenv("GROQ_API_KEY", ""),
            type="password",
            disabled=not use_groq,
            help="Used only for this running app process; never written to disk.",
        )
        groq_model = st.text_input(
            "Groq model",
            value=os.getenv("GROQ_MODEL", ReasoningAgent.DEFAULT_MODEL),
            disabled=not use_groq,
        )
        st.caption(
            "Privacy note: profile details are sent to Groq only when this toggle "
            "is on and an API key is configured."
        )

    return {
        "top_k": top_k,
        "embedding_model": embedding_model.strip() or EmbeddingAgent.DEFAULT_MODEL,
        "use_groq": use_groq,
        "groq_key": groq_key.strip(),
        "groq_model": groq_model.strip() or ReasoningAgent.DEFAULT_MODEL,
    }


def build_profile() -> Any:
    """Run the deterministic Profile Analyzer over the current form state."""

    return ProfileAnalyzer().analyze(
        skills=st.session_state.profile_skills,
        experience_level=st.session_state.experience_level,
        years_experience=st.session_state.years_experience,
        target_roles=st.session_state.target_roles,
        preferred_locations=st.session_state.preferred_locations,
        work_preferences=st.session_state.work_preferences,
        professional_summary=st.session_state.professional_summary,
    )


def run_agentic_workflow(settings: dict[str, Any], jobs: list[dict[str, Any]]) -> None:
    """Orchestrate the specialist hand-offs and persist their combined output."""

    try:
        profile = build_profile()
    except ValueError as exc:
        st.error(str(exc), icon="⚠️")
        return

    with st.status("Specialist agents are working…", expanded=True) as status:
        st.write("**01 · Profile Analyzer** normalized skills, goals, and constraints.")
        matcher = get_embedding_agent(settings["embedding_model"])
        try:
            ranked_jobs = matcher.rank_jobs(
                profile.to_embedding_text(), jobs, top_k=settings["top_k"]
            )
        except Exception as exc:
            status.update(label="Matching stopped", state="error")
            st.error(
                "The embedding model could not run. Confirm dependencies are "
                f"installed and the model can be downloaded. ({type(exc).__name__})"
            )
            return
        st.write(
            "**02 · Semantic Matcher** embedded the profile and postings, then "
            "ranked them with cosine similarity."
        )

        reasoning_agent = ReasoningAgent(
            api_key=settings["groq_key"] if settings["use_groq"] else "",
            model=settings["groq_model"],
        )
        results: list[dict[str, Any]] = []
        for job in ranked_jobs:
            explanation = reasoning_agent.explain(
                profile, job, float(job["match_score"])
            )
            results.append({"job": job, "explanation": explanation})
        st.write(
            "**03 · Reasoning Agent** produced evidence, gaps, and a next action "
            "for every shortlisted role."
        )
        status.update(label="Agent hand-off complete", state="complete", expanded=False)

    st.session_state.match_results = {
        "profile": profile,
        "items": results,
        "embedding_model": settings["embedding_model"],
    }


def render_landing() -> None:
    """Explain the workflow before the first run."""

    st.markdown('<div class="section-kicker">Three specialist hand-offs</div>', unsafe_allow_html=True)
    st.subheader("A shortlist you can interrogate")
    columns = st.columns(3, gap="medium")
    cards = [
        (
            "01 / Structure",
            "Profile Analyzer",
            "Turns your raw skills, experience, and constraints into a stable candidate document.",
        ),
        (
            "02 / Retrieve",
            "Semantic Matcher",
            "Compares meaning—not just keywords—using MiniLM embeddings and cosine similarity.",
        ),
        (
            "03 / Explain",
            "Reasoning Agent",
            "Surfaces supporting evidence, honest gaps, and one concrete next move for each role.",
        ),
    ]
    for column, (number, title, copy) in zip(columns, cards):
        with column:
            st.markdown(
                f"""
                <div class="agent-step">
                    <span class="agent-number">{number}</span>
                    <strong>{title}</strong>
                    <p>{copy}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
    st.info(
        "Start with the sample profile or add your own details in the sidebar. "
        "The first run downloads the embedding model and may take a minute.",
        icon="🔎",
    )


def explanation_bullets(items: tuple[str, ...]) -> None:
    """Render model text as escaped Streamlit content rather than raw HTML."""

    for item in items:
        st.write(f"• {item}")


def render_results() -> None:
    """Render ranked cards and an exportable audit summary."""

    run = st.session_state.match_results
    if not run:
        render_landing()
        return

    items = run["items"]
    best_score = round(items[0]["job"]["match_score"] * 100) if items else 0
    sources = {item["explanation"].source for item in items}
    has_groq = any(source.startswith("Groq") for source in sources)
    has_fallback = any(source == "Local evidence fallback" for source in sources)
    if has_groq and has_fallback:
        reasoning_mode = "Mixed"
    elif has_groq:
        reasoning_mode = "Groq"
    else:
        reasoning_mode = "Local evidence"

    st.markdown('<div class="section-kicker">Shortlist generated</div>', unsafe_allow_html=True)
    st.subheader("Your strongest signals")
    metric_cols = st.columns(3)
    metric_cols[0].metric("Top semantic alignment", f"{best_score}%")
    metric_cols[1].metric("Roles shortlisted", len(items))
    metric_cols[2].metric("Reasoning mode", reasoning_mode)

    with st.expander("Inspect the agent trace and scoring boundary"):
        st.write(
            "Profile Analyzer → Hugging Face embedding model → cosine similarity "
            "ranking → job-specific reasoning. The displayed percentage is cosine "
            "alignment transformed to a 0–100 display—not a probability of an "
            "interview, an assessment of personal worth, or an automated hiring decision."
        )
        st.code(run["profile"].to_embedding_text(), language="text")
        st.caption(f"Embedding model: {run['embedding_model']}")

    for item in items:
        job = item["job"]
        explanation: FitExplanation = item["explanation"]
        score = float(job["match_score"])
        with st.container(border=True):
            heading, score_col = st.columns([5, 1.25], vertical_alignment="top")
            with heading:
                st.markdown(
                    f'<span class="rank-stamp">Rank {job["match_rank"]:02d} · '
                    f'{escape(str(job["work_mode"]))}</span>',
                    unsafe_allow_html=True,
                )
                st.subheader(job["title"])
                st.write(
                    f"**{job['company']}** · {job['location']} · "
                    f"{job['experience_level']} · {job['employment_type']}"
                )
                st.caption(f"Mock salary range: {job['salary_range']}")
            with score_col:
                st.markdown('<div class="score-label">Semantic match</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="score-number">{score:.0%}</div>',
                    unsafe_allow_html=True,
                )
            st.progress(score)

            st.markdown(
                f'<span class="source-note">Explanation: '
                f'{escape(explanation.source)}</span>',
                unsafe_allow_html=True,
            )
            st.write(explanation.summary)
            if explanation.warning:
                st.warning(explanation.warning, icon="🔄")

            strengths_col, gaps_col = st.columns(2, gap="large")
            with strengths_col:
                st.markdown("#### Evidence of fit")
                explanation_bullets(explanation.matched_strengths)
            with gaps_col:
                st.markdown("#### Questions to resolve")
                explanation_bullets(explanation.skill_gaps)

            st.markdown("#### Recommended next move")
            st.success(explanation.next_step, icon="➡️")

            with st.expander("Read the full mock posting"):
                st.write(job["description"])
                st.markdown("**Responsibilities**")
                for responsibility in job.get("responsibilities", []):
                    st.write(f"• {responsibility}")
                st.markdown("**Required skills**")
                st.write(" · ".join(job.get("required_skills", [])))
                preferred = job.get("preferred_skills", [])
                if preferred:
                    st.markdown("**Preferred skills**")
                    st.write(" · ".join(preferred))

    export_rows = [
        {
            "rank": item["job"]["match_rank"],
            "title": item["job"]["title"],
            "company": item["job"]["company"],
            "location": item["job"]["location"],
            "semantic_match_percent": round(item["job"]["match_score"] * 100, 1),
            "reasoning_source": item["explanation"].source,
            "summary": item["explanation"].summary,
            "next_step": item["explanation"].next_step,
        }
        for item in items
    ]
    csv_bytes = pd.DataFrame(export_rows).to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download shortlist audit (.csv)",
        data=csv_bytes,
        file_name="rolesignal_shortlist.csv",
        mime="text/csv",
        use_container_width=True,
    )


inject_styles()
initialize_state()
jobs = load_jobs()
settings = render_sidebar()

st.markdown(
    f"""
    <section class="hero">
        <div class="eyebrow">Agentic job intelligence · Human decision</div>
        <h1>Find the signal<br>in the job noise.</h1>
        <div class="hero-copy">
            A transparent specialist-agent workflow that retrieves promising roles,
            shows its evidence, and leaves the application decision with you.
        </div>
        <div class="proof-strip">
            <span class="proof-chip">{len(jobs)} detailed mock roles</span>
            <span class="proof-chip">Local semantic ranking</span>
            <span class="proof-chip">Optional Groq reasoning</span>
            <span class="proof-chip">Human-in-the-loop by design</span>
        </div>
    </section>
    """,
    unsafe_allow_html=True,
)

if st.button("Run agentic match", type="primary", use_container_width=True):
    run_agentic_workflow(settings, jobs)

render_results()

st.markdown(
    """
    <div class="fine-print">
        RoleSignal is an educational decision-support prototype using fictional job
        postings. Verify every opportunity independently. Match scores and AI text
        should support—not replace—human judgment.
    </div>
    """,
    unsafe_allow_html=True,
)
