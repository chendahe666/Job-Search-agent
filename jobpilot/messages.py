"""Bilingual (zh/en) templates for every agent-generated message and enum label."""

from __future__ import annotations

from typing import Any, Union

from .schemas import Msg

T: dict[str, dict[str, str]] = {
    # ---- hard filters -------------------------------------------------
    "hf.ok": {"en": "OK", "zh": "通过"},
    "hf.liveness.ok": {"en": "Posting verified live and consistent", "zh": "已验证：职位在线且信息一致"},
    "hf.liveness.dead": {"en": "Posting is closed or gone ({detail})", "zh": "职位已关闭或不存在（{detail}）"},
    "hf.liveness.mismatch": {"en": "Link does not match the claimed job ({detail})", "zh": "链接与搜索声称的职位不符（{detail}）"},
    "hf.liveness.unverified": {"en": "Could not independently verify the posting", "zh": "无法独立验证该职位（可能被网站拦截）"},
    "hf.auth.no_sponsorship": {"en": "Posting states no visa sponsorship", "zh": "职位明确不提供签证担保"},
    "hf.auth.citizen": {"en": "Posting requires US citizenship / permanent residency", "zh": "职位要求美国公民/绿卡"},
    "hf.auth.clearance": {"en": "Posting requires a security clearance", "zh": "职位要求安全许可（Security Clearance）"},
    "hf.auth.sponsors": {"en": "Posting offers visa sponsorship", "zh": "职位明确提供签证担保"},
    "hf.auth.unknown": {"en": "Sponsorship not mentioned", "zh": "职位未提及签证担保"},
    "hf.auth.not_needed": {"en": "Sponsorship not needed", "zh": "无需签证担保"},
    "hf.location.remote_ok": {"en": "Remote (US) — allowed", "zh": "美国远程 — 符合"},
    "hf.location.remote_non_us": {"en": "Remote but not US-eligible ({location})", "zh": "远程但不面向美国（{location}）"},
    "hf.location.mode_excluded": {"en": "Work mode {mode} not in your preferences", "zh": "工作方式 {mode} 不在你的选择中"},
    "hf.location.ok": {"en": "Location matches {location}", "zh": "地点匹配 {location}"},
    "hf.location.non_us": {"en": "Outside the US ({location})", "zh": "不在美国（{location}）"},
    "hf.location.relocate": {"en": "Requires relocation to {location}", "zh": "需要搬迁至 {location}"},
    "hf.location.unknown": {"en": "Location not stated", "zh": "未注明地点"},
    "hf.location.outside": {"en": "Location {location} not in your list", "zh": "地点 {location} 不在你的目标城市中"},
    "hf.seniority.unknown": {"en": "Seniority not stated", "zh": "未注明级别"},
    "hf.seniority.too_far": {"en": "Seniority {level} is far from your target", "zh": "级别 {level} 与目标差距过大"},
    "hf.seniority.adjacent": {"en": "Seniority {level} is one level off", "zh": "级别 {level} 相差一级"},
    "hf.seniority.ok": {"en": "Seniority {level} matches", "zh": "级别 {level} 匹配"},
    "hf.years.unknown": {"en": "Years of experience not stated", "zh": "未注明年限要求"},
    "hf.years.too_many": {"en": "Requires {need}+ years (you have {have})", "zh": "要求 {need}+ 年经验（你有 {have} 年）"},
    "hf.years.ok": {"en": "Requires {need} years (you have {have})", "zh": "要求 {need} 年（你有 {have} 年）"},
    "hf.etype.unknown": {"en": "Employment type not stated", "zh": "未注明雇佣类型"},
    "hf.etype.mismatch": {"en": "Employment type {etype} not wanted", "zh": "雇佣类型 {etype} 不符合"},
    "hf.etype.ok": {"en": "Employment type {etype}", "zh": "雇佣类型 {etype}"},
    "hf.age.unknown": {"en": "Posting date unknown", "zh": "发布日期未知"},
    "hf.age.too_old": {"en": "Posted {days} days ago (limit {limit})", "zh": "发布于 {days} 天前（上限 {limit} 天）"},
    "hf.age.updated": {"en": "First posted {days} days ago, updated {updated} days ago (evergreen/repost)", "zh": "首次发布于 {days} 天前，{updated} 天前更新（常年招聘/重新发布）"},
    "hf.age.ok": {"en": "Posted {days} days ago", "zh": "发布于 {days} 天前"},
    "hf.salary.unknown": {"en": "Salary not posted", "zh": "未公布薪资"},
    "hf.salary.below": {"en": "Max salary ${max} below your floor ${min}", "zh": "最高薪资 ${max} 低于你的底线 ${min}"},
    "hf.salary.ok": {"en": "Salary up to ${max}", "zh": "薪资最高 ${max}"},
    "hf.block.company": {"en": "Company on your blocklist ({company})", "zh": "公司在黑名单中（{company}）"},
    "hf.block.title": {"en": "Title contains excluded keyword “{keyword}”", "zh": "职位名含排除关键词“{keyword}”"},
    # ---- reasons ------------------------------------------------------
    "r.skills": {"en": "Meets {met}/{total} required qualifications ({examples})", "zh": "满足 {met}/{total} 项必需要求（{examples}）"},
    "r.sponsors": {"en": "Explicitly offers visa sponsorship", "zh": "明确提供签证担保"},
    "r.intel": {"en": "Employer sponsors H-1B {level}", "zh": "雇主有 H-1B 担保记录（{level}）"},
    "r.fresh": {"en": "Fresh: posted {days} days ago", "zh": "新鲜职位：{days} 天前发布"},
    "r.remote": {"en": "Remote in the US", "zh": "美国远程"},
    "r.location": {"en": "In your target location ({location})", "zh": "位于目标地点（{location}）"},
    "r.title": {"en": "Title closely matches your targets", "zh": "职位名与目标高度吻合"},
    "r.dream": {"en": "On your dream-company list ({company})", "zh": "理想公司（{company}）"},
    "r.salary": {"en": "Posted pay {range}", "zh": "公布薪资 {range}"},
    # ---- risks --------------------------------------------------------
    "risk.unverified": {"en": "Not independently verified — open the link before investing time", "zh": "未能独立验证，投入时间前请先打开链接确认"},
    "risk.disabled_rule": {"en": "Soft warning ({rule}): {reason}", "zh": "软警告（{rule}）：{reason}"},
    "risk.sponsor_unknown": {"en": "Sponsorship unclear — ask the recruiter early", "zh": "担保情况不明，建议尽早向招聘方确认"},
    "risk.stretch_years": {"en": "Stretch: asks for {need} years, you have {have}", "zh": "略有挑战：要求 {need} 年，你有 {have} 年"},
    "risk.ghost": {"en": "Ghost-job risk: {level}", "zh": "“幽灵职位”风险：{level}"},
    # ---- ghost job signals -------------------------------------------
    "ghost.old": {"en": "Open for {days} days", "zh": "已挂出 {days} 天"},
    "ghost.no_date": {"en": "No posting date", "zh": "无发布日期"},
    "ghost.no_salary_transparency": {"en": "No salary despite pay-transparency law in {state}", "zh": "{state} 有薪资透明法但未公布薪资"},
    "ghost.thin_description": {"en": "Very short description", "zh": "职位描述过短"},
    "ghost.unverified": {"en": "Not found on an employer/ATS page", "zh": "未在雇主/ATS 页面验证"},
    # ---- critic -------------------------------------------------------
    "diag.search_failed": {"en": "All search calls failed", "zh": "所有搜索调用都失败了"},
    "diag.dead_rate": {"en": "{pct}% of leads were closed or mismatched links", "zh": "{pct}% 的线索是已关闭或不匹配的链接"},
    "diag.unverified_rate": {"en": "{pct}% of leads could not be verified (aggregators/blocked pages)", "zh": "{pct}% 的线索无法验证（聚合站/被拦截）"},
    "diag.no_leads": {"en": "Search returned no leads", "zh": "搜索没有返回任何线索"},
    "diag.few_new": {"en": "Only {n} new unique postings", "zh": "仅有 {n} 个新的不重复职位"},
    "diag.top_reject": {"en": "Main rejection cause: {rule} ({pct}% of postings)", "zh": "主要淘汰原因：{rule}（占 {pct}%）"},
    "diag.low_fit": {"en": "{passed} passed hard filters but only {shortlisted} scored A/B", "zh": "{passed} 个通过硬过滤，但只有 {shortlisted} 个达到 A/B"},
    "act.ats_sites": {"en": "Restrict to employer ATS sites (Greenhouse/Lever/Ashby/Workday); {n} tasks updated", "zh": "改为只搜雇主 ATS 站点（Greenhouse/Lever/Ashby/Workday），更新 {n} 个任务"},
    "act.title_synonyms": {"en": "Search title synonyms: {titles}", "zh": "扩展职位同义词：{titles}"},
    "act.skill_focus": {"en": "Narrow queries with core skills: {skills}", "zh": "用核心技能收窄搜索：{skills}"},
    "act.sponsor_focus": {"en": "Add sponsorship-friendly searches", "zh": "增加“提供签证担保”方向的搜索"},
    "act.seniority_terms": {"en": "Emphasize seniority keywords {exclude}", "zh": "强化级别关键词 {exclude}"},
    "act.metro_expansion": {"en": "Search nearby cities: {cities}", "zh": "搜索同一都市圈城市：{cities}"},
    "act.recency": {"en": "Bias toward freshly posted roles", "zh": "偏向最新发布的职位"},
    "act.llm_queries": {"en": "Critic-proposed queries: {queries}", "zh": "Critic 建议的新查询：{queries}"},
    # ---- user suggestions ------------------------------------------
    "sugg.no_results": {"en": "No postings were found — add title synonyms or broaden locations", "zh": "没有找到职位——请添加职位同义词或扩大地点范围"},
    "sugg.locations": {"en": "{pct}% were rejected for location — consider adding cities, Remote, or relocation", "zh": "{pct}% 因地点被淘汰——可考虑增加城市、远程或接受搬迁"},
    "sugg.seniority": {"en": "{pct}% were rejected for seniority/years — consider adjacent levels or a higher years tolerance", "zh": "{pct}% 因级别/年限被淘汰——可考虑相邻级别或提高年限容忍度"},
    "sugg.window": {"en": "{pct}% were older than {days} days — consider a longer window", "zh": "{pct}% 超过 {days} 天——可放宽发布时间窗口"},
    "sugg.sponsorship": {"en": "{pct}% excluded sponsorship — prioritize dream companies with H-1B history", "zh": "{pct}% 明确不担保——建议优先添加有 H-1B 记录的理想公司"},
    "sugg.salary": {"en": "Many postings fall below your salary floor", "zh": "较多职位低于你的薪资底线"},
    "sugg.more_titles": {"en": "Shortlist has {n}/{target} — add related titles or skills keywords", "zh": "候选清单 {n}/{target}——可增加相关职位名或技能关键词"},
}

LABELS: dict[str, dict[str, str]] = {
    # seniority
    "intern": {"en": "Intern", "zh": "实习"}, "entry": {"en": "Entry / New grad", "zh": "初级 / 应届"},
    "mid": {"en": "Mid-level", "zh": "中级"}, "senior": {"en": "Senior", "zh": "高级"},
    "staff": {"en": "Staff", "zh": "Staff"}, "principal": {"en": "Principal", "zh": "Principal"},
    "manager": {"en": "Manager", "zh": "管理岗"}, "unknown": {"en": "Unknown", "zh": "未知"},
    # work mode
    "remote": {"en": "Remote", "zh": "远程"}, "hybrid": {"en": "Hybrid", "zh": "混合办公"}, "onsite": {"en": "On-site", "zh": "现场办公"},
    # employment type
    "full_time": {"en": "Full-time", "zh": "全职"}, "part_time": {"en": "Part-time", "zh": "兼职"},
    "contract": {"en": "Contract", "zh": "合同工"}, "internship": {"en": "Internship", "zh": "实习"}, "temporary": {"en": "Temporary", "zh": "临时"},
    # work auth
    "us_citizen": {"en": "US citizen", "zh": "美国公民"}, "permanent_resident": {"en": "Green card", "zh": "绿卡"},
    "f1_cpt": {"en": "F-1 CPT", "zh": "F-1 CPT"}, "f1_opt": {"en": "F-1 OPT", "zh": "F-1 OPT"},
    "f1_stem_opt": {"en": "F-1 STEM OPT", "zh": "F-1 STEM OPT"}, "h1b": {"en": "H-1B", "zh": "H-1B"}, "other_visa": {"en": "Other visa", "zh": "其他签证"},
    # degree
    "none": {"en": "No degree", "zh": "无学位"}, "associate": {"en": "Associate", "zh": "副学士"}, "bachelor": {"en": "Bachelor's", "zh": "本科"},
    "master": {"en": "Master's", "zh": "硕士"}, "phd": {"en": "PhD", "zh": "博士"},
    # verification
    "verified": {"en": "Verified", "zh": "已验证"}, "unverified": {"en": "Unverified", "zh": "未验证"}, "dead": {"en": "Closed", "zh": "已关闭"},
    "mismatch": {"en": "Mismatch", "zh": "不匹配"}, "demo": {"en": "Demo", "zh": "示例"},
    # evidence
    "met": {"en": "Met", "zh": "满足"}, "partial": {"en": "Partial", "zh": "部分"}, "gap": {"en": "Gap", "zh": "缺口"}, "n/a": {"en": "N/A", "zh": "不适用"},
    # sponsorship
    "sponsors": {"en": "Sponsors", "zh": "提供担保"}, "no_sponsorship": {"en": "No sponsorship", "zh": "不担保"},
    "citizen_only": {"en": "Citizens only", "zh": "仅限公民"}, "clearance": {"en": "Clearance", "zh": "需安全许可"},
    "frequent": {"en": "frequent", "zh": "频繁"}, "occasional": {"en": "occasional", "zh": "偶尔"}, "rare": {"en": "rare", "zh": "很少"}, "none_found": {"en": "none found", "zh": "未找到"},
    # ghost risk
    "low": {"en": "Low", "zh": "低"}, "medium": {"en": "Medium", "zh": "中"}, "high": {"en": "High", "zh": "高"},
    # rules
    "liveness": {"en": "Live posting", "zh": "职位存活"}, "work_authorization": {"en": "Work authorization", "zh": "工作许可/担保"},
    "location": {"en": "Location", "zh": "地点"}, "seniority": {"en": "Seniority", "zh": "级别"}, "years_experience": {"en": "Years", "zh": "年限"},
    "employment_type": {"en": "Employment type", "zh": "雇佣类型"}, "posted_age": {"en": "Posting age", "zh": "发布时间"},
    "salary": {"en": "Salary", "zh": "薪资"}, "blocklists": {"en": "Blocklists", "zh": "黑名单"},
    # dimensions
    "skills": {"en": "Skills evidence", "zh": "技能证据"}, "experience": {"en": "Experience/level", "zh": "经验/级别"},
    "role_alignment": {"en": "Role alignment", "zh": "岗位契合"}, "compensation": {"en": "Compensation", "zh": "薪资"},
    "sponsorship": {"en": "Sponsorship", "zh": "签证担保"}, "company": {"en": "Company", "zh": "公司偏好"},
    "freshness": {"en": "Freshness", "zh": "新鲜度"}, "feedback": {"en": "Your feedback", "zh": "你的反馈"},
    # stop reasons
    "target_reached": {"en": "target shortlist reached", "zh": "达到目标数量"}, "max_iterations": {"en": "max iterations", "zh": "达到最大迭代次数"},
    "budget": {"en": "search budget used", "zh": "搜索预算用完"}, "saturated": {"en": "no new search angles", "zh": "没有新的搜索方向"},
    "search_failed": {"en": "search failing", "zh": "搜索持续失败"},
    # stages
    "read": {"en": "Read", "zh": "读取"}, "plan": {"en": "Plan", "zh": "规划"}, "search": {"en": "Search", "zh": "搜索"},
    "work": {"en": "Work", "zh": "处理"}, "verify": {"en": "Verify", "zh": "验证"}, "evaluate": {"en": "Evaluate", "zh": "评估"},
    "reflect": {"en": "Reflect", "zh": "反思迭代"}, "report": {"en": "Report", "zh": "汇报"}, "agent": {"en": "Agent", "zh": "Agent"},
}


class _SafeDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def label(value: Any, lang: str = "zh") -> str:
    key = getattr(value, "value", value)
    entry = LABELS.get(str(key))
    return entry.get(lang, entry["en"]) if entry else str(key)


def render(m: Union[Msg, dict, str], lang: str = "zh") -> str:
    if isinstance(m, str):
        return m
    if isinstance(m, dict):
        m = Msg.model_validate(m)
    template = T.get(m.key, {}).get(lang) or T.get(m.key, {}).get("en") or m.key
    params = dict(m.params)
    if m.key == "risk.disabled_rule":
        params.setdefault("reason", "")
    if m.key == "risk.disabled_rule" and "reason_key" in params:
        inner = Msg(key=params.pop("reason_key"), params={k: v for k, v in params.items() if k != "rule"})
        params = {"rule": label(params.get("rule", ""), lang), "reason": render(inner, lang)}
    for k in ("level", "rule", "mode", "etype"):
        if k in params and isinstance(params[k], str) and params[k] in LABELS:
            params[k] = label(params[k], lang)
    return template.format_map(_SafeDict(params))
