"""Guided setup wizard: resume → targets → hard constraints → priorities → review."""

from __future__ import annotations

import streamlit as st

from jobpilot.ingest.resume_parser import parse_resume, read_upload
from jobpilot.messages import label
from jobpilot.schemas import (
    CandidateProfile, DegreeLevel, Education, EmploymentType, Experience, HardRuleToggles, Project, ScoreWeights,
    Seniority, WorkAuth, WorkMode,
)
from jobpilot.search.planner import SearchPlan
from jobpilot.taxonomy import INDUSTRIES, KNOWN_SKILLS, ROLE_FAMILIES, US_METROS, US_STATES
from ui import components as C
from ui import state
from ui.i18n import t
from ui.nav import go

STEPS = ["wiz.resume", "wiz.targets", "wiz.constraints", "wiz.priorities", "wiz.review"]

PRESETS = {
    "balanced": ScoreWeights(),
    "fast": ScoreWeights(skills=0.30, experience=0.20, role_alignment=0.10, location=0.08, compensation=0.04, sponsorship=0.16, company=0.02, freshness=0.08, feedback=0.02),
    "dream": ScoreWeights(skills=0.30, experience=0.10, role_alignment=0.18, location=0.06, compensation=0.08, sponsorship=0.10, company=0.14, freshness=0.02, feedback=0.02),
    "visa": ScoreWeights(skills=0.28, experience=0.12, role_alignment=0.12, location=0.06, compensation=0.04, sponsorship=0.28, company=0.04, freshness=0.04, feedback=0.02),
}
AUTH_NEEDS_SPONSORSHIP = {WorkAuth.F1_CPT, WorkAuth.F1_OPT, WorkAuth.F1_STEM_OPT, WorkAuth.H1B, WorkAuth.OTHER_VISA}


def multiselect_free(label_text: str, options: list[str], default: list[str], key: str, help_text: str = "", placeholder: str = "") -> list[str]:
    """Multiselect that also accepts typed values (falls back gracefully on older Streamlit)."""
    opts = list(dict.fromkeys(list(default) + list(options)))
    # Once the session holds a value for this key it is the source of truth; passing
    # `default` as well is what makes Streamlit complain about double-setting a widget.
    seeded = key in st.session_state
    try:
        kwargs = {} if seeded else {"default": default}
        return st.multiselect(label_text, opts, key=key, help=help_text or None,
                              accept_new_options=True, placeholder=placeholder or None, **kwargs)
    except TypeError:
        raw = st.text_input(label_text, ", ".join(default), key=key + "_txt", help=help_text or None)
        return [x.strip() for x in raw.split(",") if x.strip()]


def render() -> None:
    lang = state.lang()
    # Seed every keyed multi-select once per session so a selection survives stepping away and back.
    p = state.prefs()
    for widget_key, value in (("tg_sen", p.seniority), ("tg_et", p.employment_types), ("tg_modes", p.work_modes),
                              ("tg_titles", p.target_titles), ("tg_locs", p.locations), ("tg_kw", p.extra_keywords),
                              ("cons_cb", p.company_blocklist), ("cons_te", p.title_exclude_keywords),
                              ("prio_dream", p.dream_companies)):
        st.session_state.setdefault(widget_key, list(value))
    st.title(t("profile.title"))
    st.markdown(f'<div class="jp-sub">{t("profile.subtitle")}</div>', unsafe_allow_html=True)
    step = st.session_state.wizard_step
    reached = max(st.session_state.get("wizard_max_step", 0), step)
    st.session_state.wizard_max_step = reached
    picked = C.stepper_nav([t(s) for s in STEPS], step, reached)
    if picked is not None and picked != step:
        st.session_state.wizard_step = picked
        st.rerun()

    [step_resume, step_targets, step_constraints, step_priorities, step_review][step](lang)


def nav_buttons(can_next: bool = True, next_label: str = "") -> None:
    st.divider()
    c1, _, c3 = st.columns([1.5, 2, 1.5])  # wide enough that "下一步 →" stays on one line
    step = st.session_state.wizard_step
    if step > 0 and c1.button("← " + t("common.back"), width="stretch"):
        st.session_state.wizard_step -= 1
        st.rerun()
    if step < len(STEPS) - 1 and c3.button((next_label or t("common.next")) + " →", type="primary", width="stretch", disabled=not can_next):
        st.session_state.wizard_step += 1
        st.session_state.wizard_max_step = max(st.session_state.get("wizard_max_step", 0), st.session_state.wizard_step)
        st.rerun()


# --------------------------------------------------------------------------- #
def step_resume(lang: str) -> None:
    profile = state.profile()
    left, right = st.columns([5, 7], gap="large")
    with left:
        st.subheader("① " + t("resume.upload"))
        st.caption(t("resume.upload_help"))
        up = st.file_uploader(t("resume.file"), type=["pdf", "docx", "txt", "md"], key="resume_file")
        pasted = st.text_area(t("resume.paste"), value="", height=160, key="resume_paste", placeholder=t("resume.paste_ph"))
        mode = t("resume.mode_llm") if state.has_key() else t("resume.mode_offline")
        st.caption(mode)
        if st.button(t("resume.parse"), type="primary", width="stretch", disabled=not (up or pasted.strip())):
            with st.spinner(t("resume.parsing")):
                text, inline = (read_upload(up.name, up.getvalue()) if up else (pasted, None))
                if pasted.strip() and up:
                    text = pasted
                parsed, warnings = parse_resume(text, state.llm_client(), inline)
            for w in warnings:
                st.warning(w)
            if parsed.is_ready():
                state.save_profile(parsed)
                st.toast(t("resume.parsed_ok"), icon="✅")
                st.rerun()
            else:
                st.error(t("resume.parse_failed"))
    with right:
        st.subheader("② " + t("resume.review"))
        if not profile.is_ready():
            C.empty_state(t("resume.empty"))
            nav_buttons(can_next=False)
            return
        edit_profile(profile, lang)
    nav_buttons(can_next=profile.is_ready())


def edit_profile(p: CandidateProfile, lang: str) -> None:
    with st.form("profile_form", border=True):
        c1, c2 = st.columns(2)
        name = c1.text_input(t("resume.name"), p.name)
        headline = c2.text_input(t("resume.headline"), p.headline, placeholder="ML Engineer · RAG · Python")
        c3, c4, c5 = st.columns(3)
        location = c3.text_input(t("resume.location"), p.current_location)
        years = c4.number_input(t("resume.years"), 0.0, 60.0, float(p.years_experience), 0.5, help=t("resume.years_help"))
        degrees = list(DegreeLevel)
        degree = c5.selectbox(t("resume.degree"), degrees, index=degrees.index(p.highest_degree), format_func=lambda d: label(d, lang))
        skills = multiselect_free(t("resume.skills"), sorted(KNOWN_SKILLS), p.skills, "pf_skills", t("resume.skills_help"))
        summary = st.text_area(t("resume.summary"), p.summary, height=80)

        st.markdown(f"**{t('resume.experience')}** · <span class='jp-sub'>{t('resume.experience_help')}</span>", unsafe_allow_html=True)
        new_exps: list[Experience] = []
        for i, exp in enumerate(p.experiences + [Experience()]):
            is_new = i == len(p.experiences)
            with st.expander((f"➕ {t('resume.add_experience')}" if is_new else f"{exp.title} @ {exp.company}"), expanded=False):
                a, b, c, d = st.columns([3, 3, 1.3, 1.3])
                title = a.text_input(t("resume.role"), exp.title, key=f"exp_t_{i}")
                company = b.text_input(t("resume.company"), exp.company, key=f"exp_c_{i}")
                start = c.text_input(t("resume.start"), exp.start, key=f"exp_s_{i}")
                end = d.text_input(t("resume.end"), exp.end, key=f"exp_e_{i}")
                bullets = st.text_area(t("resume.bullets"), "\n".join(exp.bullets), key=f"exp_b_{i}", height=110)
                remove = False if is_new else st.checkbox(t("common.remove"), key=f"exp_rm_{i}")
            if (title or company or bullets.strip()) and not remove:
                new_exps.append(Experience(title=title, company=company, start=start, end=end,
                                           bullets=[b.strip(" •-") for b in bullets.split("\n") if b.strip()]))

        st.markdown(f"**{t('resume.projects')}**")
        new_projects: list[Project] = []
        for i, proj in enumerate(p.projects + [Project()]):
            is_new = i == len(p.projects)
            with st.expander((f"➕ {t('resume.add_project')}" if is_new else proj.name or "Project"), expanded=False):
                pname = st.text_input(t("resume.project_name"), proj.name, key=f"prj_n_{i}")
                pdesc = st.text_area(t("resume.project_desc"), proj.description, key=f"prj_d_{i}", height=80)
                ptech = st.text_input(t("resume.project_tech"), ", ".join(proj.technologies), key=f"prj_t_{i}")
                remove = False if is_new else st.checkbox(t("common.remove"), key=f"prj_rm_{i}")
            if (pname or pdesc.strip()) and not remove:
                new_projects.append(Project(name=pname, description=pdesc, technologies=[x.strip() for x in ptech.split(",") if x.strip()]))

        st.markdown(f"**{t('resume.education')}**")
        new_edu: list[Education] = []
        for i, edu in enumerate(p.education + [Education()]):
            cols = st.columns([4, 2, 3, 2])
            school = cols[0].text_input(t("resume.school"), edu.school, key=f"edu_s_{i}", label_visibility="visible" if i == 0 else "collapsed",
                                        placeholder=t("resume.add_education") if i == len(p.education) else "")
            deg = cols[1].selectbox(t("resume.degree"), degrees, index=degrees.index(edu.degree), key=f"edu_d_{i}",
                                    format_func=lambda d: label(d, lang), label_visibility="visible" if i == 0 else "collapsed")
            field = cols[2].text_input(t("resume.field"), edu.field, key=f"edu_f_{i}", label_visibility="visible" if i == 0 else "collapsed")
            grad = cols[3].text_input(t("resume.graduation"), edu.graduation, key=f"edu_g_{i}", label_visibility="visible" if i == 0 else "collapsed")
            if school.strip():
                new_edu.append(Education(school=school, degree=deg, field=field, graduation=grad))

        if st.form_submit_button(t("common.save"), type="primary", width="stretch"):
            updated = p.model_copy(update={
                "name": name, "headline": headline, "current_location": location, "years_experience": years,
                "highest_degree": degree, "skills": skills, "summary": summary, "experiences": new_exps,
                "projects": new_projects, "education": new_edu,
            })
            state.save_profile(updated)
            st.toast(t("common.saved"), icon="💾")
            st.rerun()
    chunks = len(p.experiences and [b for e in p.experiences for b in e.bullets] or []) + len(p.projects)
    st.caption(t("resume.rag_note", n=chunks))


# --------------------------------------------------------------------------- #
def step_targets(lang: str) -> None:
    p = state.prefs()
    st.subheader(t("targets.title"))
    st.caption(t("targets.caption"))
    all_titles = sorted({n for names in ROLE_FAMILIES.values() for n in names})
    c1, c2 = st.columns([3, 2], gap="large")
    with c1:
        titles = multiselect_free(t("targets.titles") + " *", all_titles, p.target_titles, "tg_titles", t("targets.titles_help"))
        families = st.multiselect(t("targets.families"), list(ROLE_FAMILIES), default=[f for f in p.role_families if f in ROLE_FAMILIES],
                                  help=t("targets.families_help"))
        seniority = st.pills(t("targets.seniority") + " *", [s for s in Seniority if s != Seniority.UNKNOWN], selection_mode="multi",
                             format_func=lambda s: label(s, lang), key="tg_sen")
        etypes = st.pills(t("targets.etypes"), [e for e in EmploymentType if e != EmploymentType.UNKNOWN], selection_mode="multi",
                          format_func=lambda e: label(e, lang), key="tg_et")
        keywords = multiselect_free(t("targets.keywords"), [], p.extra_keywords, "tg_kw", t("targets.keywords_help"))
    with c2:
        modes = st.pills(t("targets.modes") + " *", [WorkMode.REMOTE, WorkMode.HYBRID, WorkMode.ONSITE], selection_mode="multi",
                         format_func=lambda m: label(m, lang), key="tg_modes", help=t("targets.modes_help"))
        loc_options = list(US_METROS) + [f"{v}" for v in US_STATES.values()]
        locations = multiselect_free(t("targets.locations"), loc_options, p.locations, "tg_locs", t("targets.locations_help"))
        relocate = st.toggle(t("targets.relocate"), p.willing_to_relocate)
        window = st.select_slider(t("targets.window"), options=[1, 3, 7, 14, 30, 60], value=p.posted_within_days if p.posted_within_days in [1, 3, 7, 14, 30, 60] else 14,
                                  format_func=lambda d: t("targets.days", n=d))
    updated = p.model_copy(update={
        "target_titles": titles, "role_families": families, "seniority": list(seniority or []), "employment_types": list(etypes or []),
        "extra_keywords": keywords, "work_modes": list(modes or []), "locations": locations, "willing_to_relocate": relocate,
        "posted_within_days": int(window),
    })
    if updated != p:
        state.save_prefs(updated)
    errors = [e for e in updated.validation_errors()]
    for e in errors:
        st.warning(t(f"validate.{e}"))
    nav_buttons(can_next=not errors)


# --------------------------------------------------------------------------- #
def step_constraints(lang: str) -> None:
    p = state.prefs()
    st.subheader(t("cons.title"))
    st.caption(t("cons.caption"))
    c1, c2 = st.columns(2, gap="large")
    with c1:
        with st.container(border=True):
            st.markdown(f"**🛂 {t('cons.auth')}** " + C.badge("HARD", "hard"), unsafe_allow_html=True)
            auths = list(WorkAuth)
            auth = st.selectbox(t("cons.auth_status"), auths, index=auths.index(p.work_auth), format_func=lambda a: label(a, lang))
            default_need = auth in AUTH_NEEDS_SPONSORSHIP
            needs = st.toggle(t("cons.needs_sponsorship"), value=p.needs_sponsorship if auth == p.work_auth else default_need,
                              help=t("cons.needs_sponsorship_help"))
            clearance = st.toggle(t("cons.clearance"), value=p.open_to_clearance_roles and not needs, disabled=needs, help=t("cons.clearance_help"))
            if auth == WorkAuth.F1_STEM_OPT:
                st.info(t("cons.everify_note"))
        with st.container(border=True):
            st.markdown(f"**💵 {t('cons.salary')}**", unsafe_allow_html=True)
            min_salary = st.number_input(t("cons.min_salary"), min_value=0, max_value=1_000_000, step=5000, value=int(p.min_salary or 0),
                                         help=t("cons.min_salary_help"))
            salary_hard = st.toggle(t("cons.salary_hard"), value=p.hard_rules.salary, disabled=min_salary == 0)
        with st.container(border=True):
            st.markdown(f"**📏 {t('cons.years')}**")
            tolerance = st.slider(t("cons.tolerance"), 0.0, 5.0, float(p.years_tolerance), 0.5, help=t("cons.tolerance_help"))
    with c2:
        with st.container(border=True):
            st.markdown(f"**🚫 {t('cons.blocklists')}** " + C.badge("HARD", "hard"), unsafe_allow_html=True)
            blocklist = multiselect_free(t("cons.company_block"), [], p.company_blocklist, "cons_cb", t("cons.company_block_help"))
            title_ex = multiselect_free(t("cons.title_exclude"), ["Senior", "Staff", "Principal", "Lead", "Manager", "Director", "Contract", "Intern"],
                                        p.title_exclude_keywords, "cons_te", t("cons.title_exclude_help"))
        with st.container(border=True):
            st.markdown(f"**⚖️ {t('cons.rules')}**")
            st.caption(t("cons.rules_help"))
            rules = p.hard_rules.model_dump()
            new_rules = {}
            for rule in ["liveness", "work_authorization", "location", "seniority", "years_experience", "employment_type", "posted_age", "blocklists"]:
                new_rules[rule] = st.toggle(f"{label(rule, lang)} — {t('rule.' + rule)}", value=rules[rule], key=f"rule_{rule}")
            new_rules["salary"] = salary_hard
    updated = p.model_copy(update={
        "work_auth": auth, "needs_sponsorship": needs, "open_to_clearance_roles": clearance and not needs,
        "min_salary": int(min_salary) or None, "years_tolerance": tolerance, "company_blocklist": blocklist,
        "title_exclude_keywords": title_ex, "hard_rules": HardRuleToggles(**new_rules),
    })
    if updated != p:
        state.save_prefs(updated)
    nav_buttons()


# --------------------------------------------------------------------------- #
def step_priorities(lang: str) -> None:
    p = state.prefs()
    st.subheader(t("prio.title"))
    st.caption(t("prio.caption"))
    preset = st.segmented_control(t("prio.preset"), list(PRESETS), format_func=lambda k: t(f"prio.preset.{k}"), key="prio_preset")
    if preset and st.session_state.get("_last_preset") != preset:
        st.session_state["_last_preset"] = preset
        p = p.model_copy(update={"weights": PRESETS[preset]})
        state.save_prefs(p)
        for k in ScoreWeights.model_fields:
            st.session_state.pop(f"w_{k}", None)
    c1, c2 = st.columns([3, 2], gap="large")
    weights = {}
    with c1:
        for k, v in p.weights.as_dict().items():
            if k == "sponsorship" and not p.needs_sponsorship:
                weights[k] = v
                continue
            weights[k] = st.slider(f"{label(k, lang)} — {t('dim.' + k)}", 0.0, 0.5, float(v), 0.01, key=f"w_{k}")
    with c2:
        total = sum(weights.values()) or 1
        st.markdown(f"**{t('prio.normalized')}**")
        for k, v in sorted(weights.items(), key=lambda kv: -kv[1]):
            if k == "sponsorship" and not p.needs_sponsorship:
                continue
            st.progress(min(v / total, 1.0), text=f"{label(k, lang)} · {v / total:.0%}")
        dream = multiselect_free(t("prio.dream"), [], p.dream_companies, "prio_dream", t("prio.dream_help"))
        ind_pref = st.multiselect(t("prio.ind_prefer"), INDUSTRIES, default=[i for i in p.industries_prefer if i in INDUSTRIES])
        ind_avoid = st.multiselect(t("prio.ind_avoid"), INDUSTRIES, default=[i for i in p.industries_avoid if i in INDUSTRIES])
    updated = p.model_copy(update={"weights": ScoreWeights(**weights), "dream_companies": dream, "industries_prefer": ind_pref, "industries_avoid": ind_avoid})
    if updated != p:
        state.save_prefs(updated)
    nav_buttons(next_label=t("wiz.review"))


# --------------------------------------------------------------------------- #
def step_review(lang: str) -> None:
    prof, p = state.profile(), state.prefs()
    st.subheader(t("review.title"))
    errors = p.validation_errors() + ([] if prof.is_ready() else ["profile"])
    c1, c2, c3 = st.columns(3, gap="medium")
    with c1, st.container(border=True):
        st.markdown(f"**👤 {t('review.candidate')}**")
        st.write(f"{prof.name or '—'} · {prof.headline or ''}")
        st.caption(f"{prof.years_experience:g} {t('review.years')} · {label(prof.highest_degree, lang)} · {len(prof.skills)} {t('review.skills')}")
        st.markdown(" ".join(C.badge(s, "gray") for s in prof.skills[:14]), unsafe_allow_html=True)
    with c2, st.container(border=True):
        st.markdown(f"**🎯 {t('review.targets')}**")
        st.write(", ".join(p.target_titles) or "—")
        st.caption(" · ".join([", ".join(label(s, lang) for s in p.seniority), ", ".join(label(m, lang) for m in p.work_modes),
                               ", ".join(p.locations) or ("US" if WorkMode.REMOTE in p.work_modes else "—"), t("targets.days", n=p.posted_within_days)]))
    with c3, st.container(border=True):
        st.markdown(f"**🛂 {t('review.auth')}**")
        st.write(label(p.work_auth, lang) + (" · " + t("review.needs_sponsorship") if p.needs_sponsorship else ""))
        enforced = [label(k, lang) for k, v in p.hard_rules.model_dump().items() if v]
        st.caption(t("review.hard_rules") + ": " + ", ".join(enforced))

    st.markdown(f"#### 🧠 {t('review.how')}")
    plan = SearchPlan(prof, p)
    cols = st.columns(2)
    with cols[0]:
        st.markdown(t("review.how_steps"))
    with cols[1]:
        st.markdown(f"**{t('review.plan_preview')}**")
        for task in plan.tasks[:6]:
            with st.expander(task.describe()):
                for q in task.queries(p)[:3]:
                    st.code(q, language=None, wrap_lines=True)
    for e in errors:
        st.error(t(f"validate.{e}"))
    st.divider()
    b1, _, b3 = st.columns([1, 2, 2])
    if b1.button("← " + t("common.back"), width="stretch"):
        st.session_state.wizard_step -= 1
        st.rerun()
    if b3.button("🚀 " + t("review.start"), type="primary", width="stretch", disabled=bool(errors)):
        go("run")
