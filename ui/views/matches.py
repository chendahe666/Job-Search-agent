"""Results: tiered, explainable shortlist with master–detail evidence view."""

from __future__ import annotations

from html import escape

import pandas as pd
import streamlit as st

from jobpilot.messages import label, render
from jobpilot.rag.embeddings import GeminiEmbedder, HashingEmbedder, ResilientEmbedder
from jobpilot.rag.retriever import HybridIndex
from jobpilot.report.tailor import tailor_application
from jobpilot.schemas import EvidenceStatus, MatchResult, SponsorshipStatus, Tier, VerificationStatus, WorkMode
from ui import components as C
from ui import runner, state
from ui.i18n import t
from ui.nav import go

FEEDBACK_REASONS = ["location", "seniority", "domain", "company", "salary", "sponsorship", "stack", "other"]


def _runs():
    db = state.get_db()
    return [r for r in db.list_runs(30)]


def render_page() -> None:
    lang = state.lang()
    db = state.get_db()
    st.title(t("matches.title"))
    runs = _runs()
    handle = runner.current()
    if not runs:
        C.empty_state(t("matches.empty"))
        if st.button(t("matches.go_run"), type="primary"):
            go("run")
        return
    run_ids = [r.run_id for r in runs]
    default_idx = 0
    picked = st.selectbox(t("matches.run"), run_ids, index=default_idx,
                          format_func=lambda rid: _run_label(next(r for r in runs if r.run_id == rid), lang))
    report = next(r for r in runs if r.run_id == picked)
    if handle and handle.running and handle.live_report and handle.live_report.run_id == picked:
        st.info(t("matches.live_note"))
    matches = db.load_matches(picked)
    if not matches:
        C.empty_state(t("matches.none_in_run"))
        return

    prefs = state.prefs()
    counts = {tier: sum(1 for m in matches if m.tier == tier) for tier in Tier}
    tiers = st.pills(t("matches.tiers"), list(Tier), selection_mode="multi", default=[Tier.A, Tier.B],
                     format_func=lambda x: f"{t('tier.' + x.value)} · {counts[x]}", key=f"tier_filter_{picked}")
    f1, f2, f3, f4 = st.columns([3, 2, 2, 2])
    q = f1.text_input(t("matches.search"), placeholder=t("matches.search_ph"), label_visibility="collapsed")
    modes = f2.multiselect(t("matches.mode"), [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE, WorkMode.UNKNOWN],
                           format_func=lambda m: label(m, lang), placeholder=t("matches.mode"), label_visibility="collapsed")
    verified_only = f3.toggle(t("matches.verified_only"), value=False)
    sort = f4.selectbox(t("matches.sort"), ["score", "fresh", "company"], format_func=lambda s: t("sort." + s), label_visibility="collapsed")

    shown = [m for m in matches if (not tiers or m.tier in tiers)]
    if q:
        ql = q.lower()
        shown = [m for m in shown if ql in f"{m.job.title} {m.job.company} {m.job.location_text} {' '.join(r.text for r in m.job.requirements)}".lower()]
    if modes:
        shown = [m for m in shown if m.job.work_mode in modes]
    if verified_only:
        shown = [m for m in shown if m.job.verification.status in (VerificationStatus.VERIFIED, VerificationStatus.DEMO)]
    if sort == "fresh":
        shown.sort(key=lambda m: (m.job.age_days() is None, m.job.age_days() or 0))
    elif sort == "company":
        shown.sort(key=lambda m: m.job.company.lower())

    if report.suggestions and counts[Tier.A] + counts[Tier.B] < state.run_config().target_shortlist:
        with st.expander("💡 " + t("matches.why_few"), expanded=False):
            for s in report.suggestions:
                st.markdown("- " + render(s, lang))
            if st.button(t("matches.adjust_prefs")):
                st.session_state.wizard_step = 1
                go("profile")

    left, right = st.columns([5, 7], gap="large")
    selected_id = st.session_state.get("selected_job")
    if selected_id not in {m.job.id for m in shown}:
        selected_id = shown[0].job.id if shown else None
    pipeline = db.pipeline()
    feedback = db.feedback()
    with left:
        st.caption(t("matches.count", n=len(shown), total=len(matches)))
        with st.container(height=900, border=False):
            for m in shown[:150]:
                job_card(m, lang, prefs.needs_sponsorship, selected=m.job.id == selected_id, saved=m.job.id in pipeline,
                         verdict=feedback.get(m.job.id, {}).get("verdict"))
    with right:
        sel = next((m for m in shown if m.job.id == selected_id), None)
        if sel:
            detail(sel, lang)
        else:
            C.empty_state(t("matches.pick"))


def _run_label(r, lang: str) -> str:
    when = r.started_at.astimezone().strftime("%m-%d %H:%M")
    return f"{when} · {r.mode} · {r.status} · A{r.tier_counts.get('A', 0)} B{r.tier_counts.get('B', 0)} · {r.funnel.get('unique', 0)} {t('matches.postings')}"


def job_card(m: MatchResult, lang: str, needs: bool, *, selected: bool, saved: bool, verdict) -> None:
    db = state.get_db()
    j = m.job
    with st.container(border=True):
        a, b = st.columns([1, 4])
        with a:
            C.html(C.score_ring(m.total_score, m.tier))
        with b:
            age = j.age_days()
            meta = " · ".join(x for x in [j.company, j.location_text or "—", label(j.work_mode, lang) if j.work_mode != WorkMode.UNKNOWN else "",
                                          t("matches.age", n=age) if age is not None else ""] if x)
            C.html(f'<div class="jp-card-title">{"▶ " if selected else ""}{escape(j.title or "(untitled)")}</div><div class="jp-card-meta">{escape(meta)}</div>')
            C.html(C.verification_badge(j.verification.status, lang) + C.sponsorship_badge(m, lang, needs) + C.ghost_badge(m.ghost_risk, lang)
                   + (C.badge(t("matches.saved"), "brand", "📌") if saved else ""))
            if m.tier == Tier.REJECTED:
                for h in m.failed_rules[:2]:
                    C.html(f'<div class="jp-gapline">✕ {escape(render(h.reason, lang))}</div>')
            else:
                for r in m.reasons[:2]:
                    C.html(f'<div class="jp-reason">✓ {escape(render(r, lang))}</div>')
                if m.gaps:
                    C.html(f'<div class="jp-gapline">△ {escape(m.gaps[0][:90])}</div>')
        c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
        if c1.button(t("matches.details"), key=f"det_{m.job.id}", width="stretch", type="primary" if selected else "secondary"):
            st.session_state.selected_job = m.job.id
            st.rerun()
        if c2.button(("📌 " + t("matches.saved")) if saved else ("➕ " + t("matches.save")), key=f"save_{m.job.id}", width="stretch", disabled=saved):
            db.set_pipeline(m.job.id, "saved")
            st.toast(t("matches.saved_toast"), icon="📌")
            st.rerun()
        if c3.button("👍", key=f"up_{m.job.id}", width="stretch", type="primary" if verdict == 1 else "secondary"):
            db.set_feedback(m.job.id, 1, [])
            st.toast(t("matches.feedback_thanks"))
            st.rerun()
        with c4.popover("👎", width="stretch"):
            reasons = st.pills(t("matches.why_not"), FEEDBACK_REASONS, selection_mode="multi", format_func=lambda r: t("fb." + r), key=f"fbr_{m.job.id}")
            if st.button(t("common.submit"), key=f"down_{m.job.id}"):
                db.set_feedback(m.job.id, -1, list(reasons or []))
                if "company" in (reasons or []):
                    p = state.prefs()
                    if j.company and j.company not in p.company_blocklist:
                        state.save_prefs(p.model_copy(update={"company_blocklist": p.company_blocklist + [j.company]}))
                        st.toast(t("matches.blocked_company", company=j.company))
                st.rerun()


def detail(m: MatchResult, lang: str) -> None:
    j = m.job
    db = state.get_db()
    with st.container(border=True):
        top_l, top_r = st.columns([5, 2])
        with top_l:
            st.markdown(f"### {escape(j.title)}")
            st.caption(" · ".join(x for x in [j.company, j.location_text, label(j.work_mode, lang), label(j.employment_type, lang),
                                               label(j.seniority, lang), str(j.date_posted or "")] if x and x != label("unknown", lang)))
        with top_r:
            C.html(C.score_ring(m.total_score, m.tier))
            st.caption(t("detail.confidence", c=f"{m.confidence:.0%}"))
        link = j.apply_url or j.url
        if link.startswith("http"):
            st.link_button("↗ " + t("detail.open"), link, width="stretch")
        tabs = st.tabs([t("detail.tab_overview"), t("detail.tab_evidence"), t("detail.tab_verify"), t("detail.tab_jd"), t("detail.tab_apply")])
        with tabs[0]:
            c1, c2 = st.columns(2, gap="medium")
            with c1:
                st.markdown(f"**{t('detail.why')}**")
                for r in m.reasons:
                    st.markdown(f"✅ {render(r, lang)}")
                if m.risks:
                    st.markdown(f"**{t('detail.risks')}**")
                    for r in m.risks:
                        st.markdown(f"⚠️ {render(r, lang)}")
                if m.gaps:
                    st.markdown(f"**{t('detail.gaps')}**")
                    for g in m.gaps:
                        st.markdown(f"△ {g}")
            with c2:
                st.markdown(f"**{t('detail.breakdown')}**")
                C.dimension_bars(m, lang)
                st.caption(t("detail.breakdown_note"))
            st.markdown(f"**{t('detail.hard_filters')}**")
            C.hard_filter_list(m.hard_filters, lang)
        with tabs[1]:
            st.caption(t("detail.evidence_note"))
            rows = []
            for e in m.evidence:
                rows.append({
                    t("ev.req"): e.requirement_text, t("ev.kind"): t("ev." + e.kind.value), t("ev.status"): label(e.status, lang),
                    t("ev.quote"): e.quote, t("ev.source"): f"{e.source_label} [{e.chunk_id}]" if e.chunk_id else e.source_label,
                    t("ev.method"): e.method, t("ev.why"): e.rationale,
                })
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df, hide_index=True, width="stretch", height=min(40 + 36 * len(rows), 620),
                             column_config={t("ev.req"): st.column_config.TextColumn(width="medium"), t("ev.quote"): st.column_config.TextColumn(width="large")})
            else:
                st.info(t("detail.no_requirements"))
            met = sum(1 for e in m.evidence if e.status == EvidenceStatus.MET)
            unv = sum(1 for e in m.evidence if e.status == EvidenceStatus.UNVERIFIED)
            st.caption(t("detail.evidence_summary", met=met, total=len(m.evidence), unverified=unv))
        with tabs[2]:
            v = j.verification
            C.html(C.verification_badge(v.status, lang) + C.badge(f"source: {j.source}", "gray") + C.badge(f"extract: {j.extraction_method}", "gray"))
            for c in v.checks:
                icon = "✅" if c.passed else "❌" if c.passed is False else "❔"
                st.markdown(f"{icon} **{c.name}** — {c.detail}")
            if j.sponsorship.status != SponsorshipStatus.UNKNOWN:
                st.markdown(f"**🛂 {label(j.sponsorship.status, lang)}**")
                C.html(f'<div class="jp-quote">“{escape(j.sponsorship.quote)}”</div>')
            if m.company_intel:
                st.markdown(f"**{t('detail.intel')}**: {label(m.company_intel.sponsorship, lang)} — {m.company_intel.note}")
                if m.company_intel.source_url.startswith("http"):
                    st.caption(m.company_intel.source_url)
            st.markdown(f"**👻 {t('detail.ghost')}: {label(m.ghost_risk, lang)}**")
            for g in m.ghost_signals:
                st.markdown(f"- {render(g, lang)}")
        with tabs[3]:
            if j.responsibilities:
                st.markdown(f"**{t('detail.responsibilities')}**")
                for r in j.responsibilities:
                    st.markdown(f"- {r}")
            st.text_area(t("detail.full_jd"), j.description_text or "—", height=420, disabled=True, key=f"jd_{j.id}")
        with tabs[4]:
            pipe = db.pipeline().get(j.id, {})
            from jobpilot.storage.db import PIPELINE_STATUSES
            s1, s2 = st.columns([1, 2])
            cur = pipe.get("status") or "saved"
            status = s1.selectbox(t("pipeline.status"), PIPELINE_STATUSES, index=PIPELINE_STATUSES.index(cur), format_func=lambda s: t("pipe." + s), key=f"ps_{j.id}")
            notes = s2.text_input(t("pipeline.notes"), pipe.get("notes", ""), key=f"pn_{j.id}")
            if st.button(t("common.save"), key=f"psave_{j.id}"):
                db.set_pipeline(j.id, status, notes)
                st.toast(t("common.saved"), icon="💾")
            st.divider()
            st.markdown(f"**✍️ {t('apply.title')}**")
            st.caption(t("apply.caption"))
            if st.button(t("apply.generate"), key=f"tailor_{j.id}", type="primary"):
                with st.spinner(t("apply.generating")):
                    prof = state.profile()
                    llm = state.llm_client()
                    embedder = ResilientEmbedder(GeminiEmbedder(llm, db) if llm else None, HashingEmbedder())
                    index = HybridIndex.for_profile(prof, embedder, db)
                    st.session_state[f"tailor_result_{j.id}"] = tailor_application(m, index, prof, llm, lang)
            result = st.session_state.get(f"tailor_result_{j.id}")
            if result:
                st.caption(t("apply.method", method=result.method))
                for b in result.bullets:
                    if b.verified:
                        st.markdown(f"✅ {b.text}  \n<span style='color:#94a3b8;font-size:.75rem'>{', '.join(b.chunk_ids)}</span>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"⚠️ ~~{b.text}~~  \n<span style='color:#b45309;font-size:.78rem'>{t('apply.rejected')}: {'; '.join(b.problems)}</span>", unsafe_allow_html=True)
                st.text_area(t("apply.pitch"), result.pitch, height=110, key=f"pitch_{j.id}")
                if result.keywords:
                    st.markdown(t("apply.keywords") + " " + " ".join(C.badge(k, "brand") for k in result.keywords), unsafe_allow_html=True)
