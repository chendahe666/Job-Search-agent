"""Public applicant-tracking-system APIs: the most trustworthy source of truth for a posting.

* Greenhouse: https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{id}  (404 once closed)
* Lever:      https://api.lever.co/v0/postings/{company}/{id}
* Ashby:      https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true
* Workday:    https://{tenant}.wd{n}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/job/{path} (best effort)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from ..schemas import EmploymentType, WorkMode
from ..textutils import html_to_text, parse_date
from .fetcher import Fetcher


@dataclass
class AtsRef:
    ats: str
    token: str
    job_id: str = ""
    extra: str = ""  # workday: site + path


@dataclass
class AtsJob:
    ats: str
    exists: bool
    status: int
    title: str = ""
    company: str = ""
    location: str = ""
    description_text: str = ""
    url: str = ""
    apply_url: str = ""
    date_posted: Any = None
    date_updated: Any = None
    work_mode: WorkMode = WorkMode.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    salary_period: str = "year"
    closed: bool = False


def parse_ats_url(url: str) -> Optional[AtsRef]:
    try:
        p = urlparse(url)
    except ValueError:
        return None
    host, parts = p.netloc.lower(), [x for x in p.path.split("/") if x]
    if host.endswith("greenhouse.io") and len(parts) >= 3 and parts[1] == "jobs":
        return AtsRef("greenhouse", parts[0], re.sub(r"\D", "", parts[2]))
    if host.endswith("greenhouse.io") and "embed" in parts:
        q = parse_qs(p.query)
        if q.get("for") and q.get("token"):
            return AtsRef("greenhouse", q["for"][0], q["token"][0])
    if host in {"jobs.lever.co", "jobs.eu.lever.co"} and len(parts) >= 2:
        return AtsRef("lever", parts[0], parts[1], extra="eu" if ".eu." in host else "")
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        return AtsRef("ashby", parts[0], parts[1])
    m = re.match(r"([\w-]+)\.(wd\d+)\.myworkdayjobs\.com", host)
    if m and "job" in parts:
        idx = parts.index("job")
        site_parts = [x for x in parts[:idx] if not re.fullmatch(r"[a-z]{2}-[A-Z]{2}", x)]
        site = site_parts[-1] if site_parts else ""
        return AtsRef("workday", m.group(1), parts[-1], extra=f"{m.group(2)}|{site}|{'/'.join(parts[idx + 1:])}")
    return None


def _mode(value: str) -> WorkMode:
    v = (value or "").lower().replace("-", "").replace(" ", "")
    if "remote" in v:
        return WorkMode.REMOTE
    if "hybrid" in v:
        return WorkMode.HYBRID
    if "onsite" in v or "inoffice" in v or "office" in v:
        return WorkMode.ONSITE
    return WorkMode.UNKNOWN


def _etype(value: str) -> EmploymentType:
    v = (value or "").lower().replace("-", "").replace(" ", "").replace("_", "")
    if "intern" in v or "coop" in v:
        return EmploymentType.INTERNSHIP
    if "contract" in v or "contractor" in v:
        return EmploymentType.CONTRACT
    if "parttime" in v:
        return EmploymentType.PART_TIME
    if "temp" in v:
        return EmploymentType.TEMPORARY
    if "fulltime" in v or "regular" in v or "permanent" in v:
        return EmploymentType.FULL_TIME
    return EmploymentType.UNKNOWN


def fetch_ats_job(ref: AtsRef, fetcher: Fetcher) -> Optional[AtsJob]:
    try:
        if ref.ats == "greenhouse":
            return _greenhouse(ref, fetcher)
        if ref.ats == "lever":
            return _lever(ref, fetcher)
        if ref.ats == "ashby":
            return _ashby(ref, fetcher)
        if ref.ats == "workday":
            return _workday(ref, fetcher)
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return None


def _greenhouse(ref: AtsRef, f: Fetcher) -> AtsJob:
    status, data = f.get_json(f"https://boards-api.greenhouse.io/v1/boards/{ref.token}/jobs/{ref.job_id}")
    if status in (404, 410) or not data:
        return AtsJob("greenhouse", exists=False, status=status, closed=status in (404, 410))
    text, _, _ = html_to_text(data.get("content", ""))
    location = (data.get("location") or {}).get("name", "")
    mode_value = ""
    for meta in data.get("metadata") or []:
        name = str((meta or {}).get("name", "")).lower()
        if any(k in name for k in ("location type", "workplace", "remote", "work type", "work arrangement")):
            value = meta.get("value")
            mode_value = ", ".join(value) if isinstance(value, list) else str(value or "")
            break
    return AtsJob(
        "greenhouse", True, status, title=data.get("title", ""),
        company=data.get("company_name", "") or ref.token,
        location=location, description_text=text,
        url=data.get("absolute_url", ""), apply_url=data.get("absolute_url", ""),
        date_posted=parse_date(data.get("first_published") or data.get("updated_at")),
        date_updated=parse_date(data.get("updated_at")),
        work_mode=_mode(mode_value) if _mode(mode_value) != WorkMode.UNKNOWN else _mode(location),
    )


def _lever(ref: AtsRef, f: Fetcher) -> AtsJob:
    base = "https://api.eu.lever.co" if ref.extra == "eu" else "https://api.lever.co"
    status, data = f.get_json(f"{base}/v0/postings/{ref.token}/{ref.job_id}")
    if status in (404, 410) or not data:
        return AtsJob("lever", exists=False, status=status, closed=status in (404, 410))
    lists = "\n".join(
        f"{lst.get('text', '')}\n" + html_to_text(lst.get("content", ""))[0] for lst in data.get("lists", [])
    )
    desc = "\n".join(x for x in [data.get("descriptionPlain", ""), lists, data.get("additionalPlain", "")] if x)
    cats = data.get("categories", {}) or {}
    salary = data.get("salaryRange") or {}
    interval = (salary.get("interval") or "").lower()
    return AtsJob(
        "lever", True, status, title=data.get("text", ""), company=ref.token,
        location=cats.get("location", "") or ", ".join(cats.get("allLocations", []) or []),
        description_text=desc, url=data.get("hostedUrl", ""), apply_url=data.get("applyUrl", ""),
        date_posted=parse_date(data.get("createdAt")), work_mode=_mode(data.get("workplaceType", "")),
        employment_type=_etype(cats.get("commitment", "")), salary_min=salary.get("min"),
        salary_max=salary.get("max"), salary_period="hour" if "hour" in interval else "year",
    )


def _ashby(ref: AtsRef, f: Fetcher) -> AtsJob:
    status, data = f.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{ref.token}?includeCompensation=true")
    if not data:
        return AtsJob("ashby", exists=False, status=status)
    job = next((j for j in data.get("jobs", []) if str(j.get("id")) == ref.job_id or ref.job_id in str(j.get("jobUrl", ""))), None)
    if not job:
        return AtsJob("ashby", exists=False, status=404, closed=True)
    comp = job.get("compensation") or {}
    lo = hi = None
    for tier in comp.get("summaryComponents", []) or []:
        if (tier.get("compensationType") or "").lower() == "salary":
            lo, hi = tier.get("minValue"), tier.get("maxValue")
    mode = job.get("workplaceType") or ("Remote" if job.get("isRemote") else "")
    address = job.get("address") or {}
    address = address.get("postalAddress", address) if isinstance(address, dict) else {}
    location = job.get("location", "") or ""
    extra = [address.get("addressRegion"), address.get("addressCountry")] if isinstance(address, dict) else []
    extra = [x for x in extra if x and x.lower() not in location.lower()]
    if extra:
        location = ", ".join([location] + extra) if location else ", ".join(extra)
    return AtsJob(
        "ashby", bool(job.get("isListed", True)), 200, title=job.get("title", ""), company=ref.token,
        location=location, description_text=job.get("descriptionPlain", ""),
        url=job.get("jobUrl", ""), apply_url=job.get("applyUrl", ""), date_posted=parse_date(job.get("publishedAt")),
        work_mode=_mode(mode), employment_type=_etype(job.get("employmentType", "")), salary_min=lo, salary_max=hi,
    )


def _workday(ref: AtsRef, f: Fetcher) -> Optional[AtsJob]:
    wd, site, path = ref.extra.split("|", 2)
    if not site or not path:
        return None
    url = f"https://{ref.token}.{wd}.myworkdayjobs.com/wday/cxs/{ref.token}/{site}/job/{path}"
    status, data = f.get_json(url)
    if status in (404, 410):
        return AtsJob("workday", exists=False, status=status, closed=True)
    if not data or "jobPostingInfo" not in data:
        return None
    info = data["jobPostingInfo"]
    text, _, _ = html_to_text(info.get("jobDescription", ""))
    return AtsJob(
        "workday", bool(info.get("canApply", True)), status, title=info.get("title", ""),
        company=(data.get("hiringOrganization") or {}).get("name", "") or ref.token,
        location=info.get("location", ""), description_text=text, url=info.get("externalUrl", ""),
        apply_url=info.get("externalUrl", ""),
        date_posted=parse_date(info.get("startDate") or info.get("postedOn")),
        employment_type=_etype(info.get("timeType", "")), work_mode=_mode(info.get("remoteType", "") or info.get("location", "")),
        closed=not info.get("canApply", True),
    )
