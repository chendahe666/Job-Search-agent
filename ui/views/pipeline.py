"""Application tracker (kanban)."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from jobpilot.storage.db import PIPELINE_STATUSES
from ui import components as C
from ui import state
from ui.i18n import t

BOARD = ["saved", "applying", "applied", "interview", "offer", "rejected"]


def render_page() -> None:
    db = state.get_db()
    st.title(t("pipeline.title"))
    st.markdown(f'<div class="jp-sub">{t("pipeline.subtitle")}</div>', unsafe_allow_html=True)
    items = db.pipeline()
    if not items:
        C.empty_state(t("pipeline.empty"))
        return
    jobs = {jid: db.get_job(jid) for jid in items}
    view = st.segmented_control(t("pipeline.view"), ["board", "table"], default="board", format_func=lambda v: t("pipeline.view_" + v))
    if view == "table":
        rows = []
        for jid, it in items.items():
            j = jobs.get(jid)
            rows.append({t("pipeline.col_status"): t("pipe." + it["status"]), t("pipeline.col_role"): j.title if j else jid,
                         t("pipeline.col_company"): j.company if j else "", t("pipeline.notes"): it.get("notes", ""),
                         t("pipeline.col_updated"): it.get("updated_at", "")[:16], "URL": (j.apply_url or j.url) if j else ""})
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, width="stretch", column_config={"URL": st.column_config.LinkColumn()})
        st.download_button(t("pipeline.export"), df.to_csv(index=False).encode("utf-8"), "jobpilot_pipeline.csv", "text/csv")
        return
    cols = st.columns(len(BOARD), gap="small")
    for col, status in zip(cols, BOARD):
        entries = [(jid, it) for jid, it in items.items() if it["status"] == status]
        with col:
            st.markdown(f"**{t('pipe.' + status)}** · {len(entries)}")
            for jid, it in entries:
                j = jobs.get(jid)
                with st.container(border=True):
                    C.html(f'<div class="jp-card-title" style="font-size:.9rem">{escape(j.title if j else jid)}</div>'
                           f'<div class="jp-card-meta">{escape(j.company if j else "")}</div>')
                    if it.get("notes"):
                        st.caption(it["notes"][:120])
                    new = st.selectbox(t("pipeline.move"), PIPELINE_STATUSES, index=PIPELINE_STATUSES.index(status),
                                       format_func=lambda s: t("pipe." + s), key=f"mv_{jid}", label_visibility="collapsed")
                    if new != status:
                        db.set_pipeline(jid, new, it.get("notes", ""), it.get("next_action", ""))
                        st.rerun()
                    if j and (j.apply_url or j.url).startswith("http"):
                        st.link_button("↗", j.apply_url or j.url, width="stretch")
    archived = [jid for jid, it in items.items() if it["status"] == "archived"]
    if archived:
        st.caption(t("pipeline.archived", n=len(archived)))
