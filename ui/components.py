"""Reusable rendering helpers."""

from __future__ import annotations

from html import escape
from typing import Iterable, Optional

import streamlit as st

from jobpilot.messages import label, render
from jobpilot.schemas import (
    EvidenceStatus, GhostRisk, HardFilterResult, MatchResult, SponsorshipStatus, Tier, VerificationStatus,
)

TIER_COLORS = {"A": "#10b981", "B": "#6366f1", "C": "#f59e0b", "D": "#94a3b8", "rejected": "#ef4444"}


def badge(text: str, tone: str = "gray", icon: str = "") -> str:
    return f'<span class="jp-badge jp-{tone}">{escape(icon + " " if icon else "")}{escape(text)}</span>'


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def score_ring(score: float, tier: Tier) -> str:
    color = TIER_COLORS.get(tier.value, "#94a3b8")
    pct = max(0, min(100, score))
    return (f'<div class="jp-score" style="background:conic-gradient({color} {pct * 3.6}deg, #e2e8f0 0deg);">'
            f'<div style="background:#fff;border-radius:50%;width:52px;height:52px;display:flex;flex-direction:column;'
            f'align-items:center;justify-content:center;">{pct:.0f}<small>{escape(tier.value if tier != Tier.REJECTED else "✕")}</small></div></div>')


def verification_badge(status: VerificationStatus, lang: str) -> str:
    tone = {"verified": "green", "demo": "gray", "unverified": "amber", "dead": "red", "mismatch": "red"}[status.value]
    icon = {"verified": "✓", "demo": "◇", "unverified": "?", "dead": "✕", "mismatch": "≠"}[status.value]
    return badge(label(status, lang), tone, icon)


def sponsorship_badge(m: MatchResult, lang: str, needs: bool) -> str:
    s = m.job.sponsorship.status
    if s == SponsorshipStatus.SPONSORS:
        return badge(label(s, lang), "green", "🛂")
    if s != SponsorshipStatus.UNKNOWN:
        return badge(label(s, lang), "red", "🛂")
    if not needs:
        return ""
    if m.company_intel and m.company_intel.sponsorship in ("frequent", "occasional"):
        return badge(("H-1B " + label(m.company_intel.sponsorship, lang)), "blue", "🛂")
    return badge("?" if lang == "en" else "担保未知", "amber", "🛂")


def ghost_badge(risk: GhostRisk, lang: str) -> str:
    if risk == GhostRisk.LOW:
        return ""
    return badge(("ghost " if lang == "en" else "幽灵风险 ") + label(risk, lang), "amber" if risk == GhostRisk.MEDIUM else "red", "👻")


def stepper(steps: list[str], current: int, done: Optional[Iterable[int]] = None) -> None:
    done = set(done or range(current))
    parts = []
    for i, s in enumerate(steps):
        cls = "active" if i == current else "done" if i in done else ""
        parts.append(f'<div class="jp-step {cls}"><span>{i + 1:02d}</span><b>{escape(s)}</b></div>')
    html('<div class="jp-stepper">' + "".join(parts) + "</div>")


def funnel(rows: list[tuple[str, int]]) -> None:
    top = max([v for _, v in rows] + [1])
    out = []
    for name, value in rows:
        width = int(100 * value / top)
        out.append(f'<div class="jp-funnel-row"><div class="jp-funnel-label">{escape(name)}</div>'
                   f'<div style="flex:1"><div class="jp-funnel-bar" style="width:{max(width, 1)}%"></div></div>'
                   f'<div class="jp-funnel-val">{value}</div></div>')
    html("".join(out))


def dimension_bars(m: MatchResult, lang: str) -> None:
    rows = []
    for key, d in sorted(m.dimensions.items(), key=lambda kv: -kv[1].weight):
        color = "#10b981" if d.score >= 75 else "#6366f1" if d.score >= 55 else "#f59e0b" if d.score >= 35 else "#ef4444"
        unknown = "" if d.known else " ·?"
        rows.append(
            f'<div class="jp-dim" title="{escape(d.detail)}"><div>{escape(label(key, lang))} <span style="color:#94a3b8">'
            f'{d.weight * 100:.0f}%{unknown}</span></div><div class="jp-dim-track"><div class="jp-dim-fill" '
            f'style="width:{d.score:.0f}%;background:{color}"></div></div><div style="text-align:right">{d.score:.0f}</div></div>'
        )
    html("".join(rows))


def hard_filter_list(results: list[HardFilterResult], lang: str) -> None:
    for h in results:
        if not h.passed and h.enforced:
            icon, cls = "✕", "red"
        elif not h.passed:
            icon, cls = "!", "gap"
        elif not h.known:
            icon, cls = "?", "gap"
        else:
            icon, cls = "✓", ""
        tag = badge("HARD" if h.enforced else "SOFT", "hard" if h.enforced else "soft")
        quote = f'<div style="margin-top:3px;color:#64748b">“{escape(h.evidence[:260])}”</div>' if h.evidence else ""
        html(f'<div class="jp-quote {cls}" style="margin-bottom:6px"><b>{icon} {escape(label(h.rule, lang))}</b> {tag}<br>'
             f'{escape(render(h.reason, lang))}{quote}</div>')


def evidence_tone(status: EvidenceStatus) -> str:
    return {"met": "green", "partial": "blue", "gap": "amber", "unverified": "red", "n/a": "gray"}[status.value]


def empty_state(text: str) -> None:
    html(f'<div class="jp-empty">{escape(text)}</div>')
