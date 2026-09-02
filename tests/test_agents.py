"""Fast unit tests that avoid network access and model downloads."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from agents.embedding_agent import EmbeddingAgent
from agents.profile_analyzer import ProfileAnalyzer
from agents.reasoning_agent import ReasoningAgent
from data.retriever import JobRepository


ROOT = Path(__file__).resolve().parents[1]


class KeywordEncoder:
    """Tiny deterministic encoder used to test ranking orchestration."""

    VOCABULARY = ("python", "sql", "react", "aws", "security")

    def encode(self, sentences, **_kwargs):
        if isinstance(sentences, str):
            sentences = [sentences]
        return np.asarray(
            [
                [text.casefold().count(term) for term in self.VOCABULARY]
                for text in sentences
            ],
            dtype=float,
        )


class FakeCompletions:
    def create(self, **_kwargs):
        content = (
            '{"summary":"Strong Python evidence with a measurable SQL gap.",'
            '"matched_strengths":["Python appears in both profile and role."],'
            '"skill_gaps":["SQL is not listed in the profile."],'
            '"next_step":"Add a small SQL project to the portfolio."}'
        )
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class FakeGroqClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=FakeCompletions())


class ProfileAnalyzerTests(unittest.TestCase):
    def test_normalizes_and_deduplicates_profile_input(self):
        profile = ProfileAnalyzer().analyze(
            skills="Python, SQL\npython; Git",
            experience_level="Entry-level",
            years_experience=1,
            target_roles="Data Analyst | ML Engineer",
        )

        self.assertEqual(profile.skills, ("Python", "SQL", "Git"))
        self.assertEqual(profile.target_roles, ("Data Analyst", "ML Engineer"))
        self.assertIn("Candidate skills: Python, SQL, Git", profile.to_embedding_text())

    def test_rejects_an_empty_skill_list(self):
        with self.assertRaisesRegex(ValueError, "at least one skill"):
            ProfileAnalyzer().analyze(
                skills="  ,  ",
                experience_level="Student",
                years_experience=0,
            )


class EmbeddingAgentTests(unittest.TestCase):
    def test_ranks_semantically_aligned_job_first(self):
        jobs = [
            {
                "id": "frontend",
                "title": "React Engineer",
                "company": "A",
                "description": "Build React interfaces",
                "required_skills": ["React"],
                "location": "Remote",
            },
            {
                "id": "data",
                "title": "Python Data Engineer",
                "company": "B",
                "description": "Develop Python and SQL pipelines",
                "required_skills": ["Python", "SQL"],
                "location": "Chicago",
            },
        ]
        matcher = EmbeddingAgent(encoder=KeywordEncoder())

        results = matcher.rank_jobs("Python SQL developer", jobs, top_k=2)

        self.assertEqual(results[0]["id"], "data")
        self.assertEqual(results[0]["match_rank"], 1)
        self.assertGreater(results[0]["match_score"], results[1]["match_score"])
        self.assertNotIn("match_score", jobs[0], "Input dictionaries must not mutate")


class ReasoningAgentTests(unittest.TestCase):
    def setUp(self):
        self.profile = ProfileAnalyzer().analyze(
            skills="Python, Docker",
            experience_level="Entry-level",
            years_experience=1,
        )
        self.job = {
            "title": "Backend Engineer",
            "company": "Test Co",
            "description": "Build Python services backed by SQL.",
            "required_skills": ["Python", "SQL"],
            "preferred_skills": ["Docker"],
        }

    def test_local_fallback_names_evidence_and_gaps(self):
        explanation = ReasoningAgent(api_key="").explain(
            self.profile, self.job, 0.72
        )

        self.assertEqual(explanation.source, "Local evidence fallback")
        self.assertIn("Python", explanation.matched_strengths[0])
        self.assertIn("SQL", explanation.skill_gaps)

    def test_structures_llm_response(self):
        explanation = ReasoningAgent(
            client=FakeGroqClient(), model="test-model"
        ).explain(self.profile, self.job, 0.72)

        self.assertEqual(explanation.source, "Groq · test-model")
        self.assertEqual(len(explanation.matched_strengths), 1)
        self.assertFalse(explanation.warning)


class DataLayerTests(unittest.TestCase):
    def test_mock_database_has_ten_valid_unique_jobs(self):
        jobs = JobRepository(ROOT / "data" / "jobs.json").load_jobs()

        self.assertEqual(len(jobs), 10)
        self.assertEqual(len({job["id"] for job in jobs}), 10)
        self.assertTrue(all(len(job["description"]) > 150 for job in jobs))
        self.assertTrue(all(len(job["required_skills"]) >= 6 for job in jobs))


if __name__ == "__main__":
    unittest.main()
