"""Headless UI tests with Streamlit's AppTest (skipped automatically if Streamlit isn't installed)."""

import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from streamlit.testing.v1 import AppTest
except Exception:  # pragma: no cover
    AppTest = None

ROOT = Path(__file__).resolve().parents[1]
RESUME = """Dahe Chen
Kansas City, MO

EDUCATION
University of Missouri-Kansas City - M.S. Computer Science, May 2027

EXPERIENCE
Machine Learning Research Assistant  Aug 2024 - Present
UMKC AI Lab
- Built a RAG pipeline with FAISS and Gemini embeddings for 50k documents
- Deployed PyTorch models on AWS with Docker and FastAPI

SKILLS
Python, SQL, PyTorch, Docker, AWS, FastAPI
"""

VIEW = """
import streamlit as st
from ui import state, styles
from ui.views import {mod}
state.init(); styles.inject()
{mod}.{fn}()
"""


def _btn(at, text):
    for b in at.button:
        if text in b.label:
            return b
    raise AssertionError(f"button {text!r} not in {[b.label for b in at.button]}")


@unittest.skipIf(AppTest is None, "streamlit not installed")
class UITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ["JOBPILOT_DB"] = str(Path(cls.tmp) / "ui.db")
        os.environ.pop("GEMINI_API_KEY", None)
        os.chdir(ROOT)

    def assertClean(self, at):
        self.assertFalse(at.exception, [e.message for e in at.exception])

    def test_1_wizard_to_demo_run_to_matches(self):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.session_state["api_key"] = ""
        at.run()
        self.assertClean(at)
        at.text_area(key="resume_paste").input(RESUME).run()
        _btn(at, "解析简历").click().run()
        self.assertClean(at)
        _btn(at, "下一步").click().run()
        at.multiselect(key="tg_titles").set_value(["Machine Learning Engineer", "Data Scientist"]).run()
        at.multiselect(key="tg_locs").set_value(["Chicago, IL", "Austin, TX"]).run()
        for _ in range(3):
            _btn(at, "下一步").click().run() if any("下一步" in b.label for b in at.button) else _btn(at, "确认并开始").click().run()
            self.assertClean(at)
        self.assertClean(at)

        run = AppTest.from_string(VIEW.format(mod="run", fn="render_page"), default_timeout=60)
        run.session_state["api_key"] = ""
        run.run()
        self.assertClean(run)
        _btn(run, "开始演示运行").click().run()
        from ui import runner
        for _ in range(80):
            h = runner.current()
            if h and not h.running:
                break
            time.sleep(0.25)
        self.assertEqual(runner.current().report.status, "completed")
        run.run()
        self.assertClean(run)

        m = AppTest.from_string(VIEW.format(mod="matches", fn="render_page"), default_timeout=60)
        m.run()
        self.assertClean(m)
        _btn(m, "收藏").click().run()
        _btn(m, "生成简历要点").click().run()
        self.assertClean(m)

    def test_2_other_pages(self):
        for mod in ("pipeline", "reports", "settings"):
            a = AppTest.from_string(VIEW.format(mod=mod, fn="render_page"), default_timeout=60)
            a.run()
            self.assertClean(a)
        en = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        en.session_state["lang"] = "en"
        en.run()
        self.assertClean(en)


if __name__ == "__main__":
    unittest.main()
