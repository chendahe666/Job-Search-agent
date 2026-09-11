"""Bilingual, resume-first workspace with stable IDs and explicit approval gates."""
from __future__ import annotations

from datetime import date
import json

import streamlit as st

from services.workspace import Workspace, ROLES, source_draft, filter_jobs, split_skills

# Persisted identifiers do not depend on display language, including legacy records.
PAGES = ["简历工作台", "我的素材", "岗位库", "投递记录", "设置"]
STAGES = ["已收藏", "准备申请", "已投递", "面试中", "Offer", "已结束"]
EN_LABELS = dict(zip(PAGES + STAGES, ["Resumes", "Profile", "Jobs", "Applications", "Settings", "Saved", "Preparing", "Applied", "Interviewing", "Offer", "Closed"]))


def t(zh, en):
    """Translate interface copy only; never translate user documents implicitly."""
    return en if st.session_state.get("language", "中文") == "English" else zh


def display(value):
    return EN_LABELS.get(value, value) if st.session_state.get("language") == "English" else value


def style():
    """Restrained application chrome with high-contrast focus and compact hierarchy."""
    st.markdown('''<style>
    .stApp{background:#f7f8fa;color:#17252b}
    .block-container{max-width:1180px;padding-top:3rem;padding-bottom:2rem}
    [data-testid=stHeader]{height:2.5rem;background:transparent}
    .stAppDeployButton{display:none}
    h1,h2,h3{color:#17252b;letter-spacing:-.025em}
    h1{font-family:'Segoe UI','Microsoft YaHei',sans-serif!important;font-weight:650!important;font-size:1.8rem!important}
    h3{font-size:1.2rem!important}
    .brand{font-family:'Segoe UI',sans-serif;font-size:1.55rem;letter-spacing:-.055em;font-weight:750;padding-top:5px;color:#143e34}
    .brand span{display:inline-block;width:10px;height:10px;background:#22866a;border-radius:3px;margin-right:10px}
    .step{padding:.65rem 1rem;border-bottom:2px solid #dfe5e8;color:#68777d;font-size:.85rem}
    .step.active{border-color:#16715a;color:#12513f;background:#edf5f1;font-weight:650}
    .stButton button,.stDownloadButton button{border-radius:7px;min-height:42px}
    .stButton button[kind=primary]{background:#176b55;border-color:#176b55;color:white}
    button:focus-visible{outline:3px solid #409dcb!important;outline-offset:3px}
    [data-testid=stTextArea] textarea{line-height:1.65;background:white}
    [data-testid=stVerticalBlockBorderWrapper]{border-radius:10px;background:white}
    [data-testid=stCaptionContainer]{color:#607179}
    @media(max-width:700px){.block-container{padding:3rem 1rem 1rem}.brand{font-size:1.3rem}.step{padding:.5rem;font-size:.75rem}}
    @media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
    </style>''', unsafe_allow_html=True)


def go(page, step=None):
    """Callback navigation keeps widget identity independent from labels."""
    st.session_state.page = page
    if step is not None:
        st.session_state.step = step


def field_key(key, default=""):
    cache = st.session_state.setdefault("draft_fields", {})
    if key not in st.session_state:
        st.session_state[key] = cache.get(key, default)
    return key


def remember(key):
    st.session_state.setdefault("draft_fields", {})[key] = st.session_state[key]


def text_input(label, key, default="", **kwargs):
    return st.text_input(label, key=field_key(key, default), on_change=remember, args=(key,), **kwargs)


def text_area(label, key, default="", **kwargs):
    return st.text_area(label, key=field_key(key, default), on_change=remember, args=(key,), **kwargs)


def replace_editor(text):
    st.session_state.editor = text
    st.session_state.setdefault("draft_fields", {})["editor"] = text
    st.session_state.pop("proposal", None)


def switch_language():
    """Retain active widget drafts before translated labels are rendered."""
    for key in list(st.session_state.get("draft_fields", {})):
        if key in st.session_state:
            remember(key)


def select_page(widget_key):
    st.session_state.page = st.session_state[widget_key]


def save_profile(store, guided):
    """Validate inside a callback, avoiding mid-render rerun/widget collisions."""
    source = st.session_state.get("source_input", "").strip()
    if not source:
        st.session_state.profile_error = True
        return
    store.put("profile", {"source": source, "skills": st.session_state.get("skills_input", ""), "name": st.session_state.get("name_input", ""), "location": st.session_state.get("location_input", "United States")}, "me")
    st.session_state.pop("profile_error", None)
    st.session_state.notice = t("素材已保存", "Profile saved")
    if guided:
        st.session_state.step = 2


def profile_editor(store, profile, guided=False):
    st.subheader(t("经历素材", "Experience"))
    source = text_area(t("简历或项目经历", "Resume or project experience"), "source_input", profile.get("source", ""), height=250, placeholder=t("粘贴现有简历或项目经历", "Paste your resume or project experience"), max_chars=30000)
    if st.session_state.get("profile_error"):
        st.error(t("请先填写经历内容。", "Enter your experience to continue."))
    st.button(t("保存并继续", "Save & continue") if guided else t("保存素材", "Save profile"), type="primary", key="save_profile", on_click=save_profile, args=(store, guided))
    with st.expander(t("基本信息 · 可选", "Details · optional")):
        text_input(t("技能", "Skills"), "skills_input", profile.get("skills", ""), placeholder="Python, SQL, PyTorch")
        text_input(t("姓名", "Name"), "name_input", profile.get("name", ""))
        text_input(t("目标地区", "Target location"), "location_input", profile.get("location", "United States"))


def config_changed(key):
    remember(key)
    st.session_state.ai_consent = False


def settings(store):
    """Technical configuration and privacy information live outside daily workflows."""
    st.subheader(t("AI 服务", "AI service"))
    with st.container(border=True):
        st.selectbox(t("服务商", "Provider"), ["groq", "gemini"], key=field_key("provider", "groq"), on_change=config_changed, args=("provider",))
        st.text_input(t("API 密钥", "API key"), type="password", key=field_key("api_key"), on_change=config_changed, args=("api_key",))
        st.text_input(t("模型", "Model"), key=field_key("model"), on_change=config_changed, args=("model",))
        st.caption(t("密钥仅保留在本次会话。未配置时可正常编辑和保存。", "Keys stay in this session. Editing and saving work without AI."))
    with st.expander(t("隐私与数据", "Privacy & data")):
        st.write(t("本机单用户存储，未加密。请勿公开部署；不包含账户隔离或支付功能。", "Single-user local storage, unencrypted. Do not deploy publicly. Account isolation and billing are not included."))
        st.write(t("AI 仅在授权后接收当前草稿和关联职位；发送前可移除个人联系方式。", "AI receives the current draft and linked job only with consent. Remove personal contact details before sending."))
        st.caption(t("语言切换不改变简历正文。保存的跟进日期不会触发自动提醒。", "Language changes do not translate documents. Follow-up dates do not trigger notifications."))
        backup = {kind: store.all(kind) for kind in ("profile", "resume", "job", "application")}
        st.download_button(t("导出数据 · JSON", "Export data · JSON"), json.dumps(backup, ensure_ascii=False, indent=2), file_name="rolesignal-backup.json", mime="application/json")


def begin_edit(role, target, profile):
    st.session_state.active_role = role
    st.session_state.target_job = target
    if not st.session_state.get("draft_fields", {}).get("editor"):
        replace_editor(source_draft(profile))
    st.session_state.step = 3


def restart_draft(store, profile):
    draft = st.session_state.get("draft_fields", {}).get("editor", "")
    if draft.strip():
        store.save_version(draft, st.session_state.get("active_role", ROLES[0]), profile, store.get("job", st.session_state.get("target_job", "")))
    replace_editor(source_draft(profile))
    st.session_state.notice = t("旧草稿已备份", "Previous draft backed up")


def make_proposal(source, role, job):
    """Do not expose prompts, provider errors, raw JSON, or model metadata to the UI."""
    from agents.resume_agent import ResumeAgent
    with st.spinner(t("正在分析…", "Analyzing…")):
        try:
            config = st.session_state.get("draft_fields", {})
            agent = ResumeAgent(api_key=config.get("api_key", ""), provider=config.get("provider", "groq"), model=config.get("model", ""))
            result = agent.suggest(source, role, job)
            st.session_state.proposal = {"source": source, "result": result, "role": role, "job_id": job.get("id") if job else None}
            st.session_state.proposal_serial = st.session_state.get("proposal_serial", 0) + 1
        except Exception:
            st.error(t("暂时无法生成建议。请检查 AI 设置后重试。", "Suggestions unavailable. Check your AI settings and retry."))


def apply_selected(source, edits):
    from agents.resume_agent import apply_suggestions
    replace_editor(apply_suggestions(source, edits))
    st.session_state.notice = t("修改已应用，尚未保存", "Changes applied, not yet saved")


def resume_editor(store, profile):
    """Three focused stages; one primary action per stage."""
    step = st.session_state.setdefault("step", 1 if not profile.get("source") else 2)
    cols = st.columns(3)
    for i, label in enumerate([t("经历", "Experience"), t("方向", "Target"), t("编辑", "Edit")], 1):
        cols[i-1].markdown(f'<div class="step {"active" if i == step else ""}">0{i} &nbsp; {label}</div>', unsafe_allow_html=True)
    st.write("")
    if step == 1:
        profile_editor(store, profile, guided=True)
        return
    if not profile.get("source"):
        st.info(t("请先添加经历。", "Add your experience first."))
        st.button(t("添加经历", "Add experience"), on_click=go, args=(PAGES[0], 1), type="primary")
        return
    if step == 2:
        st.subheader(t("目标方向", "Target role"))
        role = st.radio(t("方向", "Role"), ROLES, key=field_key("role_choice", st.session_state.get("active_role", ROLES[0])), on_change=remember, args=("role_choice",))
        jobs = store.all("job")
        with st.expander(t("关联岗位 · 可选", "Link a job · optional")):
            ids = [""] + [j["id"] for j in jobs]
            target = st.session_state.get("target_job", "")
            if target not in ids:
                target = ""
            job_labels = {"": t("基础版", "Base resume"), **{j["id"]: f"{j['title']} · {j['company']}" for j in jobs}}
            target = st.selectbox(t("岗位", "Job"), ids, index=ids.index(target), key="target_picker", format_func=job_labels.__getitem__)
        st.button(t("继续编辑", "Continue"), type="primary", key="begin_edit", on_click=begin_edit, args=(role, target, profile))
        if st.session_state.get("draft_fields", {}).get("editor"):
            st.caption(t("将继续使用当前草稿。", "Your current draft will be retained."))
            st.button(t("从素材重新开始", "Start from profile"), help=t("当前草稿会先备份。", "Your current draft is backed up first."), on_click=restart_draft, args=(store, profile))
        st.button(t("返回", "Back"), on_click=go, args=(PAGES[0], 1), key="back_to_profile")
        return
    role = st.session_state.get("active_role", ROLES[0])
    job = store.get("job", st.session_state.get("target_job", ""))
    st.subheader(role)
    if job:
        st.caption(f"{job['title']} · {job['company']}")
    editor, review = st.columns([1.7, 1], gap="large")
    with editor:
        source = text_area(t("简历正文", "Resume draft"), "editor", source_draft(profile), height=440, max_chars=30000)
        a, b = st.columns(2)
        if a.button(t("保存新版本", "Save version"), type="primary", use_container_width=True, key="save_version"):
            if not source.strip():
                st.error(t("内容不能为空。", "The draft cannot be empty."))
            else:
                store.save_version(source, role, profile, job)
                st.success(t("版本已保存", "Version saved"))
        b.download_button(t("下载 TXT", "Download TXT"), source, file_name=f"resume-{role.replace(' / ', '-').replace(' ', '-')}.txt", mime="text/plain", disabled=not source.strip(), use_container_width=True)
        st.caption(t("离开前请保存。PDF / Word 导出暂未开放。", "Save before closing. PDF / Word export is not available yet."))
    with review:
        st.markdown("#### " + t("修改建议", "Review"))
        config = st.session_state.get("draft_fields", {})
        configured = bool(config.get("api_key") and config.get("model"))
        if configured:
            consent = st.checkbox(t("允许 AI 分析当前简历与关联岗位", "Allow AI to analyze this resume and linked job"), key="ai_consent", help=t("内容将发送给设置中选择的服务商。", "Content is sent to the provider selected in Settings."))
            if st.button(t("分析简历", "Analyze resume"), disabled=not(consent and source.strip()), key="analyze"):
                make_proposal(source, role, job)
        else:
            st.caption(t("连接 AI 后可获取修改建议。", "Connect AI to get editing suggestions."))
            st.button(t("连接 AI", "Connect AI"), on_click=go, args=(PAGES[4],))
        proposal = st.session_state.get("proposal")
        if proposal:
            if proposal["source"] != source or proposal["role"] != role or proposal["job_id"] != (job.get("id") if job else None):
                st.info(t("内容已更新，请重新分析。", "Content changed. Run analysis again."))
            else:
                selected = []
                st.caption(t("核对事实后选择修改。", "Verify the facts before accepting edits."))
                for i, edit in enumerate(proposal["result"]["edits"]):
                    with st.container(border=True):
                        st.caption(t("原文", "Original"))
                        st.text(edit["original"])
                        st.caption(t("建议", "Suggested"))
                        st.text(edit["suggested"])
                        if st.checkbox(t("接受", "Accept"), key=f"accept_{st.session_state.proposal_serial}_{i}"):
                            selected.append(edit)
                if not proposal["result"]["edits"]:
                    st.info(t("暂无可用修改。", "No edits available."))
                st.button(t("应用修改", "Apply edits"), disabled=not selected, on_click=apply_selected, args=(source, selected))
        with st.expander(t("参考素材", "Source material")):
            st.text(profile.get("source", ""))
            if job:
                st.divider()
                st.text(job["description"])
    st.button(t("调整目标", "Change target"), on_click=go, args=(PAGES[0], 2))
    history(store)


def load_version(store, version):
    draft = st.session_state.get("draft_fields", {}).get("editor", "")
    if draft.strip():
        store.save_version(draft, st.session_state.get("active_role", ROLES[0]), store.get("profile", "me", {}), store.get("job", st.session_state.get("target_job", "")))
    replace_editor(version["text"])
    st.session_state.active_role = version["role"]
    st.session_state.role_choice = version["role"]
    st.session_state.target_job = (version.get("job_snapshot") or {}).get("id", "")
    go(PAGES[0], 3)


def version_label(version):
    job = version.get("job_snapshot")
    return f"{version['role']} · {job['company'] if job else t('基础版', 'Base')} · {version['updated']}"


def history(store):
    versions = store.all("resume")
    with st.expander(t("版本记录", "Version history") + f" · {len(versions)}"):
        if not versions:
            st.caption(t("暂无已保存版本", "No saved versions"))
            return
        labels = {v["id"]: version_label(v) for v in versions}
        selected = st.selectbox(t("版本", "Version"), list(labels), key="version_picker", format_func=labels.__getitem__)
        version = next(v for v in versions if v["id"] == selected)
        st.text(version["text"])
        st.download_button(t("下载此版本", "Download version"), version["text"], file_name=f"resume-{selected[:8]}.txt", mime="text/plain")
        st.button(t("恢复此版本", "Restore version"), help=t("当前草稿会先备份。", "Your current draft is backed up first."), key="restore_version", on_click=load_version, args=(store, version))


def save_import(store):
    """Callback import: errors are localized, never raw exception text."""
    title = st.session_state.get("import_title", "").strip()
    description = st.session_state.get("import_description", "").strip()
    url = st.session_state.get("import_url", "").strip()
    if not title or not description:
        st.session_state.import_error = t("请填写岗位名称和职位描述。", "Enter a job title and description.")
        return
    if url and not url.startswith(("https://", "http://")):
        st.session_state.import_error = t("请输入有效的 HTTP / HTTPS 链接。", "Enter a valid HTTP / HTTPS URL.")
        return
    _, created = store.save_job(title, st.session_state.get("import_company", ""), description, url, st.session_state.get("import_skills", ""))
    st.session_state.pop("import_error", None)
    st.session_state.notice = t("岗位已保存", "Job saved") if created else t("岗位已存在", "Job already saved")


def job_import(store):
    with st.expander(t("添加岗位", "Add job"), expanded=not store.all("job")):
        text_input(t("岗位名称 *", "Job title *"), "import_title")
        text_area(t("职位描述 *", "Job description *"), "import_description", height=150)
        a, b = st.columns(2)
        with a:
            text_input(t("公司", "Company"), "import_company")
        with b:
            text_input(t("来源链接", "Source URL"), "import_url", help=t("保存链接，不自动抓取网页。", "Saves the link; does not fetch the page."))
        text_input(t("要求的技能 · 可选", "Required skills · optional"), "import_skills", placeholder="Python, SQL")
        st.button(t("保存岗位", "Save job"), key="save_job", type="primary", on_click=save_import, args=(store,))
        if st.session_state.get("import_error"):
            st.error(st.session_state.import_error)


@st.cache_data(show_spinner=False)
def demo_jobs():
    from data.retriever import JobRepository
    return JobRepository(use_expanded=True).load_jobs()


@st.cache_data(show_spinner=False)
def rank_all(profile_data, jobs):
    from agents.profile_analyzer import UserProfile
    from agents.embedding_agent import EmbeddingAgent
    from agents.hybrid_matcher import HybridMatcher
    profile = UserProfile(skills=tuple(split_skills(profile_data.get("skills", ""))), experience_level="Not specified", years_experience=0, professional_summary=profile_data.get("source", ""))
    dense = EmbeddingAgent(local_files_only=True)
    results = HybridMatcher(dense_agent=dense).rank_jobs(profile, jobs, top_k=len(jobs))
    return results, dense.backend


def prepare_job(job, profile):
    st.session_state.target_job = job["id"]
    st.session_state.pop("target_picker", None)
    go(PAGES[0], 2 if profile.get("source") else 1)


def track_job(store, job):
    if not store.get("application", job["id"]):
        store.put("application", {"job": job, "stage": STAGES[0], "note": "", "resume_id": "", "follow_up": ""}, job["id"])
    st.session_state.notice = t("已加入投递记录", "Added to applications")


def jobs_page(store, profile):
    job_import(store)
    demo = st.toggle(t("示例数据", "Demo data"), value=False, key="demo", help=t("40 条模拟岗位，不可真实投递。", "40 fictional jobs; not real application opportunities."))
    jobs = demo_jobs() if demo else store.all("job")
    if demo:
        st.caption(t("模拟岗位 · 仅供演示", "Fictional jobs · demo only"))
    if not jobs:
        st.info(t("暂无岗位", "No jobs yet"))
        return
    if profile.get("source"):
        if st.button(t("按相关度排序", "Rank by relevance")):
            with st.spinner(t("正在排序…", "Ranking…")):
                try:
                    ranked, backend = rank_all(profile, jobs)
                    st.session_state.ranking = {"profile": profile, "jobs": jobs, "results": ranked, "backend": backend}
                except Exception:
                    st.warning(t("排序暂不可用。", "Ranking is unavailable."))
    ranking = st.session_state.get("ranking")
    if ranking and ranking["jobs"] == jobs and ranking["profile"] == profile:
        jobs = ranking["results"]
        st.caption(t("相关度不代表录用概率。", "Relevance is not a hiring probability."))
        if "TF-IDF" in ranking["backend"]:
            st.caption(t("语义模型不可用，已切换至关键词匹配。", "Semantic model unavailable. Using keyword matching."))
    search = text_input(t("搜索岗位", "Search jobs"), "job_search", placeholder=t("岗位、公司或技能", "Role, company or skill"))
    results = filter_jobs(jobs, search)
    st.caption(f"{len(results)} / {len(jobs)} " + t("岗位", "jobs"))
    for job in results:
        with st.container(border=True):
            col, action = st.columns([3, 1])
            with col:
                st.subheader(job["title"])
                company = job["company"] if job["company"] != "未填写公司" else t("公司未填写", "Company not specified")
                st.text(f"{company} · {job.get('location', '')}")
                if "match_score" in job:
                    st.caption(t("相关度", "Relevance") + f" {job['match_score']:.0%}")
                with st.expander(t("职位详情", "Job details")):
                    st.text(job["description"])
                    if job.get("required_skills"):
                        declared = {s.casefold() for s in split_skills(profile.get("skills", ""))}
                        matches = [s for s in job["required_skills"] if s.casefold() in declared]
                        unknown = [s for s in job["required_skills"] if s.casefold() not in declared]
                        st.text(t("已声明技能：", "Declared skills: ") + (", ".join(matches) or "—"))
                        st.text(t("待确认技能：", "Skills to confirm: ") + (", ".join(unknown) or "—"))
                    if job.get("url"):
                        st.link_button(t("查看来源", "View source"), job["url"])
            with action:
                if not demo:
                    st.button(t("准备简历", "Prepare resume"), key=f"prepare_{job['id']}", use_container_width=True, on_click=prepare_job, args=(job, profile))
                    st.button(t("加入投递记录", "Track application"), key=f"track_{job['id']}", use_container_width=True, on_click=track_job, args=(store, job))


def save_application(store, record):
    key = record["id"]
    follow = st.session_state.get(f"follow_{key}")
    store.put("application", {**record, "stage": st.session_state[f"stage_{key}"], "resume_id": st.session_state[f"resume_{key}"], "note": st.session_state.get(f"note_{key}", ""), "follow_up": follow.isoformat() if follow else ""}, key)
    st.session_state.notice = t("进度已保存", "Progress saved")


def tracker(store):
    records, versions = store.all("application"), store.all("resume")
    if not records:
        st.info(t("暂无投递记录", "No applications yet"))
        st.button(t("浏览岗位", "Browse jobs"), on_click=go, args=(PAGES[2],), type="primary")
        return
    for record in records:
        job, key = record["job"], record["id"]
        with st.expander(f"{display(record['stage'])} · {job['title']} · {job['company']}"):
            stage_labels = {s: display(s) for s in STAGES}
            st.selectbox(t("状态", "Status"), STAGES, key=field_key(f"stage_{key}", record["stage"]), format_func=stage_labels.__getitem__, on_change=remember, args=(f"stage_{key}",))
            ids = [""] + [v["id"] for v in versions]
            resume_labels = {"": t("未选择", "Not selected"), **{v["id"]: version_label(v) for v in versions}}
            st.selectbox(t("使用的简历", "Resume used"), ids, key=field_key(f"resume_{key}", record.get("resume_id", "")), format_func=resume_labels.__getitem__, on_change=remember, args=(f"resume_{key}",))
            default_date = date.fromisoformat(record["follow_up"]) if record.get("follow_up") else None
            st.date_input(t("跟进日期", "Follow-up date"), key=field_key(f"follow_{key}", default_date), on_change=remember, args=(f"follow_{key}",))
            text_area(t("备注", "Notes"), f"note_{key}", record.get("note", ""))
            st.button(t("保存进度", "Save progress"), type="primary", key=f"save_{key}", on_click=save_application, args=(store, record))
            if job.get("url"):
                st.link_button(t("查看来源", "View source"), job["url"])


def main():
    """Render a fast shell; technical details are not part of the primary journey."""
    st.set_page_config(page_title="RoleSignal", page_icon="📄", layout="wide")
    style()
    store = Workspace()
    profile = store.get("profile", "me", {})
    brand, language = st.columns([5, 1])
    brand.markdown('<div class="brand"><span></span>RoleSignal</div>', unsafe_allow_html=True)
    with language:
        st.selectbox("Language / 语言", ["中文", "English"], key="language", on_change=switch_language, label_visibility="collapsed")
    st.session_state.setdefault("page", PAGES[0])
    page_labels = {p: display(p) for p in PAGES}
    nav_key = "nav_" + st.session_state.language
    # Locale-specific widget avoids stale translated option labels in the browser.
    st.session_state[nav_key] = st.session_state.page
    st.radio(t("工作区", "Workspace"), PAGES, horizontal=True, key=nav_key, format_func=page_labels.__getitem__, label_visibility="collapsed", on_change=select_page, args=(nav_key,))
    st.divider()
    if st.session_state.get("notice"):
        st.success(st.session_state.pop("notice"))
    page = st.session_state.page
    st.title(display(page))
    if page == PAGES[0]:
        resume_editor(store, profile)
    elif page == PAGES[1]:
        profile_editor(store, profile)
    elif page == PAGES[2]:
        jobs_page(store, profile)
    elif page == PAGES[3]:
        tracker(store)
    else:
        settings(store)
