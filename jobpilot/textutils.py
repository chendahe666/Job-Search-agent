"""Small, dependency-free text helpers (HTML → text, JSON-LD, parsing, fuzzy quotes)."""

from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from typing import Any, Iterable, Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

_WS = re.compile(r"\s+")


def norm_ws(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def norm_key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def stable_id(*parts: str, length: int = 16) -> str:
    raw = "||".join(p or "" for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:length]


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid",
    "ref", "refid", "src", "source", "lever-source", "lever-origin", "trk", "trackingid",
}


def canonical_url(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except ValueError:
        return url.strip()
    if not p.scheme:
        p = urlparse("https://" + url.strip())
    query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=False) if k.lower() not in _TRACKING_PARAMS]
    path = re.sub(r"/+$", "", p.path) or "/"
    for suffix in ("/apply", "/application"):
        if path.endswith(suffix) and ("lever.co" in p.netloc or "ashbyhq.com" in p.netloc):
            path = path[: -len(suffix)]
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower(), path, "", urlencode(query), ""))


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


# --------------------------------------------------------------------------- #
# HTML → text
# --------------------------------------------------------------------------- #
class _TextExtractor(HTMLParser):
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "section", "article", "header", "footer"}
    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0
        self.title = ""
        self._in_title = False
        self.jsonld: list[str] = []
        self._in_jsonld = False
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag == "script" and any(k == "type" and (v or "").lower() == "application/ld+json" for k, v in attrs):
            self._in_jsonld = True
            self._buf = []
            return
        if tag in self.SKIP:
            self.skip_depth += 1
        if tag == "title":
            self._in_title = True
        if tag == "li":
            self.parts.append("\n• ")
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if self._in_jsonld and tag == "script":
            self.jsonld.append("".join(self._buf))
            self._in_jsonld = False
            return
        if tag in self.SKIP and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self._in_title = False
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._buf.append(data)
            return
        if self._in_title:
            self.title += data
        if not self.skip_depth:
            self.parts.append(data)


def html_to_text(markup: str) -> tuple[str, str, list[dict[str, Any]]]:
    """Return (text, <title>, json-ld objects)."""
    if not markup:
        return "", "", []
    if "&lt;" in markup[:2000] and "<" not in markup[:200]:
        markup = html.unescape(markup)  # Greenhouse returns entity-escaped HTML
    parser = _TextExtractor()
    try:
        parser.feed(markup)
        parser.close()
    except Exception:  # malformed HTML — keep what we have
        pass
    text = "".join(parser.parts)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    lines = [ln.strip() for ln in text.split("\n")]
    text = "\n".join(ln for ln in lines if ln and ln != "•")
    objects: list[dict[str, Any]] = []
    for raw in parser.jsonld:
        try:
            data = json.loads(raw.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        for obj in (data if isinstance(data, list) else [data]):
            if isinstance(obj, dict) and "@graph" in obj and isinstance(obj["@graph"], list):
                objects.extend(o for o in obj["@graph"] if isinstance(o, dict))
            elif isinstance(obj, dict):
                objects.append(obj)
    return text, norm_ws(parser.title), objects


def find_jobposting_jsonld(objects: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    for obj in objects:
        kind = obj.get("@type")
        kinds = kind if isinstance(kind, list) else [kind]
        if any(str(k).lower() == "jobposting" for k in kinds):
            return obj
    return None


# --------------------------------------------------------------------------- #
# Parsing helpers
# --------------------------------------------------------------------------- #
def parse_date(value: Any, today: Optional[date] = None) -> Optional[date]:
    """Parse ISO strings, epoch millis, and relative phrases ('Posted 3 days ago')."""
    if value in (None, ""):
        return None
    today = today or datetime.now(timezone.utc).date()
    if isinstance(value, (int, float)):
        ts = value / 1000 if value > 1e11 else value
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc).date()
        except (OverflowError, OSError, ValueError):
            return None
    s = str(value).strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    low = s.lower()
    if "today" in low or "just posted" in low or "just now" in low or re.search(r"\b\d+\s*(hours?|hrs?|minutes?|mins?)\b", low):
        return today
    if "yesterday" in low:
        return today - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*(day|week|month)s?\s*ago", low)
    if m:
        n = int(m.group(1))
        mult = {"day": 1, "week": 7, "month": 30}[m.group(2)]
        return today - timedelta(days=n * mult)
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%d %B %Y", "%d %b %Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


_MONEY = r"\$\s?(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"


def parse_salary(text: str) -> tuple[Optional[float], Optional[float], str]:
    """Find the first USD range in text. Returns (min, max, period)."""
    if not text:
        return None, None, "year"
    second = _MONEY.replace(r"\$\s?", r"\$?\s?", 1)
    pattern = re.compile(_MONEY + r"\s*(?:-|–|—|to)\s*" + second + r"(?:\s*(?:/|per|an?)\s*(hour|hr|year|yr|annum|month))?", re.I)
    m = pattern.search(text)
    if not m:
        return None, None, "year"

    def _val(num: str, k: Optional[str]) -> float:
        v = float(num.replace(",", ""))
        return v * 1000 if k else v

    lo, hi = _val(m.group(1), m.group(2)), _val(m.group(3), m.group(4))
    if m.group(4) and not m.group(2) and lo < 1000:  # "$120-150k"
        lo *= 1000
    unit = (m.group(5) or "").lower()
    if unit in {"hour", "hr"} or (hi < 400 and not unit):
        period = "hour"
    elif unit == "month":
        period = "month"
    else:
        period = "year"
    if period == "year" and hi < 1000:  # "$120-$150" without k — ambiguous, assume thousands
        lo, hi = lo * 1000, hi * 1000
    if lo > hi:
        lo, hi = hi, lo
    return lo, hi, period


def parse_min_years(text: str) -> Optional[float]:
    """Smallest 'N+ years' requirement mentioned (None if absent)."""
    if not text:
        return None
    values = []
    for m in re.finditer(r"(\d{1,2})(?:\.\d)?\s*\+?\s*(?:-|–|to)?\s*(\d{1,2})?\s*\+?\s*years?", text, flags=re.I):
        window = text[m.end(): m.end() + 60].lower()
        before = text[max(0, m.start() - 25): m.start()].lower()
        if "old" in window[:10] or "ago" in window[:10] or "anniversary" in window:
            continue
        if any(w in window for w in ("experience", "industry", "professional", "working", "of ", "in ", "building", "developing")) or "minimum" in before or "at least" in before:
            n = int(m.group(1))
            if 0 < n <= 25:
                values.append(float(n))
    return min(values) if values else None


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|\n+|•", text or "")
    return [norm_ws(p) for p in parts if len(norm_ws(p)) > 2]


def quote_in_source(quote: str, source: str, threshold: float = 0.86) -> bool:
    """True if `quote` appears (nearly) verbatim in `source`.

    This is the anti-hallucination check applied to every LLM-produced quote:
    exact normalized containment, else best sliding-window similarity.
    """
    q, s = norm_key(quote), norm_key(source)
    if not q:
        return False
    if q in s:
        return True
    if len(q) < 12 or not s:
        return False
    window = len(q)
    step = max(1, window // 6)
    best = 0.0
    matcher = SequenceMatcher(autojunk=False)
    matcher.set_seq2(q)
    for start in range(0, max(1, len(s) - window + 1), step):
        matcher.set_seq1(s[start:start + window + step])
        if matcher.real_quick_ratio() < threshold:
            continue
        best = max(best, matcher.ratio())
        if best >= threshold:
            return True
    return False


def extract_json_block(text: str) -> Any:
    """Parse JSON from an LLM reply that may include prose or ``` fences."""
    if text is None:
        raise ValueError("empty response")
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, flags=re.S | re.I)
    candidates = [fence.group(1)] if fence else []
    candidates.append(cleaned)
    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            pass
        for opener, closer in (("[", "]"), ("{", "}")):
            start, end = cand.find(opener), cand.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(cand[start:end + 1])
                except (json.JSONDecodeError, ValueError):
                    continue
    raise ValueError("no JSON found in model response")


def truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + " …[truncated]"
