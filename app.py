"""JobPilot — evidence-grounded, self-correcting job matching agent (Streamlit entry point).

Run:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="JobPilot · 求职匹配 Agent", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")

from ui import runner, state, styles  # noqa: E402
from ui.i18n import t  # noqa: E402
from ui.nav import register  # noqa: E402
from ui.views import matches, pipeline, profile, reports, run, settings  # noqa: E402

state.init()
styles.inject()

with st.sidebar:
    st.markdown("## 🧭 JobPilot")
    st.session_state["lang_toggle"] = state.lang()

    def _set_lang() -> None:
        chosen = st.session_state.get("lang_toggle")
        if chosen:
            st.session_state.lang = chosen
            state.get_db().kv_set("ui_lang", chosen)

    st.segmented_control("Language", ["zh", "en"], format_func=lambda x: "中文" if x == "zh" else "English",
                         key="lang_toggle", label_visibility="collapsed", on_change=_set_lang)
    prof, prefs = state.profile(), state.prefs()
    done = sum([prof.is_ready(), bool(prefs.target_titles), bool(prefs.seniority and prefs.work_modes)])
    st.progress(done / 3, text=t("side.setup", n=done))
    st.caption(("🔑 " + t("side.live", model=st.session_state.model)) if state.has_key() else ("🧪 " + t("side.demo")))
    handle = runner.current()
    if handle and handle.running:
        st.info("🟢 " + t("side.running"))
    else:
        latest = state.get_db().latest_run()
        if latest:
            st.caption(t("side.latest", a=latest.tier_counts.get("A", 0), b=latest.tier_counts.get("B", 0), status=latest.status))

# Decide the landing page once per session so it never flips while the user is mid-wizard.
if "landing" not in st.session_state:
    st.session_state.landing = "matches" if (prof.is_ready() and prefs.target_titles and state.get_db().latest_run()) else "profile"
landing = st.session_state.landing

pages = {
    "profile": st.Page(profile.render, title=t("nav.profile"), icon="🧭", url_path="profile", default=landing == "profile"),
    "run": st.Page(run.render_page, title=t("nav.run"), icon="🚀", url_path="run"),
    "matches": st.Page(matches.render_page, title=t("nav.matches"), icon="🎯", url_path="matches", default=landing == "matches"),
    "pipeline": st.Page(pipeline.render_page, title=t("nav.pipeline"), icon="📋", url_path="pipeline"),
    "reports": st.Page(reports.render_page, title=t("nav.reports"), icon="📊", url_path="reports"),
    "settings": st.Page(settings.render_page, title=t("nav.settings"), icon="⚙️", url_path="settings"),
}
for key, page in pages.items():
    register(key, page)

nav = st.navigation(list(pages.values()), position="top")
nav.run()
