"""JobPilot — evidence-grounded, self-correcting job matching agent (Streamlit entry point).

Run:  streamlit run app.py
"""

from __future__ import annotations

import streamlit as st

st.set_page_config(page_title="JobPilot · 求职匹配 Agent", page_icon="🧭", layout="wide", initial_sidebar_state="expanded")

from ui import runner, state, styles  # noqa: E402
from ui.i18n import t  # noqa: E402
from ui.nav import register  # noqa: E402
from ui.views import home, matches, pipeline, profile, reports, run, settings  # noqa: E402

state.init()
styles.inject()

pages = {
    "home": st.Page(home.render_page, title=t("nav.home"), icon="🏠", url_path="home", default=True),
    "profile": st.Page(profile.render, title=t("nav.profile"), icon="🧭", url_path="profile"),
    "run": st.Page(run.render_page, title=t("nav.run"), icon="🚀", url_path="run"),
    "matches": st.Page(matches.render_page, title=t("nav.matches"), icon="🎯", url_path="matches"),
    "pipeline": st.Page(pipeline.render_page, title=t("nav.pipeline"), icon="📋", url_path="pipeline"),
    "reports": st.Page(reports.render_page, title=t("nav.reports"), icon="📊", url_path="reports"),
    "settings": st.Page(settings.render_page, title=t("nav.settings"), icon="⚙️", url_path="settings"),
}
for key, page in pages.items():
    register(key, page)

# Grouped sidebar navigation: the order of the sections is the order of the job hunt.
nav = st.navigation({
    t("navsec.start"): [pages["home"], pages["profile"]],
    t("navsec.search"): [pages["run"], pages["matches"]],
    t("navsec.track"): [pages["pipeline"], pages["reports"]],
    t("navsec.system"): [pages["settings"]],
}, position="sidebar")

# Status lives under the nav: which mode we're in, and whether a run is in flight.
with st.sidebar:
    st.session_state["lang_toggle"] = state.lang()

    def _set_lang() -> None:
        chosen = st.session_state.get("lang_toggle")
        if chosen:
            st.session_state.lang = chosen
            state.get_db().kv_set("ui_lang", chosen)

    st.segmented_control("Language", ["zh", "en"], format_func=lambda x: "中文" if x == "zh" else "English",
                         key="lang_toggle", label_visibility="collapsed", on_change=_set_lang)
    st.caption(("🔑 " + t("side.live", model=st.session_state.model)) if state.has_key() else ("🧪 " + t("side.demo")))
    handle = runner.current()
    if handle and handle.running:
        st.info("🟢 " + t("side.running"))

nav.run()
