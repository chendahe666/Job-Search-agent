"""Home: one screen that answers "what do I do next?" and nothing else."""

from __future__ import annotations

import streamlit as st

from ui import state
from ui.i18n import t
from ui.nav import go


def _next_step(prof, prefs, latest) -> tuple[str, dict, str, int | None]:
    """Return (string prefix, body params, target page, wizard step to deep-link into)."""
    if not prof.is_ready():
        return "home.step1", {}, "profile", 0
    if prefs.validation_errors():
        return "home.step2", {}, "profile", 1
    if latest is None:
        return "home.step3", {}, "run", None
    return "home.done", {"a": latest.tier_counts.get("A", 0), "b": latest.tier_counts.get("B", 0)}, "matches", None


def render_page() -> None:
    prof, prefs = state.profile(), state.prefs()
    db = state.get_db()
    latest = db.latest_run()

    st.title(t("home.title"))
    st.markdown(f'<div class="jp-sub">{t("home.subtitle")}</div>', unsafe_allow_html=True)

    key, params, target, wizard_step = _next_step(prof, prefs, latest)
    with st.container(border=True):
        st.markdown(f'<div class="jp-kpi-label">{t("home.next")}</div>', unsafe_allow_html=True)
        st.markdown(f"### {t(key + '.title')}")
        st.markdown(f'<div class="jp-sub">{t(key + ".body", **params)}</div>', unsafe_allow_html=True)
        if st.button(t(key + ".cta") + "  →", type="primary", key="home_cta"):
            if wizard_step is not None:
                st.session_state.wizard_step = wizard_step
                st.session_state.wizard_max_step = max(st.session_state.get("wizard_max_step", 0), wizard_step)
            go(target)

    done_resume, done_targets = prof.is_ready(), not prefs.validation_errors()
    st.markdown(f"**{t('home.progress')}**")
    for ok, text in ((done_resume, t("home.chk_resume")), (done_targets, t("home.chk_targets")),
                     (latest is not None, t("home.chk_run"))):
        st.markdown(("✅ " if ok else "⬜ ") + text)

    if latest is not None:
        runs = db.list_runs(limit=50)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric(t("home.kpi_a"), latest.tier_counts.get("A", 0))
        k2.metric(t("home.kpi_b"), latest.tier_counts.get("B", 0))
        k3.metric(t("home.kpi_pipeline"), len(db.pipeline()))
        k4.metric(t("home.kpi_runs"), len(runs))

    st.caption(t("home.mode_live") if state.has_key() else t("home.mode_demo"))
    with st.expander(t("home.how")):
        st.markdown(t("review.how_steps"))
