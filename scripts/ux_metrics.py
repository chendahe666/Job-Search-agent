"""Measure objective UI complexity on a cold start, so UX changes are verifiable.

Usage:  python scripts/ux_metrics.py            (human-readable table)
        python scripts/ux_metrics.py --json     (machine-readable)

Metrics come from a real headless render via Streamlit's AppTest against a throwaway
database, so "the landing page got simpler" is a number, not an opinion.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WIDGET_NODES = {
    "Button", "ButtonGroup", "FileUploader", "TextArea", "TextInput", "SelectSlider", "Selectbox", "SelectBox",
    "Multiselect", "MultiSelect", "Slider", "Checkbox", "Toggle", "Radio", "NumberInput", "DateInput", "ColorPicker",
}


def walk(node) -> list:
    out = []
    children = getattr(node, "children", None) or {}
    for child in (children.values() if hasattr(children, "values") else children):
        out.append(child)
        out.extend(walk(child))
    return out


def _text(node) -> str:
    return str(getattr(node, "label", "") or getattr(node, "value", "") or "")


def measure() -> dict:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
    at.session_state["api_key"] = ""
    at.run()
    if at.exception:
        raise SystemExit("app raised on cold start: " + "; ".join(e.message for e in at.exception))

    main = walk(at.main)
    widgets = [n for n in main if type(n).__name__ in WIDGET_NODES]
    buttons = [n for n in main if type(n).__name__ == "Button"]
    primary = [b for b in buttons if b.proto.type == "primary" and not b.proto.disabled]
    # A wizard should show the user's position once. Both a rendered stepper and a
    # "jump to step" control means the same information is competing with itself.
    step_controls = sum([
        any("jp-stepper" in _text(n) for n in main),
        any(lbl in _text(n) for n in main for lbl in ("跳转", "Jump to")),
    ])

    return {
        "landing_main_nodes": len(main),
        "landing_main_widgets": len(widgets),
        "landing_buttons": len(buttons),
        "landing_enabled_primary_ctas": len(primary),
        "primary_cta_labels": [b.label for b in primary],
        "step_position_controls": step_controls,
        "sidebar_widgets": len([n for n in walk(at.sidebar) if type(n).__name__ in WIDGET_NODES]),
    }


def main() -> None:
    os.environ["JOBPILOT_DB"] = str(Path(tempfile.mkdtemp()) / "metrics.db")
    os.environ["GEMINI_API_KEY"] = ""  # empty, not absent: load_dotenv() would refill it from .env
    os.chdir(ROOT)
    result = measure()
    if "--json" in sys.argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    width = max(len(k) for k in result)
    for key, value in result.items():
        print(f"{key.ljust(width)}  {value}")


if __name__ == "__main__":
    main()
