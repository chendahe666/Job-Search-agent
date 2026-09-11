"""Run history: funnel, iterations, issues, exports."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from jobpilot.messages import label, render
from jobpilot.report.exporter import matches_csv, run_markdown
from ui import components as C
from ui import state
from ui.i18n import t


def render_page() -> None:
    lang = state.lang()
    db = state.get_db()
    st.title(t("reports.title"))
    runs = db.list_runs(50)
    if not runs:
        C.empty_state(t("reports.empty"))
        return
    table = pd.DataFrame([{
        "run": r.run_id, t("reports.col_started"): r.started_at.astimezone().strftime("%Y-%m-%d %H:%M"), t("reports.col_mode"): r.mode,
        t("reports.col_status"): r.status, t("reports.col_stop"): label(r.stop_reason, lang) if r.stop_reason else "",
        t("reports.col_iters"): len(r.iterations), "A": r.tier_counts.get("A", 0), "B": r.tier_counts.get("B", 0),
        t("reports.col_unique"): r.funnel.get("unique", 0), t("reports.col_cost"): round(r.usage.estimated_cost_usd(), 3),
    } for r in runs])
    st.dataframe(table, hide_index=True, width="stretch")
    rid = st.selectbox(t("reports.pick"), [r.run_id for r in runs])
    report = next(r for r in runs if r.run_id == rid)
    matches = db.load_matches(rid)

    k = st.columns(5)
    for col, (name, key) in zip(k, [("funnel.leads", "leads"), ("funnel.unique", "unique"), ("funnel.verified", "verified"),
                                     ("funnel.passed", "hard_passed"), ("funnel.shortlisted", "shortlisted")]):
        col.metric(t(name), report.funnel.get(key, 0))
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        st.markdown(f"**{t('run.iterations')}**")
        for it in report.iterations:
            with st.container(border=True):
                st.markdown(t("run.iteration_title", n=it.number, leads=it.leads, unique=it.new_unique, short=it.shortlisted) + f" · {it.seconds}s")
                st.caption(" | ".join(it.tasks))
                if it.rejection_reasons:
                    C.html(" ".join(C.badge(f"{label(k_, lang)} × {v}", "red") for k_, v in it.rejection_reasons.items()))
                for d in it.diagnosis:
                    st.markdown(f"🩺 {render(d, lang)}")
                for a in it.actions:
                    st.markdown(f"🔧 {render(a, lang)}")
    with c2:
        st.markdown(f"**{t('reports.usage')}**")
        u = report.usage
        st.markdown(t("reports.usage_detail", llm=u.llm_calls, fail=u.llm_failures, q=u.search_queries, calls=u.search_calls,
                      tokens=f"{u.prompt_tokens + u.output_tokens:,}", fetch=u.http_fetches, cost=f"{u.estimated_cost_usd():.3f}"))
        if report.suggestions:
            st.markdown(f"**💡 {t('run.suggestions')}**")
            for s in report.suggestions:
                st.markdown("- " + render(s, lang))
        st.markdown(f"**{t('reports.export')}**")
        md = run_markdown(report, matches, state.profile(), state.prefs(), lang)
        st.download_button("⬇️ Markdown", md.encode("utf-8"), f"jobpilot_{rid}.md", "text/markdown", width="stretch")
        st.download_button("⬇️ CSV", matches_csv(matches, lang).encode("utf-8"), f"jobpilot_{rid}.csv", "text/csv", width="stretch")
    if report.issues:
        st.markdown(f"**⚠️ {t('run.issues')}**")
        st.dataframe(pd.DataFrame([{"stage": label(i.stage, lang), "severity": i.severity, "message": i.message, "resolution": i.resolution,
                                    "time": i.ts.astimezone().strftime("%H:%M:%S")} for i in report.issues]), hide_index=True, width="stretch")
    with st.expander(t("reports.events")):
        events = db.events(rid)
        st.dataframe(pd.DataFrame(events), hide_index=True, width="stretch", height=380)
    with st.expander(t("reports.preview_md")):
        st.markdown(md)
