"""Employer sponsorship intelligence (soft signal) — cached, grounded, or imported from USCIS data."""

from __future__ import annotations

import csv
import io
import re
from typing import Optional

from ..llm.gemini import GeminiClient, GeminiError
from ..llm.prompts import INTEL_PROMPT, INTEL_SYSTEM, CompanyIntelDTO
from ..schemas import CompanyIntel
from ..storage.db import Database
from ..verify.verifier import company_core

LEVELS = {"frequent", "occasional", "rare", "none_found", "unknown"}


def company_key(name: str) -> str:
    return company_core(name).replace(" ", "")


class CompanyIntelService:
    def __init__(self, db: Database, llm: Optional[GeminiClient] = None) -> None:
        self.db = db
        self.llm = llm

    def cached(self, company: str) -> Optional[CompanyIntel]:
        return self.db.get_company_intel(company_key(company)) if company else None

    def lookup(self, company: str, title: str) -> Optional[CompanyIntel]:
        if not company:
            return None
        hit = self.cached(company)
        if hit or self.llm is None:
            return hit
        try:
            dto, resp = self.llm.generate_json(INTEL_PROMPT.format(company=company, title=title), CompanyIntelDTO,
                                               system=INTEL_SYSTEM, tools=["google_search"])
        except GeminiError:
            return None
        level = dto.sponsorship.strip().lower()
        intel = CompanyIntel(company=company, sponsorship=level if level in LEVELS else "unknown", note=dto.note[:300],
                             source_url=dto.source_url or (resp.sources[0].uri if resp.sources else ""))
        self.db.put_company_intel(company_key(company), intel)
        return intel

    def import_uscis_csv(self, data: bytes) -> int:
        """Import a USCIS H-1B Employer Data Hub export. Column names vary by year, so detect them."""
        text = data.decode("utf-8-sig", errors="replace")
        sample = text[:5000]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        if not reader.fieldnames:
            return 0
        employer_col = next((c for c in reader.fieldnames if re.search(r"employer|petitioner", c, re.I)), None)
        approval_cols = [c for c in reader.fieldnames if re.search(r"approv", c, re.I)]
        if not employer_col or not approval_cols:
            return 0
        totals: dict[str, tuple[str, float]] = {}
        for row in reader:
            name = (row.get(employer_col) or "").strip()
            if not name:
                continue
            count = 0.0
            for col in approval_cols:
                try:
                    count += float(str(row.get(col, "0")).replace(",", "") or 0)
                except ValueError:
                    continue
            key = company_key(name)
            prev = totals.get(key, (name, 0.0))
            totals[key] = (prev[0], prev[1] + count)
        for key, (name, count) in totals.items():
            level = "frequent" if count >= 50 else "occasional" if count >= 3 else "rare" if count >= 1 else "none_found"
            self.db.put_company_intel(key, CompanyIntel(company=name, sponsorship=level,
                                                        note=f"{count:,.0f} H-1B approvals in imported USCIS data",
                                                        source_url="USCIS H-1B Employer Data Hub (imported)"))
        return len(totals)
