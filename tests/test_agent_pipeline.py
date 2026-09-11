"""End-to-end agent loop with simulated Gemini + HTTP (no network)."""

import unittest

from jobpilot.agent.orchestrator import JobPilotAgent
from jobpilot.llm.gemini import GeminiClient
from jobpilot.rag.embeddings import HashingEmbedder
from jobpilot.rag.retriever import HybridIndex
from jobpilot.report.exporter import matches_csv, run_markdown
from jobpilot.report.tailor import tailor_application
from jobpilot.schemas import (
    CandidateProfile, DegreeLevel, EvidenceStatus, Experience, RunConfig, SearchPreferences, Seniority, SponsorshipStatus, Tier,
    VerificationStatus,
)
from jobpilot.search.fetcher import Fetcher
from jobpilot.storage.db import Database
from tests.fakes import FakeGemini, FakeSession, fake_routes

NOSLEEP = lambda s: None  # noqa: E731


def profile():
    return CandidateProfile(
        name="Test", headline="ML engineer", years_experience=2.0, highest_degree=DegreeLevel.MASTER,
        skills=["Python", "PyTorch", "SQL", "Docker", "AWS"],
        experiences=[Experience(title="ML Engineer", company="Acme", bullets=[
            "Built a RAG pipeline with FAISS and Gemini embeddings for 50k documents",
            "Deployed PyTorch models on AWS with Docker and FastAPI",
        ])],
    )


def prefs():
    return SearchPreferences(target_titles=["Machine Learning Engineer"], locations=["Austin, TX", "Chicago, IL"],
                             seniority=[Seniority.ENTRY, Seniority.MID], needs_sponsorship=True, posted_within_days=14)


class LivePipelineTest(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.gemini = FakeGemini()
        self.llm = GeminiClient("fake-key", sleep=NOSLEEP, transport=self.gemini)
        self.session = FakeSession(fake_routes())
        self.fetcher = Fetcher(None, session=self.session)
        self.events = []
        self.agent = JobPilotAgent(self.db, llm=self.llm, fetcher=self.fetcher,
                                   config=RunConfig(max_iterations=2, target_shortlist=5, max_search_calls=6),
                                   on_event=self.events.append)

    def test_full_loop(self):
        report, matches = self.agent.run(profile(), prefs())
        by_company = {m.job.company: m for m in matches}
        self.assertEqual(report.status, "completed", report.issues)
        self.assertEqual(report.mode, "live")

        # SEARCH + WORK via ATS API
        acme = by_company["Acme AI"]
        self.assertEqual(acme.job.source, "greenhouse")
        self.assertEqual(acme.job.verification.status, VerificationStatus.VERIFIED)
        self.assertEqual(acme.job.sponsorship.status, SponsorshipStatus.SPONSORS)
        self.assertEqual(acme.job.salary_max, 150000.0)
        self.assertTrue(acme.job.grounded)
        # invented requirement ("PhD ... required") not present in JD is dropped
        self.assertFalse(any("PhD" in r.text for r in acme.job.requirements))

        # EVALUATE: verified quote counted, hallucinated quote not counted
        ev = {e.requirement_text: e for e in acme.evidence}
        self.assertEqual(ev["Experience deploying models on AWS with Docker"].status, EvidenceStatus.MET)
        k8s = ev["Experience with Kubernetes"]
        self.assertIn(k8s.status, (EvidenceStatus.UNVERIFIED, EvidenceStatus.GAP, EvidenceStatus.PARTIAL))
        self.assertNotIn("Orchestrated Kubernetes", k8s.quote if k8s.status != EvidenceStatus.UNVERIFIED else "")
        self.assertTrue(acme.hard_pass)
        self.assertIn(acme.tier, (Tier.A, Tier.B))

        # VERIFY: dead + mismatch caught, no-sponsorship excluded with quote
        gamma = by_company.get("Gamma")
        self.assertIsNotNone(gamma)
        self.assertEqual(gamma.job.verification.status, VerificationStatus.DEAD)
        self.assertEqual(gamma.tier, Tier.REJECTED)
        delta = next(m for m in matches if "delta" in m.job.url)
        self.assertEqual(delta.job.verification.status, VerificationStatus.MISMATCH)
        beta = next(m for m in matches if "lever" in m.job.url)
        self.assertEqual(beta.tier, Tier.REJECTED)
        auth = next(h for h in beta.hard_filters if h.rule == "work_authorization")
        self.assertIn("unable to sponsor", auth.evidence.lower())

        # Aggregator handled through Gemini URL context, never fetched directly
        self.assertFalse(any("linkedin.com" in c for c in self.session.calls))
        epsilon = by_company.get("Epsilon")
        self.assertIsNotNone(epsilon)
        self.assertEqual(epsilon.job.extraction_method, "url_context")

        # REFLECT: second iteration ran with a changed plan and found Zeta via Ashby
        self.assertEqual(len(report.iterations), 2)
        self.assertTrue(report.iterations[0].actions)
        self.assertIn("Zeta", by_company)
        self.assertEqual(by_company["Zeta"].job.source, "ashby")

        # REPORT
        self.assertGreater(report.usage.search_queries, 0)
        md = run_markdown(report, matches, profile(), prefs(), "en")
        self.assertIn("Shortlist", md)
        self.assertIn("Acme AI", matches_csv(matches))
        stages = {e.stage for e in self.events}
        self.assertTrue({"read", "plan", "search", "work", "verify", "evaluate", "reflect", "report"} <= stages)

        # Persistence
        self.assertEqual(len(self.db.load_matches(report.run_id)), len(matches))

    def test_tailoring_rejects_fabrication(self):
        report, matches = self.agent.run(profile(), prefs())
        acme = next(m for m in matches if m.job.company == "Acme AI")
        index = HybridIndex.for_profile(profile(), HashingEmbedder())
        result = tailor_application(acme, index, profile(), self.llm, "en")
        verdicts = {b.text: b.verified for b in result.bullets}
        self.assertTrue(verdicts["Deployed PyTorch models on AWS with Docker and FastAPI"])
        self.assertFalse(verdicts["Cut inference latency 40% on Kubernetes"])

    def test_stop_signal(self):
        agent = JobPilotAgent(self.db, llm=self.llm, fetcher=self.fetcher, config=RunConfig(max_iterations=3),
                              should_stop=lambda: True)
        report, _ = agent.run(profile(), prefs())
        self.assertEqual(report.status, "stopped")

    def test_bad_key_fails_cleanly(self):
        def transport(method, url, body, headers, timeout):
            return 400, {"error": {"message": "API key not valid. Please pass a valid API key."}}, {}
        agent = JobPilotAgent(self.db, llm=GeminiClient("bad", sleep=NOSLEEP, transport=transport), fetcher=self.fetcher, config=RunConfig())
        report, matches = agent.run(profile(), prefs())
        self.assertEqual(report.status, "failed")
        self.assertTrue(any(i.severity == "error" for i in report.issues))


class ModelNotFoundTest(unittest.TestCase):
    def test_unknown_model_fails_fast(self):
        calls = []

        def transport(method, url, body, headers, timeout):
            calls.append(url)
            return 404, {"error": {"message": "models/gemini-9 is not found"}}, {}
        db = Database(":memory:")
        agent = JobPilotAgent(db, llm=GeminiClient("k", sleep=NOSLEEP, model="gemini-9", transport=transport),
                              fetcher=Fetcher(None, session=FakeSession({})), config=RunConfig(max_iterations=3))
        report, _ = agent.run(profile(), prefs())
        self.assertEqual(report.status, "failed")
        self.assertEqual(report.stop_reason, "GeminiModelNotFound")
        self.assertLess(len(calls), 10)


class DemoModeTest(unittest.TestCase):
    def test_demo_run_without_key(self):
        db = Database(":memory:")
        report, matches = JobPilotAgent(db, config=RunConfig(demo_mode=True)).run(profile(), prefs())
        self.assertEqual(report.status, "completed")
        self.assertEqual(report.mode, "demo")
        self.assertTrue(matches)
        self.assertTrue(any(m.tier == Tier.REJECTED and m.failed_rules for m in matches))


if __name__ == "__main__":
    unittest.main()


class RefineTest(unittest.TestCase):
    def test_llm_refinement_drops_invented_requirements(self):
        from jobpilot.extract.builder import JobBuilder, WorkEvidence
        from jobpilot.schemas import JobPosting
        from jobpilot.textutils import html_to_text
        from tests.fakes import GREENHOUSE_JD
        llm = GeminiClient("k", sleep=NOSLEEP, transport=FakeGemini())
        builder = JobBuilder(Fetcher(None, session=FakeSession({})), llm)
        text = "Acme AI\n" + html_to_text(GREENHOUSE_JD)[0]
        job = JobPosting(id="1", url="https://acme.example/jobs/1", title="Machine Learning Engineer", company="Acme AI", description_text=text)
        self.assertTrue(builder.needs_refinement(job))
        ev = WorkEvidence()
        self.assertTrue(builder.refine(job, ev))
        self.assertEqual(job.extraction_method, "llm+verified")
        self.assertFalse(any("PhD" in r.text for r in job.requirements))
        self.assertTrue(any("Kubernetes" in r.text for r in job.requirements))
        self.assertEqual(job.sponsorship.status, SponsorshipStatus.SPONSORS)
