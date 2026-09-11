"""Page registry so any view can navigate to another."""

from __future__ import annotations

import streamlit as st

PAGES: dict[str, object] = {}


def register(key: str, page: object) -> None:
    PAGES[key] = page


def go(key: str) -> None:
    page = PAGES.get(key)
    if page is not None:
        st.switch_page(page)
