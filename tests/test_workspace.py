"""Offline regressions for persistence, honesty, source edits, and guided navigation."""
from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from services.workspace import Workspace, filter_jobs, source_draft
from agents.evidence_grounder import EvidenceGrounder
from agents.profile_analyzer import UserProfile
from agents.resume_agent import ResumeAgent, apply_suggestions
from agents.ai_matcher import AIMatcher

ROOT = Path(__file__).resolve().parents[1]
TEST_DATA = ROOT / "local_data"
TEST_DATA.mkdir(exist_ok=True)


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_DATA)
        self.path = Path(self.tmp.name) / "test.db"
        self.store = Workspace(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_persists_without_overwriting_resume_versions(self):
        self.store.put("profile", {"source": "Built a test."}, "me")
        first = self.store.save_version("Original", "Software Engineer", {})
        second = self.store.save_version("Revised", "Software Engineer", {})
        reloaded = Workspace(self.path)
        self.assertEqual(reloaded.get("resume", first["id"])["text"], "Original")
        self.assertNotEqual(first["id"], second["id"])
        self.assertEqual(len(reloaded.all("resume")), 2)

    def test_import_validation_and_dedup(self):
        with self.assertRaises(ValueError):
            self.store.save_job("", "", "")
        with self.assertRaises(ValueError):
            self.store.save_job("AI", "A", "JD", "javascript:alert(1)")
        first, created = self.store.save_job("AI", "A", "JD", "https://example.com/job")
        second, duplicate = self.store.save_job("AI", "A", "New JD", "https://example.com/job")
        self.assertTrue(created)
        self.assertFalse(duplicate)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(second["description"], "JD")

    def test_search_includes_jobs_outside_first_five(self):
        jobs = [{"id": str(i), "title": f"Position {i}"} for i in range(40)]
        self.assertEqual(filter_jobs(jobs, "Position 39")[0]["id"], "39")

    def test_source_draft_does_not_invent_experience(self):
        self.assertEqual(source_draft({"source": "I have never used AWS."}), "I have never used AWS.")

    def test_negated_skill_is_not_verified(self):
        profile = UserProfile(("Python",), "Student", 0, professional_summary="I have never used AWS.")
        report = EvidenceGrounder.audit_match(profile, {"required_skills": ["AWS"], "responsibilities": ["Deploy to AWS"]})
        self.assertEqual(report.evidence_tree[0]["status"], "NEEDS_CONFIRMATION")
        self.assertIsNone(report.hallucination_rate)
        self.assertNotIn("Deploy to AWS", " ".join(report.tailored_bullets))

    def test_ai_prompt_formats_and_explicit_empty_key_disables_env(self):
        self.assertIn('"match_score"', AIMatcher.PROMPT_TEMPLATE.format(profile_json="{}", job_json="{}"))
        with patch.dict(os.environ, {"GEMINI_API_KEY": "not-a-real-key"}):
            self.assertEqual(AIMatcher(api_key="").api_key, "")

    def test_suggestions_require_exact_unique_sources(self):
        agent = ResumeAgent(api_key="fake", provider="groq")
        response = '{"edits":[{"original":"Built a tool.","suggested":"Developed a tool.","reason":"Clarity"},{"original":"not in source","suggested":"Made up"}],"questions":[]}'
        with patch.object(agent, "_call_groq", return_value=response):
            result = agent.suggest("Built a tool.", "Software Engineer")
        self.assertEqual(len(result["edits"]), 1)
        self.assertEqual(apply_suggestions("Built a tool.", result["edits"]), "Developed a tool.")
        with self.assertRaises(ValueError):
            apply_suggestions("Changed text.", result["edits"])

    def test_instruction_echoes_and_added_metrics_are_rejected(self):
        import json
        agent = ResumeAgent(api_key="fake", provider="groq")
        for suggestion in [ResumeAgent.SYSTEM_PROMPT, "Improved accuracy by 90%.", "SYSTEM_PROMPT: secret"]:
            response = json.dumps({"edits": [{"original": "Built a tool.", "suggested": suggestion}], "questions": []})
            with patch.object(agent, "_call_groq", return_value=response):
                result = agent.suggest("Built a tool.", "Software Engineer")
            self.assertEqual(result["edits"], [])


class GuidedUITests(unittest.TestCase):
    """Streamlit's real widget state machine, with an isolated database and no API calls."""
    def setUp(self):
        from streamlit.testing.v1 import AppTest
        self.tmp = tempfile.TemporaryDirectory(dir=TEST_DATA)
        self.env = patch.dict(os.environ, {"ROLESIGNAL_DB": str(Path(self.tmp.name) / "ui.db")})
        self.env.start()
        self.at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=15).run()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def button(self, label):
        return next(b for b in self.at.button if b.label == label)

    def test_empty_input_is_recoverable_and_wizard_saves(self):
        self.assertEqual(len(self.at.exception), 0)
        self.at.button(key="save_profile").click().run()
        self.assertTrue(self.at.error)
        self.at.text_area(key="source_input").set_value("Built a Python project for a university course.").run()
        self.at.button(key="save_profile").click().run()
        self.assertEqual(self.at.session_state["step"], 2)
        self.at.button(key="begin_edit").click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.at.text_area(key="editor").value, "Built a Python project for a university course.")
        self.at.button(key="save_version").click().run()
        self.assertEqual(len(Workspace().all("resume")), 1)
        self.assertEqual(len(self.at.exception), 0)

    def test_navigation_retains_unsaved_material(self):
        self.at.text_area(key="source_input").set_value("Unsaved project notes").run()
        self.at.radio[0].set_value("岗位库").run()
        self.assertEqual(len(self.at.exception), 0)
        self.at.radio[0].set_value("我的素材").run()
        self.assertEqual(self.at.text_area(key="source_input").value, "Unsaved project notes")

    def test_real_job_prepare_navigation_and_tracking(self):
        store = Workspace()
        store.put("profile", {"source": "Built a Python project.", "skills": "Python"}, "me")
        job, _ = store.save_job("AI Engineer", "Test Co", "Build and evaluate models.")
        self.at.radio[0].set_value("岗位库").run()
        self.button("加入投递记录").click().run()
        self.assertEqual(store.get("application", job["id"])["stage"], "已收藏")
        self.at.button(key=f"prepare_{job['id']}").click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.at.session_state["page"], "简历工作台")
        self.assertEqual(self.at.session_state["step"], 2)
        self.at.radio[0].set_value("投递记录").run()
        self.at.button(key=f"save_{job['id']}").click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(store.get("application", job["id"])["follow_up"], "")

    def test_editor_draft_survives_navigation_and_history_restore_backs_it_up(self):
        store = Workspace()
        store.put("profile", {"source": "Original project experience."}, "me")
        original = store.save_version("Saved old version.", "Software Engineer", {})
        self.at.session_state["step"] = 3
        self.at.run()
        self.at.text_area(key="editor").set_value("Important unsaved edit.").run()
        self.at.radio[0].set_value("岗位库").run()
        self.at.radio[0].set_value("简历工作台").run()
        self.assertEqual(self.at.text_area(key="editor").value, "Important unsaved edit.")
        self.at.button(key="restore_version").click().run()
        self.assertEqual(len(self.at.exception), 0)
        self.assertEqual(self.at.text_area(key="editor").value, "Saved old version.")
        self.assertEqual(store.get("resume", original["id"])["text"], "Saved old version.")
        self.assertTrue(any(v["text"] == "Important unsaved edit." for v in store.all("resume")))

    def test_ai_failure_keeps_text_and_does_not_save(self):
        store = Workspace()
        store.put("profile", {"source": "My original experience."}, "me")
        self.at.session_state["step"] = 3
        self.at.run()
        self.at.radio[0].set_value("设置").run()
        self.at.text_input(key="api_key").set_value("fake-test-key").run()
        self.at.text_input(key="model").set_value("fake-model").run()
        self.at.radio[0].set_value("简历工作台").run()
        self.at.checkbox(key="ai_consent").check().run()
        with patch.object(ResumeAgent, "suggest", side_effect=RuntimeError("offline test")):
            self.at.button(key="analyze").click().run()
        self.assertTrue(self.at.error)
        self.assertEqual(self.at.text_area(key="editor").value, "My original experience.")
        self.assertEqual(store.all("resume"), [])
        self.assertEqual(len(self.at.exception), 0)

    def test_language_switch_preserves_draft_and_changes_ui(self):
        self.at.text_area(key="source_input").set_value("我的真实经历，不应被翻译").run()
        self.at.selectbox(key="language").set_value("English").run()
        self.assertEqual(len(self.at.exception), 0)

        self.assertEqual(self.at.text_area(key="source_input").value, "我的真实经历，不应被翻译")
        self.assertEqual(self.at.button(key="save_profile").label, "Save & continue")
        self.assertEqual(self.at.title[0].value, "Resumes")
        self.at.button(key="save_profile").click().run()
        self.at.button(key="begin_edit").click().run()
        self.at.text_area(key="editor").set_value("Unsaved English draft").run()
        self.at.selectbox(key="language").set_value("中文").run()
        self.assertEqual(self.at.text_area(key="editor").value, "Unsaved English draft")
        self.assertEqual(self.at.button(key="save_version").label, "保存新版本")
        self.assertEqual(len(self.at.exception), 0)

    def test_english_navigation_all_pages(self):
        self.at.selectbox(key="language").set_value("English").run()
        for page, title in [("我的素材", "Profile"), ("岗位库", "Jobs"), ("投递记录", "Applications"), ("设置", "Settings")]:
            self.at.radio[0].set_value(page).run()
            self.assertEqual(self.at.title[0].value, title)
            self.assertEqual(len(self.at.exception), 0)


if __name__ == "__main__":
    unittest.main()
