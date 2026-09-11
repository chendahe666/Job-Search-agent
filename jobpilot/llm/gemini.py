"""Minimal, dependency-light Gemini REST client.

Why REST instead of the SDK: the repo must run on Python 3.14 on Windows and
survive SDK churn. The Generative Language REST surface used here is stable:

* ``POST /v1beta/models/{model}:generateContent`` with ``tools`` =
  ``[{"google_search": {}}, {"url_context": {}}]`` for live, grounded search,
  ``generationConfig.responseMimeType`` / ``responseJsonSchema`` for JSON.
* ``POST /v1beta/models/{model}:batchEmbedContents`` for embeddings.
* ``GET  /v1beta/models`` to populate the model dropdown dynamically.

Every call is metered (tokens, grounded search queries) so the agent can
enforce budgets and report cost.
"""

from __future__ import annotations

import base64
import copy
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from ..schemas import Usage
from ..textutils import extract_json_block

BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
DEFAULT_EMBED_MODEL = "gemini-embedding-001"

T = TypeVar("T", bound=BaseModel)
Transport = Callable[[str, str, Optional[dict], dict, float], tuple[int, Any, dict]]


class GeminiError(RuntimeError):
    def __init__(self, message: str, status: int = 0, retryable: bool = False) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class GeminiAuthError(GeminiError):
    pass


class GeminiQuotaError(GeminiError):
    pass


class GeminiModelNotFound(GeminiError):
    pass


@dataclass
class GroundingSource:
    uri: str
    title: str = ""


@dataclass
class LLMResponse:
    text: str
    raw: dict[str, Any]
    search_queries: list[str] = field(default_factory=list)
    sources: list[GroundingSource] = field(default_factory=list)
    url_context: list[tuple[str, str]] = field(default_factory=list)
    prompt_tokens: int = 0
    output_tokens: int = 0
    finish_reason: str = ""


class UsageTracker:
    """Thread-safe usage counters shared across one agent run."""

    def __init__(self) -> None:
        self.usage = Usage()
        self._lock = threading.Lock()

    def add(self, **kwargs: int) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self.usage, k, getattr(self.usage, k) + int(v))


def _requests_transport(session: requests.Session) -> Transport:
    def _send(method: str, url: str, body: Optional[dict], headers: dict, timeout: float):
        resp = session.request(method, url, json=body, headers=headers, timeout=timeout)
        try:
            payload = resp.json()
        except ValueError:
            payload = {"error": {"message": resp.text[:500]}}
        return resp.status_code, payload, dict(resp.headers)

    return _send


def to_gemini_schema(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema → self-contained schema (refs inlined, defaults removed)."""
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def resolve(node: Any, in_properties: bool = False) -> Any:
        if isinstance(node, dict):
            if "$ref" in node and not in_properties:
                name = node["$ref"].split("/")[-1]
                return resolve(copy.deepcopy(defs[name]))
            out = {}
            for k, v in node.items():
                if not in_properties and k in {"default", "title", "examples"}:
                    continue  # schema annotations, not property names
                out[k] = resolve(v, in_properties=(k == "properties" and not in_properties))
            any_of = out.get("anyOf")
            if isinstance(any_of, list) and len(any_of) == 2 and {"type": "null"} in any_of:
                other = next(x for x in any_of if x != {"type": "null"})
                if isinstance(other, dict) and isinstance(other.get("type"), str):
                    merged = {**other, "type": [other["type"], "null"]}
                    out.pop("anyOf")
                    out.update(merged)
            return out
        if isinstance(node, list):
            return [resolve(x) for x in node]
        return node

    return resolve(schema)


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        *,
        embed_model: str = DEFAULT_EMBED_MODEL,
        timeout: float = 90.0,
        max_retries: int = 4,
        min_interval_s: float = 0.0,
        usage: Optional[UsageTracker] = None,
        transport: Optional[Transport] = None,
        max_concurrent: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise GeminiAuthError("Missing GEMINI_API_KEY")
        self.api_key = api_key.strip()
        self.model = model or DEFAULT_MODEL
        self.embed_model = embed_model or DEFAULT_EMBED_MODEL
        self.timeout = timeout
        self.max_retries = max_retries
        self.min_interval_s = min_interval_s
        self.usage = usage or UsageTracker()
        self._transport = transport or _requests_transport(requests.Session())
        self._rate_lock = threading.Lock()
        self._last_call = 0.0
        # JSON output negotiation. Current docs use generationConfig.responseFormat.text{mimeType,schema};
        # older endpoints/models accept responseMimeType + responseJsonSchema. We try in order and remember
        # what works (separately for calls with and without built-in tools).
        self._json_formats = ["response_format", "json_schema", "mime_only", "prompt_only"]
        self._fmt_idx = {False: 0, True: 0}
        self._slots = threading.BoundedSemaphore(max(1, max_concurrent))
        self._sleep = sleep

    # ------------------------------------------------------------------ #
    # Low-level HTTP with retries
    # ------------------------------------------------------------------ #
    def _throttle(self) -> None:
        if self.min_interval_s <= 0:
            return
        with self._rate_lock:
            wait = self._last_call + self.min_interval_s - time.monotonic()
            if wait > 0:
                self._sleep(wait)
            self._last_call = time.monotonic()

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict:
        url = f"{BASE_URL}/{path}"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        last_error: Optional[GeminiError] = None
        for attempt in range(self.max_retries + 1):
            try:
                with self._slots:
                    self._throttle()
                    status, payload, resp_headers = self._transport(method, url, body, headers, self.timeout)
            except requests.RequestException as exc:  # network error → retry
                last_error = GeminiError(f"network error: {exc}", retryable=True)
                status, payload, resp_headers = 0, {}, {}
            else:
                if 200 <= status < 300:
                    return payload
                message = (payload or {}).get("error", {}).get("message", str(payload)[:300])
                if status in (401, 403) or (status == 400 and "api key" in message.lower()):
                    raise GeminiAuthError(f"Gemini rejected the API key ({status}): {message}", status)
                if status == 404:
                    raise GeminiModelNotFound(f"Model or endpoint not found ({status}): {message}", status)
                if status in (429, 500, 502, 503, 504):
                    cls = GeminiQuotaError if status == 429 else GeminiError
                    last_error = cls(f"Gemini {status}: {message}", status, retryable=True)
                else:
                    raise GeminiError(f"Gemini {status}: {message}", status)
            if attempt < self.max_retries:
                retry_after = 0.0
                try:
                    retry_after = float((resp_headers or {}).get("Retry-After", 0))
                except (TypeError, ValueError):
                    retry_after = 0.0
                delay = max(retry_after, min(2 ** attempt * 1.5, 30)) + random.uniform(0, 0.5)
                self._sleep(delay)
        assert last_error is not None
        raise last_error

    def _request_counted(self, path: str, body: dict) -> dict:
        try:
            return self._request("POST", path, body)
        except GeminiError:
            self.usage.add(llm_failures=1)
            raise

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def list_models(self) -> list[dict[str, Any]]:
        models: list[dict[str, Any]] = []
        token = ""
        for _ in range(10):
            path = "models?pageSize=200" + (f"&pageToken={token}" if token else "")
            payload = self._request("GET", path)
            models.extend(payload.get("models", []))
            token = payload.get("nextPageToken", "")
            if not token:
                break
        return models

    def generation_models(self) -> list[str]:
        names = []
        for m in self.list_models():
            if "generateContent" in m.get("supportedGenerationMethods", []):
                names.append(m.get("name", "").replace("models/", ""))
        return sorted(set(names), reverse=True)

    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        tools: Sequence[str] = (),
        json_schema: Optional[dict] = None,
        json_mode: bool = False,
        temperature: float = 0.2,
        model: Optional[str] = None,
        inline_files: Sequence[tuple[bytes, str]] = (),
        max_output_tokens: Optional[int] = None,
    ) -> LLMResponse:
        parts: list[dict[str, Any]] = []
        for data, mime in inline_files:
            parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode("ascii")}})
        parts.append({"text": prompt})
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": temperature},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            body["tools"] = [{name: {}} for name in tools]
        if max_output_tokens:
            body["generationConfig"]["maxOutputTokens"] = max_output_tokens
        wants_json = json_schema is not None or json_mode
        path = f"models/{model or self.model}:generateContent"
        if not wants_json:
            payload = self._request_counted(path, body)
            return self._parse_response(payload, grounded="google_search" in tools, url_context="url_context" in tools)

        key = bool(tools)
        last_exc: Optional[GeminiError] = None
        while self._fmt_idx[key] < len(self._json_formats):
            fmt = self._json_formats[self._fmt_idx[key]]
            gen = {k: v for k, v in body["generationConfig"].items()
                   if k not in ("responseFormat", "responseMimeType", "responseJsonSchema")}
            if fmt == "response_format":
                text_fmt: dict[str, Any] = {"mimeType": "application/json"}
                if json_schema is not None:
                    text_fmt["schema"] = json_schema
                gen["responseFormat"] = {"text": text_fmt}
            elif fmt == "json_schema":
                gen["responseMimeType"] = "application/json"
                if json_schema is not None:
                    gen["responseJsonSchema"] = json_schema
            elif fmt == "mime_only":
                gen["responseMimeType"] = "application/json"
            body["generationConfig"] = gen
            try:
                payload = self._request_counted(path, body)
                break
            except GeminiError as exc:
                format_related = re.search(r"unknown name|cannot find field|schema|mime|response_?format|json|unsupported|not supported",
                                           str(exc), re.I)
                if (exc.status != 400 or isinstance(exc, (GeminiAuthError, GeminiModelNotFound)) or not format_related
                        or fmt == "prompt_only"):
                    raise
                last_exc = exc
                self._fmt_idx[key] += 1  # this JSON mode is not accepted here — degrade and remember
        else:
            raise last_exc or GeminiError("No accepted JSON output mode")
        return self._parse_response(payload, grounded="google_search" in tools, url_context="url_context" in tools)

    def _parse_response(self, payload: dict, *, grounded: bool, url_context: bool) -> LLMResponse:
        candidates = payload.get("candidates") or []
        if not candidates:
            feedback = payload.get("promptFeedback", {})
            raise GeminiError(f"Gemini returned no candidates ({feedback.get('blockReason', 'unknown')})")
        cand = candidates[0]
        text = "".join(
            p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought")
        )
        gm = cand.get("groundingMetadata") or {}
        queries = list(gm.get("webSearchQueries") or [])
        sources = [
            GroundingSource(uri=c.get("web", {}).get("uri", ""), title=c.get("web", {}).get("title", ""))
            for c in gm.get("groundingChunks") or []
            if c.get("web", {}).get("uri")
        ]
        ucm = cand.get("urlContextMetadata") or cand.get("url_context_metadata") or {}
        url_meta = [
            (m.get("retrievedUrl") or m.get("retrieved_url", ""), m.get("urlRetrievalStatus") or m.get("url_retrieval_status", ""))
            for m in (ucm.get("urlMetadata") or ucm.get("url_metadata") or [])
        ]
        um = payload.get("usageMetadata") or {}
        prompt_tokens = int(um.get("promptTokenCount", 0)) + int(um.get("toolUsePromptTokenCount", 0))
        output_tokens = int(um.get("candidatesTokenCount", 0)) + int(um.get("thoughtsTokenCount", 0))
        self.usage.add(
            llm_calls=1,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            search_calls=1 if grounded else 0,
            search_queries=len(queries),
            url_context_calls=1 if url_context else 0,
        )
        return LLMResponse(
            text=text,
            raw=payload,
            search_queries=queries,
            sources=sources,
            url_context=url_meta,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            finish_reason=cand.get("finishReason", ""),
        )

    def generate_json(
        self,
        prompt: str,
        model_cls: type[T],
        *,
        system: str = "",
        tools: Sequence[str] = (),
        temperature: float = 0.1,
        inline_files: Sequence[tuple[bytes, str]] = (),
        repair: bool = True,
    ) -> tuple[T, LLMResponse]:
        schema = to_gemini_schema(model_cls)
        # Tools + schema is supported on Gemini 3 models; on others generate() degrades.
        full_prompt = prompt
        schema_native = self._json_formats[min(self._fmt_idx[bool(tools)], 3)] in ("response_format", "json_schema")
        if tools or not schema_native:
            full_prompt += "\n\nReturn ONLY JSON matching this JSON Schema:\n" + json.dumps(schema)
        resp = self.generate(
            full_prompt, system=system, tools=tools, json_schema=schema, temperature=temperature,
            inline_files=inline_files,
        )
        try:
            data = extract_json_block(resp.text)
            return model_cls.model_validate(data), resp
        except (ValueError, ValidationError) as exc:
            if not repair:
                raise GeminiError(f"Invalid JSON from model: {exc}") from exc
            fix_prompt = (
                "The following output failed validation. Fix it so it is valid JSON for the schema. "
                "Do not add new facts; only repair structure.\n\nERROR:\n" + str(exc)[:1500]
                + "\n\nSCHEMA:\n" + json.dumps(schema) + "\n\nOUTPUT:\n" + resp.text[:20000]
            )
            fixed = self.generate(fix_prompt, json_schema=schema, temperature=0.0)
            try:
                data = extract_json_block(fixed.text)
                return model_cls.model_validate(data), resp
            except (ValueError, ValidationError) as exc2:
                raise GeminiError(f"Invalid JSON from model after repair: {exc2}") from exc2

    def embed(
        self,
        texts: Sequence[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        dimensions: int = 768,
        batch_size: int = 100,
    ) -> list[list[float]]:
        out: list[list[float]] = []
        use_task = "embedding-2" not in self.embed_model
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            requests_body = []
            for t in batch:
                req: dict[str, Any] = {
                    "model": f"models/{self.embed_model}",
                    "content": {"parts": [{"text": t[:8000]}]},
                    "outputDimensionality": dimensions,
                }
                if use_task:
                    req["taskType"] = task_type
                requests_body.append(req)
            payload = self._request("POST", f"models/{self.embed_model}:batchEmbedContents", {"requests": requests_body})
            embeddings = payload.get("embeddings", [])
            if len(embeddings) != len(batch):
                raise GeminiError("Embedding count mismatch")
            out.extend(e.get("values", []) for e in embeddings)
            self.usage.add(embed_calls=1)
        return out
