"""API key, models, data import, reset."""

from __future__ import annotations

import streamlit as st

from jobpilot.agent.intel import CompanyIntelService
from jobpilot.llm.gemini import FALLBACK_MODELS, GeminiClient, GeminiError
from ui import state
from ui.i18n import t


def render_page() -> None:
    db = state.get_db()
    st.title(t("settings.title"))
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(border=True):
            st.markdown(f"**🔑 {t('settings.gemini')}**")
            st.caption(t("settings.key_help"))
            key = st.text_input("GEMINI_API_KEY", st.session_state.api_key, type="password")
            if key != st.session_state.api_key:
                st.session_state.api_key = key.strip()
            models = st.session_state.get("available_models") or list(dict.fromkeys([st.session_state.model] + FALLBACK_MODELS))
            model = st.selectbox(t("settings.model"), models, index=models.index(st.session_state.model) if st.session_state.model in models else 0,
                                 help=t("settings.model_help"))
            embed_models = ["gemini-embedding-001", "gemini-embedding-2"]
            embed = st.selectbox(t("settings.embed_model"), embed_models,
                                 index=embed_models.index(st.session_state.embed_model) if st.session_state.embed_model in embed_models else 0)
            if model != st.session_state.model or embed != st.session_state.embed_model:
                st.session_state.model, st.session_state.embed_model = model, embed
                state.save_settings()
            a, b = st.columns(2)
            if a.button(t("settings.test"), width="stretch", disabled=not state.has_key()):
                try:
                    client = GeminiClient(st.session_state.api_key, st.session_state.model, max_retries=1)
                    names = client.generation_models()
                    st.session_state.available_models = [n for n in names if n.startswith("gemini")] or models
                    resp = client.generate("Reply with the single word OK.", temperature=0)
                    st.success(t("settings.test_ok", n=len(names), reply=resp.text.strip()[:20]))
                except GeminiError as exc:
                    st.error(f"{type(exc).__name__}: {exc}")
            if b.button(t("settings.save_env"), width="stretch", disabled=not state.has_key()):
                path = state.write_env_key("GEMINI_API_KEY", st.session_state.api_key)
                state.write_env_key("GEMINI_MODEL", st.session_state.model)
                st.success(t("settings.saved_env", path=str(path)))
            st.caption(t("settings.privacy"))
    with c2:
        with st.container(border=True):
            st.markdown(f"**🛂 {t('settings.uscis')}**")
            st.caption(t("settings.uscis_help"))
            up = st.file_uploader("CSV", type=["csv", "tsv", "txt"], key="uscis_csv")
            if up and st.button(t("settings.import")):
                n = CompanyIntelService(db).import_uscis_csv(up.getvalue())
                (st.success if n else st.error)(t("settings.imported", n=n))
        with st.container(border=True):
            st.markdown(f"**🧹 {t('settings.data')}**")
            st.caption(t("settings.data_help"))
            a, b, c = st.columns(3)
            if a.button(t("settings.reset_jobs"), width="stretch"):
                db.reset("jobs")
                st.toast(t("common.done"))
            if b.button(t("settings.reset_profile"), width="stretch"):
                db.reset("profile")
                for k in ("profile", "prefs", "run_config"):
                    st.session_state.pop(k, None)
                st.toast(t("common.done"))
                st.rerun()
            if c.button(t("settings.reset_all"), width="stretch", type="primary"):
                db.reset("all")
                for k in ("profile", "prefs", "run_config", "selected_job"):
                    st.session_state.pop(k, None)
                st.toast(t("common.done"))
                st.rerun()
