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
        # Set it empty rather than removing it: load_dotenv() would otherwise pull the
        # developer's real key out of .env and the suite would hit the live API.
        os.environ["GEMINI_API_KEY"] = ""
        os.chdir(ROOT)

    def assertClean(self, at):
        self.assertFalse(at.exception, [e.message for e in at.exception])

    def test_0_home_offers_exactly_one_next_step(self):
        """A first-time user must land on a screen with one obvious, enabled action."""
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=60)
        at.session_state["api_key"] = ""
        at.run()
        self.assertClean(at)
        enabled_primary = [b for b in at.button if b.proto.type == "primary" and not b.proto.disabled]
        self.assertEqual(len(enabled_primary), 1, [b.label for b in at.button])
        self.assertIn("简历", enabled_primary[0].label)

    def _wizard(self, step: int):
        """A fresh wizard instance parked on one step.

        AppTest replays the widget tree of the previous run, so clicking through a step
        change makes it look up widgets the new step never rendered. Each step gets its
        own instance instead; shared state travels through the database, which also
        proves the wizard actually persists what you type.
        """
        at = AppTest.from_string(VIEW.format(mod="profile", fn="render"), default_timeout=60)
        at.session_state["api_key"] = ""
        at.session_state["wizard_step"] = step
        at.session_state["wizard_max_step"] = 4
        at.run()
        self.assertClean(at)
        return at

    def test_1_wizard_to_demo_run_to_matches(self):
        at = self._wizard(0)
        at.text_area(key="resume_paste").input(RESUME).run()
        _btn(at, "解析简历").click().run()
        self.assertClean(at)
        _btn(at, "下一步").click().run()
        self.assertEqual(at.session_state["wizard_step"], 1)

        targets = self._wizard(1)
        targets.multiselect(key="tg_titles").set_value(["Machine Learning Engineer", "Data Scientist"]).run()
        targets.multiselect(key="tg_locs").set_value(["Chicago, IL", "Austin, TX"]).run()
        self.assertClean(targets)

        from ui import state as ui_state
        self.assertIn("Machine Learning Engineer", ui_state.get_db().load_preferences().target_titles)

        for step in (2, 3, 4):
            self._wizard(step)

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
