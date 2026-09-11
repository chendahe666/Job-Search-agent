"""Mission control: start the agent, watch each stage live, stop safely."""

from __future__ import annotations

import time
from html import escape

import streamlit as st

from jobpilot.messages import label, render
from jobpilot.schemas import RunConfig
from ui import components as C
from ui import runner, state
from ui.i18n import t
from ui.nav import go

STAGES = ["read", "plan", "search", "work", "verify", "evaluate", "reflect", "report"]
STAGE_ICON = {"read": "📄", "plan": "🗺️", "search": "🔎", "work": "🛠️", "verify": "🛡️", "evaluate": "⚖️", "reflect": "🔁", "report": "📊", "agent": "🤖"}


def render_page() -> None:
    lang = state.lang()
    st.title(t("run.title"))
    st.markdown(f'<div class="jp-sub">{t("run.subtitle")}</div>', unsafe_allow_html=True)
    handle = runner.current()
    if handle and handle.running:
        live_panel()
        return
    readiness_and_launch(lang)
    if handle:
        st.divider()
        panel_body()


def readiness_and_launch(lang: str) -> None:
    prof, prefs = state.profile(), state.prefs()
    cfg: RunConfig = state.run_config()
    checks = [
        (prof.is_ready(), t("run.check_profile"), "profile"),
        (not prefs.validation_errors(), t("run.check_prefs"), "profile"),
        (state.has_key(), t("run.check_key") if state.has_key() else t("run.check_demo"), "settings"),
    ]
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        with st.container(border=True):
            st.markdown(f"**{t('run.readiness')}**")
            for ok, text, target in checks:
                a, b = st.columns([6, 1])
                a.markdown(("✅ " if ok else "⚠️ ") + text)
                if not ok and b.button(t("common.fix"), key=f"fix_{text}"):
                    go(target)
        with st.expander("⚙️ " + t("run.budget"), expanded=False):
            a, b = st.columns(2)
            max_iter = a.slider(t("run.max_iterations"), 1, 5, cfg.max_iterations, help=t("run.max_iterations_help"))
            target = b.slider(t("run.target_shortlist"), 3, 30, cfg.target_shortlist, help=t("run.target_help"))
            calls = a.slider(t("run.max_search_calls"), 2, 30, cfg.max_search_calls, help=t("run.max_search_calls_help"))
            per_iter = b.slider(t("run.max_jobs"), 10, 60, cfg.max_jobs_per_iteration, 5)
            intel = a.toggle(t("run.company_intel"), cfg.company_intel, help=t("run.company_intel_help"))
            llm_ex = b.toggle(t("run.llm_extraction"), cfg.use_llm_extraction, help=t("run.llm_extraction_help"))
            llm_ev = a.toggle(t("run.llm_evidence"), cfg.use_llm_evidence, help=t("run.llm_evidence_help"))
            demo = b.toggle(t("run.demo_mode"), cfg.demo_mode or not state.has_key(), disabled=not state.has_key(), help=t("run.demo_help"))
            rpm = a.number_input(t("run.rpm"), 0, 1000, cfg.llm_rpm, 5, help=t("run.rpm_help"))
            new_cfg = cfg.model_copy(update={"max_iterations": max_iter, "target_shortlist": target, "max_search_calls": calls,
                                             "max_jobs_per_iteration": per_iter, "company_intel": intel, "use_llm_extraction": llm_ex,
                                             "use_llm_evidence": llm_ev, "demo_mode": demo, "llm_rpm": int(rpm)})
            if new_cfg != cfg:
                state.save_run_config(new_cfg)
                cfg = new_cfg
    with c2:
        with st.container(border=True):
            st.markdown(f"**{t('run.estimate')}**")
            demo_mode = cfg.demo_mode or not state.has_key()
            if demo_mode:
                st.caption(t("run.estimate_demo"))
            else:
                est_queries = cfg.max_search_calls * 4 + (cfg.max_company_intel_calls * 2 if cfg.company_intel else 0)
                st.markdown(t("run.estimate_live", calls=cfg.max_search_calls, queries=est_queries, model=st.session_state.model))
                st.caption(t("run.estimate_note"))
        ready = all(ok for ok, _, target in checks[:2])
        if st.button("🚀 " + (t("run.start_demo") if demo_mode else t("run.start")), type="primary", width="stretch", disabled=not ready):
            runner.start(state.get_db(), api_key="" if demo_mode else st.session_state.api_key, model=st.session_state.model,
                         embed_model=st.session_state.embed_model, profile=prof, prefs=prefs,
                         config=cfg.model_copy(update={"demo_mode": demo_mode}))
            time.sleep(0.3)
            st.rerun()


def panel_body() -> None:
    lang = state.lang()
    handle = runner.current()
    if handle is None:
        return
    report = handle.live_report
    events = list(handle.events)
    current_stage = events[-1].stage if events else "read"
    running = handle.running

    head_l, head_r = st.columns([4, 1])
    status = ("🟢 " + t("run.running")) if running else ("✅ " + t("run.done") if report and report.status == "completed" else "⏹️ " + t(f"run.status.{report.status}") if report else "…")
    elapsed = (handle.finished or time.time()) - handle.started
    head_l.markdown(f"### {status} · {elapsed:.0f}s" + (f" · <code>{escape(report.run_id)}</code>" if report else ""), unsafe_allow_html=True)
    if running:
        if head_r.button("⏹ " + t("run.stop"), width="stretch"):
            handle.stop.set()
            st.toast(t("run.stopping"))
    elif head_r.button(t("run.view_matches") + " →", type="primary", width="stretch"):
        go("matches")

    idx = STAGES.index(current_stage) if current_stage in STAGES else 0
    C.stepper([f"{STAGE_ICON[s]} {label(s, lang)}" for s in STAGES], idx if running else len(STAGES) - 1,
              done=range(idx) if running else range(len(STAGES)))

    left, right = st.columns([3, 2], gap="large")
    with left:
        st.markdown(f"**{t('run.timeline')}**")
        with st.container(height=420, border=True):
            for ev in reversed(events[-80:]):
                icon = "⚠️" if ev.level == "warning" else "❌" if ev.level == "error" else STAGE_ICON.get(ev.stage, "•")
                ts = ev.ts.astimezone().strftime("%H:%M:%S")
                st.markdown(f'<div class="jp-evt">{icon} <code>{ts}</code> <b>{escape(label(ev.stage, lang))}</b> — {escape(ev.message)}</div>',
                            unsafe_allow_html=True)
        if report and report.iterations:
            st.markdown(f"**{t('run.iterations')}**")
            for it in report.iterations:
                with st.expander(t("run.iteration_title", n=it.number, leads=it.leads, unique=it.new_unique, short=it.shortlisted), expanded=it is report.iterations[-1]):
                    if it.rejection_reasons:
                        st.markdown(" ".join(C.badge(f"{label(k, lang)} × {v}", "red") for k, v in it.rejection_reasons.items()), unsafe_allow_html=True)
                    for d in it.diagnosis:
                        st.markdown(f"🩺 {render(d, lang)}")
                    for a in it.actions:
                        st.markdown(f"🔧 {render(a, lang)}")
                    if not it.diagnosis and not it.actions:
                        st.caption(t("run.no_changes"))
    with right:
        st.markdown(f"**{t('run.funnel')}**")
        its = report.iterations if report else []
        C.funnel([
            (t("funnel.leads"), sum(i.leads for i in its)), (t("funnel.unique"), sum(i.new_unique for i in its)),
            (t("funnel.verified"), sum(i.verified for i in its)), (t("funnel.passed"), sum(i.hard_passed for i in its)),
            (t("funnel.shortlisted"), sum(i.shortlisted for i in its)),
        ])
        if handle.agent is not None:
            u = handle.agent.tracker.usage
            k1, k2, k3 = st.columns(3)
            k1.metric(t("usage.llm_calls"), u.llm_calls)
            k2.metric(t("usage.search_queries"), u.search_queries)
            k3.metric(t("usage.cost"), f"${u.estimated_cost_usd():.3f}")
            st.caption(t("usage.note", fetches=u.http_fetches, tokens=f"{u.prompt_tokens + u.output_tokens:,}"))
        if report and report.issues:
            with st.expander(f"⚠️ {t('run.issues')} ({len(report.issues)})"):
                for i in report.issues[-30:]:
                    st.markdown(f"- **{label(i.stage, lang)}** · {escape(i.message)}" + (f" → _{escape(i.resolution)}_" if i.resolution else ""))
        if handle.error:
            st.error(handle.error)
        if report and not running and report.suggestions:
            st.markdown(f"**💡 {t('run.suggestions')}**")
            for s in report.suggestions:
                st.info(render(s, lang))
    if not running and handle.finished and not st.session_state.get(f"_final_{report.run_id if report else ''}"):
        st.session_state[f"_final_{report.run_id if report else ''}"] = True
        st.rerun()  # full rerun once so the page leaves live mode


live_panel = st.fragment(run_every=1.5)(panel_body)
