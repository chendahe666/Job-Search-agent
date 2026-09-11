"""Design tokens + CSS. Calm, information-dense, readable in long sessions."""

import streamlit as st

CSS = """
<style>
:root{
  --jp-ink:#0f172a; --jp-muted:#64748b; --jp-line:#e2e8f0; --jp-soft:#f8fafc; --jp-card:#ffffff;
  --jp-brand:#4f46e5; --jp-brand-soft:#eef2ff;
  --jp-green:#047857; --jp-green-soft:#ecfdf5; --jp-amber:#b45309; --jp-amber-soft:#fffbeb;
  --jp-red:#b91c1c; --jp-red-soft:#fef2f2; --jp-blue:#1d4ed8; --jp-blue-soft:#eff6ff; --jp-gray-soft:#f1f5f9;
}
.block-container{padding-top:1.2rem; padding-bottom:3rem; max-width:1400px;}
h1,h2,h3{letter-spacing:-0.01em;}
.jp-sub{color:var(--jp-muted); font-size:.92rem; margin-top:-.4rem; margin-bottom:.8rem;}
.jp-badge{display:inline-flex; align-items:center; gap:4px; font-size:.74rem; font-weight:600; padding:2px 8px;
  border-radius:999px; border:1px solid transparent; margin:0 4px 4px 0; white-space:nowrap;}
.jp-green{background:var(--jp-green-soft); color:var(--jp-green); border-color:#a7f3d0;}
.jp-amber{background:var(--jp-amber-soft); color:var(--jp-amber); border-color:#fde68a;}
.jp-red{background:var(--jp-red-soft); color:var(--jp-red); border-color:#fecaca;}
.jp-blue{background:var(--jp-blue-soft); color:var(--jp-blue); border-color:#bfdbfe;}
.jp-gray{background:var(--jp-gray-soft); color:#334155; border-color:var(--jp-line);}
.jp-brand{background:var(--jp-brand-soft); color:var(--jp-brand); border-color:#c7d2fe;}
.jp-hard{background:#111827; color:#fff; border-color:#111827;}
.jp-soft{background:#fff; color:#4338ca; border-color:#c7d2fe;}
.jp-card-title{font-weight:650; font-size:1.02rem; color:var(--jp-ink); line-height:1.25;}
.jp-card-meta{color:var(--jp-muted); font-size:.83rem; margin:2px 0 6px;}
.jp-reason{font-size:.84rem; color:#1e293b; margin:1px 0;}
.jp-gapline{font-size:.82rem; color:var(--jp-amber); margin:1px 0;}
.jp-score{display:flex; flex-direction:column; align-items:center; justify-content:center; width:64px; height:64px;
  border-radius:50%; font-weight:700; font-size:1.15rem; color:var(--jp-ink); margin:auto;}
.jp-score small{font-size:.62rem; font-weight:600; color:var(--jp-muted); margin-top:-3px;}
.jp-stepper{display:flex; gap:6px; flex-wrap:wrap; margin:.2rem 0 1rem;}
.jp-step{flex:1 1 90px; min-width:90px; padding:8px 10px; border-radius:10px; border:1px solid var(--jp-line);
  background:var(--jp-card); font-size:.8rem; color:var(--jp-muted);}
.jp-step b{display:block; color:var(--jp-ink); font-size:.86rem;}
.jp-step.done{border-color:#a7f3d0; background:var(--jp-green-soft);}
.jp-step.active{border-color:var(--jp-brand); background:var(--jp-brand-soft); box-shadow:0 0 0 2px #e0e7ff;}
.jp-funnel-row{display:flex; align-items:center; gap:8px; margin:4px 0; font-size:.82rem;}
.jp-funnel-bar{height:18px; border-radius:6px; background:linear-gradient(90deg,#6366f1,#818cf8); min-width:4px;}
.jp-funnel-label{width:92px; color:var(--jp-muted);}
.jp-funnel-val{font-weight:650; color:var(--jp-ink); min-width:28px;}
.jp-dim{display:grid; grid-template-columns: 120px 1fr 44px; gap:8px; align-items:center; font-size:.82rem; margin:3px 0;}
.jp-dim-track{height:8px; border-radius:6px; background:var(--jp-gray-soft); overflow:hidden;}
.jp-dim-fill{height:8px; border-radius:6px;}
.jp-evt{font-size:.82rem; padding:3px 0; border-bottom:1px dashed var(--jp-line);}
.jp-evt code{font-size:.72rem;}
.jp-quote{border-left:3px solid #a7f3d0; background:var(--jp-soft); padding:6px 10px; border-radius:4px; font-size:.83rem; color:#334155;}
.jp-quote.gap{border-left-color:#fde68a;}
.jp-quote.red{border-left-color:#fecaca;}
.jp-kpi{font-size:1.5rem; font-weight:700; color:var(--jp-ink); line-height:1.1;}
.jp-kpi-label{font-size:.75rem; color:var(--jp-muted); text-transform:uppercase; letter-spacing:.04em;}
.jp-empty{border:1px dashed #cbd5e1; border-radius:12px; padding:28px; text-align:center; color:var(--jp-muted);}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
