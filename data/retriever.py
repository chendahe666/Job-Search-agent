"""Read and validate the local mock job-posting database.

This repository object is the application's data-layer boundary. The agents do
not know whether postings came from JSON, a database, or a real job API; they
only receive validated dictionaries from this module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JobRepository:
    """Load job postings from a JSON file and enforce the expected schema."""

    REQUIRED_FIELDS = {
        "id",
        "title",
        "company",
        "description",
        "required_skills",
        "location",
    }

    def __init__(
        self,
        data_path: str | Path | None = None,
        *,
        use_expanded: bool = False,
    ) -> None:
        if data_path:
            self.data_path = Path(data_path)
        elif use_expanded:
            self.data_path = Path(__file__).with_name("expanded_jobs.json")
        else:
            self.data_path = Path(__file__).with_name("jobs.json")

    def load_jobs(self) -> list[dict[str, Any]]:
        """Return validated postings while preserving the JSON display order.

        Raises:
            FileNotFoundError: If the configured mock database does not exist.
            ValueError: If the JSON is malformed or a posting lacks core data.
        """

        if not self.data_path.exists():
            raise FileNotFoundError(f"Job dataset not found: {self.data_path}")

        try:
            with self.data_path.open("r", encoding="utf-8") as handle:
                jobs = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid job dataset JSON: {exc}") from exc

        if not isinstance(jobs, list) or not jobs:
            raise ValueError("Job dataset must be a non-empty JSON array.")

        seen_ids: set[str] = set()
        for index, job in enumerate(jobs):
            if not isinstance(job, dict):
                raise ValueError(f"Job at index {index} must be a JSON object.")

            missing = self.REQUIRED_FIELDS.difference(job)
            if missing:
                missing_list = ", ".join(sorted(missing))
                raise ValueError(f"Job at index {index} is missing: {missing_list}")

            job_id = str(job["id"])
            if job_id in seen_ids:
                raise ValueError(f"Duplicate job id in dataset: {job_id}")
            seen_ids.add(job_id)

            if not isinstance(job["required_skills"], list):
                raise ValueError(f"required_skills for {job_id} must be a list.")

        return jobs
