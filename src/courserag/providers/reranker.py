from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, MutableMapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from courserag.retrieval.models import RetrievalCandidate


class RerankerFailurePolicy(StrEnum):
    FAIL_SAMPLE = "fail_sample"
    FUSION_ORDER = "fusion_order"


class RerankerUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_tokens: int = Field(default=0, ge=0)
    search_units: int = Field(default=0, ge=0)
    request_count: int = Field(default=1, ge=0)


class RerankResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[RetrievalCandidate]
    provider: str
    model: str
    usage: RerankerUsage = Field(default_factory=RerankerUsage)
    fallback_applied: bool = False
    warnings: list[str] = Field(default_factory=list)


class RerankerPort(Protocol):
    provider_name: str
    model_name: str

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], *, top_n: int
    ) -> RerankResult: ...


@dataclass
class UsageBudget:
    max_jina_tokens: int = 8_000_000
    max_cohere_search_units: int = 500
    jina_tokens: int = 0
    cohere_search_units: int = 0

    def reserve(self, provider: str, *, estimated_tokens: int, search_units: int = 1) -> None:
        if provider == "jina" and self.jina_tokens + estimated_tokens > self.max_jina_tokens:
            raise RuntimeError("Jina evaluation token budget would be exceeded")
        if provider == "cohere" and (
            self.cohere_search_units + search_units > self.max_cohere_search_units
        ):
            raise RuntimeError("Cohere evaluation Search Unit budget would be exceeded")
        if provider == "jina":
            self.jina_tokens += estimated_tokens
        if provider == "cohere":
            self.cohere_search_units += search_units


def rerank_cache_key(
    query: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    provider: str,
    model: str,
    max_document_tokens: int,
    config_sha256: str,
) -> str:
    payload = {
        "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "candidate_sha256": [
            hashlib.sha256(f"{item.chunk_id}\0{item.text}".encode()).hexdigest()
            for item in candidates
        ],
        "provider": provider,
        "model": model,
        "max_document_tokens": max_document_tokens,
        "config_sha256": config_sha256,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


class HTTPRerankerAdapter:
    def __init__(
        self,
        *,
        provider_name: str,
        model_name: str,
        endpoint: str,
        api_key: str,
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_document_tokens: int = 1200,
        budget: UsageBudget | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_request_interval_seconds: float = 0.0,
    ) -> None:
        if provider_name not in {"jina", "cohere", "voyage"}:
            raise ValueError("Unsupported HTTP reranker Provider")
        if not model_name or not endpoint or not api_key:
            raise ValueError("Reranker model, endpoint, and API key are required")
        self.provider_name = provider_name
        self.model_name = model_name
        self.endpoint = endpoint
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.max_document_tokens = max_document_tokens
        self.budget = budget
        self.client = client or httpx.Client()
        self.sleep = sleep
        self.clock = clock
        self.min_request_interval_seconds = min_request_interval_seconds
        self._last_request_at: float | None = None

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], *, top_n: int
    ) -> RerankResult:
        documents = [_truncate(item.text, self.max_document_tokens) for item in candidates]
        estimate = _estimate_tokens(query, documents)
        budget_estimate = int(estimate * 1.5)
        payload = self._payload(query, documents, top_n)
        response: httpx.Response | None = None
        request_count = 0
        for attempt in range(self.max_retries + 1):
            self._wait_for_rate_limit()
            if self.budget is not None:
                self.budget.reserve(
                    self.provider_name,
                    estimated_tokens=budget_estimate,
                    search_units=1,
                )
            request_count += 1
            try:
                response = self.client.post(
                    self.endpoint,
                    headers=self._headers(),
                    json=payload,
                    timeout=self.timeout_seconds,
                )
            except (httpx.TimeoutException, httpx.TransportError):
                if attempt >= self.max_retries:
                    raise
                self.sleep(min(2**attempt, 10))
                continue
            if response.status_code not in {429, 500, 502, 503, 504}:
                break
            if attempt < self.max_retries:
                self.sleep(min(2**attempt, 10))
        assert response is not None
        response.raise_for_status()
        body = response.json()
        results = body.get("results")
        if not isinstance(results, list):
            raise ValueError("Reranker Provider response has no results list")
        ranked: list[RetrievalCandidate] = []
        for rank, item in enumerate(results, start=1):
            source_index = int(item["index"])
            if source_index < 0 or source_index >= len(candidates):
                raise ValueError("Reranker Provider returned an invalid candidate index")
            candidate = candidates[source_index].clone()
            candidate.rerank_score = float(item["relevance_score"])
            candidate.rerank_rank = rank
            ranked.append(candidate)
        usage = self._usage(body, estimated_tokens=estimate, request_count=request_count)
        return RerankResult(
            candidates=ranked[:top_n],
            provider=self.provider_name,
            model=self.model_name,
            usage=usage,
        )

    def _headers(self) -> dict[str, str]:
        if self.provider_name == "cohere":
            return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _payload(self, query: str, documents: Sequence[str], top_n: int) -> dict[str, object]:
        payload: dict[str, object] = {
            "model": self.model_name,
            "query": query,
            "documents": list(documents),
            "top_n": min(top_n, len(documents)),
        }
        if self.provider_name == "jina":
            payload["return_documents"] = False
        return payload

    def _usage(self, body: object, *, estimated_tokens: int, request_count: int) -> RerankerUsage:
        if not isinstance(body, dict):
            return RerankerUsage(
                input_tokens=int(estimated_tokens * 1.5), request_count=request_count
            )
        usage = body.get("usage") or body.get("meta", {}).get("billed_units", {})
        if not isinstance(usage, dict):
            return RerankerUsage(
                input_tokens=int(estimated_tokens * 1.5), request_count=request_count
            )
        tokens = usage.get("total_tokens", usage.get("input_tokens", 0))
        units = usage.get("search_units", usage.get("search_units", 0))
        return RerankerUsage(
            input_tokens=int(tokens or 0),
            search_units=int(units or (1 if self.provider_name == "cohere" else 0)),
            request_count=request_count,
        )

    def _wait_for_rate_limit(self) -> None:
        now = self.clock()
        if self._last_request_at is not None:
            remaining = self.min_request_interval_seconds - (now - self._last_request_at)
            if remaining > 0:
                self.sleep(remaining)
        self._last_request_at = self.clock()


class DisabledReranker:
    provider_name = "disabled"
    model_name = "disabled"

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], *, top_n: int
    ) -> RerankResult:
        del query
        return RerankResult(
            candidates=[item.clone() for item in candidates[:top_n]],
            provider=self.provider_name,
            model=self.model_name,
        )


class CachingReranker:
    def __init__(
        self,
        inner: RerankerPort,
        *,
        cache: MutableMapping[str, dict[str, object]],
        config_sha256: str,
        max_document_tokens: int,
    ) -> None:
        self.inner = inner
        self.provider_name = inner.provider_name
        self.model_name = inner.model_name
        self.cache = cache
        self.config_sha256 = config_sha256
        self.max_document_tokens = max_document_tokens

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], *, top_n: int
    ) -> RerankResult:
        key = rerank_cache_key(
            query,
            candidates,
            provider=self.provider_name,
            model=self.model_name,
            max_document_tokens=self.max_document_tokens,
            config_sha256=self.config_sha256,
        )
        cached = self.cache.get(key)
        if cached is not None:
            result = RerankResult.model_validate(cached)
            result.usage = RerankerUsage(request_count=0)
            result.warnings = [*result.warnings, "RERANK_CACHE_HIT"]
            return result
        result = self.inner.rerank(query, candidates, top_n=top_n)
        self.cache[key] = result.model_dump(mode="python")
        return result


class LocalCrossEncoderAdapter:
    provider_name = "local_cross_encoder"

    def __init__(self, *, model_name: str, model: object | None = None) -> None:
        if model is None:
            raise RuntimeError("Local CrossEncoder dependency/model is not installed")
        self.model_name = model_name
        self.model = model

    def rerank(
        self, query: str, candidates: Sequence[RetrievalCandidate], *, top_n: int
    ) -> RerankResult:
        predict = getattr(self.model, "predict", None)
        if not callable(predict):
            raise RuntimeError("Local CrossEncoder has no callable predict method")
        scores = predict([(query, item.text) for item in candidates])
        ordered = sorted(zip(candidates, scores, strict=True), key=lambda pair: -float(pair[1]))
        output: list[RetrievalCandidate] = []
        for rank, (item, score) in enumerate(ordered[:top_n], start=1):
            candidate = item.clone()
            candidate.rerank_score = float(score)
            candidate.rerank_rank = rank
            output.append(candidate)
        return RerankResult(candidates=output, provider=self.provider_name, model=self.model_name)


def rerank_with_policy(
    reranker: RerankerPort,
    query: str,
    candidates: Sequence[RetrievalCandidate],
    *,
    top_n: int,
    policy: RerankerFailurePolicy,
) -> RerankResult:
    try:
        return reranker.rerank(query, candidates, top_n=top_n)
    except Exception:
        if policy is RerankerFailurePolicy.FAIL_SAMPLE:
            raise
        return RerankResult(
            candidates=[item.clone() for item in candidates[:top_n]],
            provider=reranker.provider_name,
            model=reranker.model_name,
            fallback_applied=True,
            warnings=["RERANKER_FAILED_FUSION_ORDER_RETURNED"],
        )


def _truncate(text: str, max_tokens: int) -> str:
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])


def _estimate_tokens(query: str, documents: Sequence[str]) -> int:
    characters = len(query) + sum(len(item) for item in documents)
    return max(1, (characters + 2) // 3)
