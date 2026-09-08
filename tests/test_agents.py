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


class FakeGeminiClient:
    def __init__(self):
        class FakeModels:
            def generate_content(self, model: str, contents: str, **kwargs):
                content = (
                    '{"summary":"Strong Python evidence with a measurable SQL gap.",'
                    '"matched_strengths":["Python appears in both profile and role."],'
                    '"skill_gaps":["SQL is not listed in the profile."],'
                    '"next_step":"Add a small SQL project to the portfolio."}'
                )
                return SimpleNamespace(text=content)

        self.models = FakeModels()


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

    def test_structures_gemini_llm_response(self):
        explanation = ReasoningAgent(
            client=FakeGeminiClient(), model="gemini-1.5-flash"
        ).explain(self.profile, self.job, 0.72)

        self.assertEqual(explanation.source, "Google Gemini · gemini-1.5-flash")
        self.assertEqual(len(explanation.matched_strengths), 1)
        self.assertFalse(explanation.warning)



class HumanMatcherTests(unittest.TestCase):
    def setUp(self):
        self.profile = ProfileAnalyzer().analyze(
            skills="Python, SQL, Docker",
            experience_level="Mid-level",
            years_experience=3,
            target_roles="Data Engineer",
        )
        self.job = {
            "id": "de-01",
            "title": "Senior Data Engineer",
            "company": "Test Corp",
            "required_skills": ["Python", "SQL", "Airflow"],
            "preferred_skills": ["Docker"],
            "description": "Build pipelines",
        }

    def test_human_matcher_accurately_detects_overlaps_and_gaps(self):
        from agents.human_matcher import HumanMatcher

        matcher = HumanMatcher()
        res = matcher.match_job(self.profile, self.job)

        self.assertIn("Python", res["matched_skills"])
        self.assertIn("SQL", res["matched_skills"])
        self.assertIn("Airflow", res["skill_gaps"])
        self.assertTrue(res["title_matched"])
        self.assertGreater(res["match_score"], 0.6)


class AIMatcherTests(unittest.TestCase):
    def setUp(self):
        self.profile = ProfileAnalyzer().analyze(
            skills="Python, Pandas",
            experience_level="Entry-level",
            years_experience=1,
            target_roles="Data Analyst",
        )
        self.job = {
            "id": "ml-01",
            "title": "Machine Learning Engineer",
            "company": "AI Inc",
            "required_skills": ["Python", "Docker", "Kubernetes"],
            "preferred_skills": ["AWS"],
            "description": "Deploy ML models",
        }

    def test_ai_matcher_flags_hallucinated_inferences(self):
        from agents.ai_matcher import AIMatcher

        matcher = AIMatcher(api_key="")  # Uses simulated naive AI
        res = matcher.match_job(self.profile, self.job)

        self.assertIn("match_score", res)
        # Naive AI often assumes Docker/AWS for developers
        self.assertTrue("hallucination_flag" in res)
        self.assertIn("Stage 2 AI Design", res["method"])


class HybridMatcherTests(unittest.TestCase):
    def test_hybrid_ranks_lexical_and_semantic_overlap_first(self):
        from agents.hybrid_matcher import HybridMatcher

        profile = ProfileAnalyzer().analyze(
            skills="Python, SQL, React",
            experience_level="Mid-level",
            years_experience=2,
            target_roles="Fullstack",
        )
        jobs = [
            {
                "id": "fullstack-match",
                "title": "Fullstack Developer",
                "company": "WebTech",
                "description": "Python SQL and React development",
                "required_skills": ["Python", "React", "SQL"],
                "location": "Remote",
            },
            {
                "id": "irrelevant-role",
                "title": "Embedded C Engineer",
                "company": "HardwareCorp",
                "description": "C++ and assembly firmware",
                "required_skills": ["C++", "Assembly"],
                "location": "Dallas",
            },
        ]

        matcher = HybridMatcher(dense_agent=EmbeddingAgent(encoder=KeywordEncoder()))
        results = matcher.rank_jobs(profile, jobs, top_k=2)

        self.assertEqual(results[0]["id"], "fullstack-match")
        self.assertGreater(results[0]["match_score"], results[1]["match_score"])
        self.assertIn("dense_score", results[0])
        self.assertIn("bm25_score", results[0])


class EvidenceGrounderTests(unittest.TestCase):
    def setUp(self):
        self.profile = ProfileAnalyzer().analyze(
            skills="Python, PyTorch",
            experience_level="Senior",
            years_experience=5,
            professional_summary="Architected scalable deep learning pipelines indexing 1M items.",
        )
        self.job = {
            "id": "nlp-01",
            "title": "Deep Learning Engineer",
            "company": "Cognition",
            "required_skills": ["Python", "PyTorch", "Kubernetes"],
            "responsibilities": ["Train models", "Scale clusters"],
        }

    def test_evidence_grounder_enforces_zero_hallucination(self):
        from agents.evidence_grounder import EvidenceGrounder

        report = EvidenceGrounder.audit_match(self.profile, self.job)

        self.assertEqual(report.hallucination_rate, 0.00)
        self.assertIn("Python", report.verified_skills)
        self.assertIn("PyTorch", report.verified_skills)
        self.assertIn("Kubernetes", report.skill_gaps)
        self.assertEqual(len(report.evidence_tree), 3)

        # Check citation tags in tailored bullets
        self.assertTrue(any("[Src:" in b for b in report.tailored_bullets))
        self.assertGreaterEqual(report.ats_readability_score, 60)


class DataLayerTests(unittest.TestCase):
    def test_mock_database_has_ten_valid_unique_jobs(self):
        jobs = JobRepository(ROOT / "data" / "jobs.json").load_jobs()

        self.assertEqual(len(jobs), 10)
        self.assertEqual(len({job["id"] for job in jobs}), 10)
        self.assertTrue(all(len(job["description"]) > 150 for job in jobs))
        self.assertTrue(all(len(job["required_skills"]) >= 6 for job in jobs))

    def test_expanded_database_has_forty_valid_unique_jobs(self):
        jobs = JobRepository(use_expanded=True).load_jobs()

        self.assertEqual(len(jobs), 40)
        self.assertEqual(len({job["id"] for job in jobs}), 40)
        self.assertTrue(all("required_skills" in job for job in jobs))


if __name__ == "__main__":
    unittest.main()

