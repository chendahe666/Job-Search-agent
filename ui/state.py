"""Session/app state helpers shared by all pages."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import streamlit as st

from jobpilot.llm.gemini import DEFAULT_EMBED_MODEL, DEFAULT_MODEL, GeminiClient
from jobpilot.schemas import CandidateProfile, RunConfig, SearchPreferences
from jobpilot.storage.db import Database

ROOT = Path(__file__).resolve().parents[1]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # python-dotenv is optional
    pass


@st.cache_resource(show_spinner=False)
def get_db() -> Database:
    return Database(os.getenv("JOBPILOT_DB") or ROOT / ".jobpilot" / "jobpilot.db")


def init() -> None:
    db = get_db()
    ss = st.session_state
    if "lang" not in ss:
        ss.lang = db.kv_get("ui_lang", "zh")
    if "api_key" not in ss:
        ss.api_key = os.getenv("GEMINI_API_KEY", "")
    settings = db.kv_get("settings", {}) or {}
    ss.setdefault("model", settings.get("model") or os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
    ss.setdefault("embed_model", settings.get("embed_model") or os.getenv("GEMINI_EMBED_MODEL", DEFAULT_EMBED_MODEL))
    ss.setdefault("wizard_step", 0)
    ss.setdefault("wizard_max_step", 0)
    ss.setdefault("selected_job", None)
    if "profile" not in ss:
        ss.profile = db.load_profile() or CandidateProfile()
    if "prefs" not in ss:
        ss.prefs = db.load_preferences() or SearchPreferences()
    if "run_config" not in ss:
        ss.run_config = db.load_run_config()


def lang() -> str:
    return st.session_state.get("lang", "zh")


def profile() -> CandidateProfile:
    return st.session_state.profile


def prefs() -> SearchPreferences:
    return st.session_state.prefs


def run_config() -> RunConfig:
    return st.session_state.run_config


def save_profile(p: CandidateProfile) -> None:
    st.session_state.profile = p
    get_db().save_profile(p)


def save_prefs(p: SearchPreferences) -> None:
    st.session_state.prefs = p
    get_db().save_preferences(p)


def save_run_config(c: RunConfig) -> None:
    st.session_state.run_config = c
    get_db().save_run_config(c)


def save_settings() -> None:
    get_db().kv_set("settings", {"model": st.session_state.model, "embed_model": st.session_state.embed_model})


def has_key() -> bool:
    return bool(st.session_state.get("api_key", "").strip())


def llm_client() -> Optional[GeminiClient]:
    if not has_key():
        return None
    return GeminiClient(st.session_state.api_key, st.session_state.model, embed_model=st.session_state.embed_model)


def write_env_key(key: str, value: str) -> Path:
    path = ROOT / ".env"
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, found = [], False
    for ln in lines:
        if ln.strip().startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


def get(key: str, default: Any = None) -> Any:
    return st.session_state.get(key, default)
