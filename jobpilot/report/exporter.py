"""REPORT stage exports: Markdown run report and CSV shortlist."""

from __future__ import annotations

import csv
import io

from ..messages import label, render
from ..schemas import CandidateProfile, EvidenceStatus, MatchResult, RunReport, SearchPreferences, Tier


def matches_csv(matches: list[MatchResult], lang: str = "en") -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["tier", "score", "confidence", "title", "company", "location", "work_mode", "posted", "salary", "sponsorship",
                "verification", "ghost_risk", "reasons", "gaps", "failed_rules", "url"])
    for m in matches:
        lo, hi = m.job.annual_salary_range()
        w.writerow([
            m.tier.value, m.total_score, m.confidence, m.job.title, m.job.company, m.job.location_text, label(m.job.work_mode, lang),
            m.job.date_posted or "", f"{lo or ''}-{hi or ''}" if (lo or hi) else "", label(m.job.sponsorship.status, lang),
            label(m.job.verification.status, lang), label(m.ghost_risk, lang), " | ".join(render(r, lang) for r in m.reasons),
            " | ".join(m.gaps), " | ".join(render(h.reason, lang) for h in m.failed_rules), m.job.apply_url or m.job.url,
        ])
    return buf.getvalue()


def run_markdown(report: RunReport, matches: list[MatchResult], profile: CandidateProfile | None,
                 prefs: SearchPreferences | None, lang: str = "en") -> str:
    zh = lang == "zh"
    L = (lambda zh_text, en_text: zh_text if zh else en_text)
    out = [f"# JobPilot {L('运行报告', 'Run report')} · {report.run_id}", ""]
    out.append(f"- {L('状态', 'Status')}: **{report.status}** ({label(report.stop_reason, lang) if report.stop_reason else '-'})")
    out.append(f"- {L('模式', 'Mode')}: {report.mode} · {L('迭代', 'Iterations')}: {len(report.iterations)}")
    u = report.usage
    out.append(f"- {L('用量', 'Usage')}: {u.llm_calls} LLM calls, {u.search_queries} search queries, "
               f"{u.prompt_tokens + u.output_tokens:,} tokens, ≈ ${u.estimated_cost_usd():.3f}")
    if prefs:
        out.append(f"- {L('目标', 'Targets')}: {', '.join(prefs.target_titles)} · {', '.join(prefs.locations) or '-'} · "
                   f"{', '.join(label(m, lang) for m in prefs.work_modes)}")
    out += ["", f"## {L('漏斗', 'Funnel')}", ""]
    f = report.funnel
    out.append(" → ".join(f"{k} {v}" for k, v in f.items()))
    out += ["", f"## {L('迭代过程', 'Iterations')}", ""]
    for it in report.iterations:
        out.append(f"### {L('第', 'Iteration ')}{it.number}{L(' 轮', '')} ({it.seconds}s)")
        out.append(f"- {L('任务', 'Tasks')}: " + "; ".join(it.tasks))
        out.append(f"- leads {it.leads} · unique {it.new_unique} · verified {it.verified} · unverified {it.unverified} · dead {it.dead} · mismatch {it.mismatch} · hard-pass {it.hard_passed} · A/B {it.shortlisted}")
        if it.rejection_reasons:
            out.append(f"- {L('淘汰原因', 'Rejections')}: " + ", ".join(f"{label(k, lang)} {v}" for k, v in it.rejection_reasons.items()))
        for d in it.diagnosis:
            out.append(f"- 🩺 {render(d, lang)}")
        for a in it.actions:
            out.append(f"- 🔧 {render(a, lang)}")
        out.append("")
    if report.issues:
        out += [f"## {L('问题与处理', 'Issues & handling')}", ""]
        for i in report.issues[:40]:
            out.append(f"- [{i.severity}] **{label(i.stage, lang)}**: {i.message}" + (f" → {i.resolution}" if i.resolution else ""))
        out.append("")
    if report.suggestions:
        out += [f"## {L('给你的建议（需要你决定）', 'Suggestions (your call)')}", ""]
        out += [f"- {render(s, lang)}" for s in report.suggestions]
        out.append("")
    shortlist = [m for m in matches if m.tier in (Tier.A, Tier.B)]
    out += [f"## {L('候选清单', 'Shortlist')} ({len(shortlist)})", ""]
    out.append(f"| Tier | Score | {L('职位', 'Role')} | {L('公司', 'Company')} | {L('地点', 'Location')} | {L('担保', 'Sponsorship')} | {L('验证', 'Verified')} |")
    out.append("|---|---|---|---|---|---|---|")
    for m in shortlist:
        out.append(f"| {m.tier.value} | {m.total_score:.0f} | [{m.job.title}]({m.job.apply_url or m.job.url}) | {m.job.company} | "
                   f"{m.job.location_text} | {label(m.job.sponsorship.status, lang)} | {label(m.job.verification.status, lang)} |")
    for m in shortlist:
        out += ["", f"### {m.job.title} — {m.job.company}", ""]
        out += [f"- ✅ {render(r, lang)}" for r in m.reasons]
        out += [f"- ⚠️ {render(r, lang)}" for r in m.risks]
        out.append("")
        out.append(f"| {L('要求', 'Requirement')} | {L('状态', 'Status')} | {L('简历证据', 'Resume evidence')} |")
        out.append("|---|---|---|")
        for e in m.evidence:
            if e.status == EvidenceStatus.NOT_APPLICABLE:
                continue
            quote = (e.quote or "").replace("|", "/")[:140]
            out.append(f"| {e.requirement_text[:90].replace('|', '/')} | {label(e.status, lang)} | {quote} {('['+e.chunk_id+']') if e.chunk_id else ''} |")
    rejected = [m for m in matches if m.tier == Tier.REJECTED]
    if rejected:
        out += ["", f"## {L('被硬过滤淘汰', 'Rejected by hard filters')} ({len(rejected)})", ""]
        for m in rejected[:30]:
            out.append(f"- {m.job.title} — {m.job.company}: " + "; ".join(render(h.reason, lang) for h in m.failed_rules)
                       + (f" (“{m.failed_rules[0].evidence[:100]}”)" if m.failed_rules and m.failed_rules[0].evidence else ""))
    return "\n".join(out) + "\n"
