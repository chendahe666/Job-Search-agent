"""JobPilot — an evidence-grounded, self-correcting job matching agent.

Pipeline: READ (resume → profile + RAG index) → PLAN → SEARCH (Gemini grounded
search + public ATS APIs) → WORK (fetch & structure postings) → VERIFY
(liveness, consistency, quote checks) → EVALUATE (hard filters + RAG evidence
+ weighted soft scores) → REFLECT (critic decides whether to loop) → REPORT.
"""

__version__ = "2.0.0"
