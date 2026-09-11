import json
import unittest
from datetime import date, timedelta

from jobpilot.evaluate.hard_filters import evaluate_hard_filters, location_matches
from jobpilot.extract import heuristics as H
from jobpilot.extract.builder import WorkEvidence
from jobpilot.llm.gemini import GeminiClient, GeminiError, to_gemini_schema
from jobpilot.messages import T, render
from jobpilot.schemas import (
    CandidateProfile, JobCandidate, JobPosting, SearchPreferences, Seniority, SponsorshipSignal, SponsorshipStatus,
    Verification, VerificationStatus, WorkMode, msg,
)
from jobpilot.search.ats import parse_ats_url
from jobpilot.search.planner import SearchPlan
from jobpilot.taxonomy import term_in_text
from jobpilot.textutils import canonical_url, parse_salary, quote_in_source
from jobpilot.verify.verifier import Verifier


class TextTests(unittest.TestCase):
    def test_word_boundaries_fix_substring_bug(self):
        self.assertFalse(term_in_text("go", "Strong algorithms background"))
        self.assertTrue(term_in_text("go", "Built services in Go"))
        self.assertFalse(term_in_text("r", "research and reporting"))
        self.assertTrue(term_in_text("c++", "C++ and Rust"))

    def test_quote_verification(self):
        src = "Built a RAG pipeline with FAISS and Gemini embeddings for 50k documents"
        self.assertTrue(quote_in_source("built a RAG pipeline with FAISS", src))
        self.assertFalse(quote_in_source("Managed Kubernetes clusters for 200 services", src))

    def test_salary_and_urls(self):
        self.assertEqual(parse_salary("$120-150k"), (120000.0, 150000.0, "year"))
        self.assertEqual(parse_salary("$45 - $60/hr")[2], "hour")
        self.assertEqual(canonical_url("https://jobs.lever.co/a/b/apply?utm_source=x"), "https://jobs.lever.co/a/b")
        self.assertEqual(parse_ats_url("https://job-boards.greenhouse.io/stripe/jobs/123").token, "stripe")


class SponsorshipTests(unittest.TestCase):
    def test_detects_statements(self):
        cases = {
            "We are unable to sponsor visas at this time.": SponsorshipStatus.NO_SPONSORSHIP,
            "Must be authorized to work in the US without the need for current or future visa sponsorship.": SponsorshipStatus.NO_SPONSORSHIP,
            "Must be a U.S. citizen.": SponsorshipStatus.CITIZEN_ONLY,
            "Requires an active Secret security clearance.": SponsorshipStatus.CLEARANCE,
            "H-1B sponsorship is available.": SponsorshipStatus.SPONSORS,
            "We build great products.": SponsorshipStatus.UNKNOWN,
        }
        for text, expected in cases.items():
            self.assertEqual(H.detect_sponsorship(text).status, expected, text)


def _job(**kw):
    base = dict(id="j", url="https://x", title="Machine Learning Engineer", company="Acme", location_text="Austin, TX",
                work_mode=WorkMode.HYBRID, seniority=Seniority.MID, date_posted=date.today() - timedelta(days=3),
                verification=Verification(status=VerificationStatus.VERIFIED))
    base.update(kw)
    return JobPosting(**base)


class HardFilterTests(unittest.TestCase):
    def setUp(self):
        self.prefs = SearchPreferences(target_titles=["ML Engineer"], locations=["San Francisco Bay Area, CA", "Austin, TX"],
                                       seniority=[Seniority.ENTRY, Seniority.MID], needs_sponsorship=True, posted_within_days=14)
        self.profile = CandidateProfile(years_experience=1.5, skills=["Python"])

    def rules(self, job):
        return {h.rule: h for h in evaluate_hard_filters(job, self.prefs, self.profile)}

    def test_metro_matching(self):
        self.assertEqual(location_matches("Sunnyvale, CA", self.prefs.locations), "San Francisco Bay Area, CA")
        self.assertIsNone(location_matches("Denver, CO", self.prefs.locations))

    def test_rejections_carry_evidence(self):
        r = self.rules(_job(sponsorship=SponsorshipSignal(status=SponsorshipStatus.NO_SPONSORSHIP, quote="We do not sponsor.")))
        self.assertFalse(r["work_authorization"].passed)
        self.assertEqual(r["work_authorization"].evidence, "We do not sponsor.")
        self.assertFalse(self.rules(_job(seniority=Seniority.STAFF))["seniority"].passed)
        self.assertFalse(self.rules(_job(min_years_experience=6))["years_experience"].passed)
        self.assertFalse(self.rules(_job(location_text="Denver, CO"))["location"].passed)
        self.assertFalse(self.rules(_job(date_posted=date.today() - timedelta(days=40)))["posted_age"].passed)
        self.assertFalse(self.rules(_job(work_mode=WorkMode.REMOTE, location_text="Remote - Canada"))["location"].passed)

    def test_unknown_facts_pass_with_warning(self):
        r = self.rules(_job(seniority=Seniority.UNKNOWN, date_posted=None, location_text=""))
        self.assertTrue(r["seniority"].passed and not r["seniority"].known)
        self.assertTrue(r["posted_age"].passed and not r["posted_age"].known)

    def test_disabled_rule_is_soft(self):
        self.prefs.hard_rules.location = False
        r = self.rules(_job(location_text="Denver, CO"))
        self.assertFalse(r["location"].passed)
        self.assertFalse(r["location"].enforced)


class VerifierTests(unittest.TestCase):
    def test_statuses(self):
        v = Verifier()
        job = _job(description_text="Acme is hiring " * 60)
        ok = v.verify(job.model_copy(), JobCandidate(title="ML Engineer", company="Acme", url="https://x"),
                      WorkEvidence(method="ats:greenhouse", ats="greenhouse", ats_exists=True, http_status=200, text_len=900))
        self.assertEqual(ok.status, VerificationStatus.VERIFIED)
        dead = v.verify(job.model_copy(), JobCandidate(url="https://x"), WorkEvidence(ats="greenhouse", ats_exists=False, http_status=404))
        self.assertEqual(dead.status, VerificationStatus.DEAD)
        mism = v.verify(job.model_copy(), JobCandidate(title="Data Scientist", company="Acme", url="https://x"),
                        WorkEvidence(method="html", http_status=200, text_len=900, page_title="Machine Learning Engineer | Acme"))
        self.assertEqual(mism.status, VerificationStatus.MISMATCH)


class GeminiClientTests(unittest.TestCase):
    def test_retries_then_succeeds_and_meters(self):
        calls = []

        def transport(method, url, body, headers, timeout):
            calls.append(url)
            if len(calls) == 1:
                return 503, {"error": {"message": "overloaded"}}, {"Retry-After": "0"}
            return 200, {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}, "groundingMetadata": {"webSearchQueries": ["q"]}}],
                         "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}, {}

        client = GeminiClient("k", transport=transport, sleep=lambda s: None)
        resp = client.generate("hi", tools=["google_search"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(client.usage.usage.search_queries, 1)
        self.assertEqual(resp.text, '{"a": 1}')

    def test_schema_rejection_degrades(self):
        seen = []

        def transport(method, url, body, headers, timeout):
            seen.append(json.loads(json.dumps(body)))
            gen = body["generationConfig"]
            if "responseFormat" in gen:
                return 400, {"error": {"message": 'Invalid JSON payload received. Unknown name "responseFormat": Cannot find field.'}}, {}
            if "responseJsonSchema" in gen:
                return 400, {"error": {"message": "Unknown name responseJsonSchema"}}, {}
            return 200, {"candidates": [{"content": {"parts": [{"text": '{"jobs": []}'}]}}]}, {}

        from jobpilot.llm.prompts import SearchResults
        client = GeminiClient("k", transport=transport)
        obj, _ = client.generate_json("x", SearchResults)
        self.assertEqual(obj.jobs, [])
        self.assertEqual(seen[-1]["generationConfig"].get("responseMimeType"), "application/json")
        n = len(seen)
        client.generate_json("y", SearchResults)  # remembered: no more failed attempts
        self.assertEqual(len(seen), n + 1)
        self.assertIn("JSON Schema", seen[-1]["contents"][0]["parts"][-1]["text"])

    def test_unrelated_400_is_not_masked(self):
        def transport(method, url, body, headers, timeout):
            return 400, {"error": {"message": "Request contains an invalid argument: contents too long"}}, {}
        from jobpilot.llm.prompts import SearchResults
        with self.assertRaises(GeminiError):
            GeminiClient("k", transport=transport).generate_json("x", SearchResults, repair=False)

    def test_auth_error_not_retried(self):
        n = []

        def transport(method, url, body, headers, timeout):
            n.append(1)
            return 400, {"error": {"message": "API key not valid"}}, {}

        with self.assertRaises(GeminiError):
            GeminiClient("bad", transport=transport).generate("x")
        self.assertEqual(len(n), 1)

    def test_schema_keeps_title_property(self):
        from jobpilot.schemas import JobCandidate
        from pydantic import BaseModel

        class X(BaseModel):
            items: list[JobCandidate]

        schema = to_gemini_schema(X)
        self.assertIn("title", schema["properties"]["items"]["items"]["properties"])
        self.assertNotIn("$defs", json.dumps(schema))


class PlanAndMessagesTests(unittest.TestCase):
    def test_plan_mutations_never_touch_constraints(self):
        prefs = SearchPreferences(target_titles=["Machine Learning Engineer"], locations=["Austin, TX"])
        before = prefs.model_dump_json()
        plan = SearchPlan(CandidateProfile(skills=["Python"]), prefs)
        for s in ["ats_sites", "title_synonyms", "skill_focus", "sponsor_focus", "seniority_terms", "metro_expansion", "recency"]:
            plan.apply(s)
        self.assertGreater(len(plan.pending()), 1)
        self.assertEqual(prefs.model_dump_json(), before)
        self.assertIsNone(plan.apply("recency"))  # each strategy applies once

    def test_message_templates_render_in_both_languages(self):
        for key in T:
            for lang in ("zh", "en"):
                out = render(msg(key, detail="d", location="L", mode="remote", level="high", need="3", have="1", etype="contract",
                                 days=3, limit=7, max="1", min="2", company="C", keyword="k", met=1, total=2, examples="e",
                                 range="r", rule="location", pct=10, n=1, passed=1, shortlisted=0, titles="t", skills="s",
                                 exclude="x", cities="c", queries="q", state="CA", target=5, updated=1), lang)
                self.assertNotIn("{", out, key)


if __name__ == "__main__":
    unittest.main()


class EvergreenTest(unittest.TestCase):
    def test_old_but_recently_updated_posting_is_kept_with_warning(self):
        prefs = SearchPreferences(target_titles=["ML"], locations=["Austin, TX"], posted_within_days=14)
        job = _job(date_posted=date.today() - timedelta(days=400), date_updated=date.today() - timedelta(days=2))
        rule = {h.rule: h for h in evaluate_hard_filters(job, prefs, CandidateProfile(years_experience=2))}["posted_age"]
        self.assertTrue(rule.passed)
        self.assertFalse(rule.known)
        self.assertEqual(rule.reason.key, "hf.age.updated")
