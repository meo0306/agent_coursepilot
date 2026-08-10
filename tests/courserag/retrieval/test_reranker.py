import httpx
import pytest

from courserag.providers.reranker import (
    CachingReranker,
    HTTPRerankerAdapter,
    RerankerFailurePolicy,
    UsageBudget,
    rerank_cache_key,
    rerank_with_policy,
)
from courserag.retrieval.models import RetrievalCandidate


def candidates() -> list[RetrievalCandidate]:
    return [
        RetrievalCandidate(chunk_id="a", document_version_id="dv", text="irrelevant"),
        RetrievalCandidate(chunk_id="b", document_version_id="dv", text="relevant"),
    ]


@pytest.mark.parametrize("provider", ["jina", "cohere", "voyage"])
def test_http_adapter_contract(provider: str) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ],
                "usage": {"total_tokens": 12, "search_units": 1},
            },
        )

    adapter = HTTPRerankerAdapter(
        provider_name=provider,
        model_name="configured-model",
        endpoint="https://provider.invalid/rerank",
        api_key="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    result = adapter.rerank("query", candidates(), top_n=2)
    assert [item.chunk_id for item in result.candidates] == ["b", "a"]
    assert result.candidates[0].rerank_rank == 1
    assert len(seen) == 1


def test_eval_fails_and_production_fallback_is_explicit() -> None:
    adapter = HTTPRerankerAdapter(
        provider_name="jina",
        model_name="configured-model",
        endpoint="https://provider.invalid/rerank",
        api_key="secret",
        max_retries=0,
        client=httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(503, json={}))),
    )
    with pytest.raises(httpx.HTTPStatusError):
        rerank_with_policy(
            adapter,
            "query",
            candidates(),
            top_n=2,
            policy=RerankerFailurePolicy.FAIL_SAMPLE,
        )
    result = rerank_with_policy(
        adapter,
        "query",
        candidates(),
        top_n=2,
        policy=RerankerFailurePolicy.FUSION_ORDER,
    )
    assert result.fallback_applied
    assert result.warnings == ["RERANKER_FAILED_FUSION_ORDER_RETURNED"]


def test_timeout_retries_are_bounded_and_count_against_budget() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise httpx.ReadTimeout("timeout")
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 1.0}]})

    budget = UsageBudget(max_jina_tokens=1_000)
    adapter = HTTPRerankerAdapter(
        provider_name="jina",
        model_name="m",
        endpoint="https://provider.invalid/rerank",
        api_key="secret",
        max_retries=1,
        budget=budget,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _: None,
    )
    result = adapter.rerank("query", candidates(), top_n=1)
    assert calls == 2
    assert result.usage.request_count == 2
    assert budget.jina_tokens > 0


def test_cost_budget_and_cache_key_are_fail_closed_and_order_sensitive() -> None:
    budget = UsageBudget(max_jina_tokens=10)
    budget.reserve("jina", estimated_tokens=10)
    with pytest.raises(RuntimeError, match="budget"):
        budget.reserve("jina", estimated_tokens=1)
    first = rerank_cache_key(
        "q",
        candidates(),
        provider="jina",
        model="m",
        max_document_tokens=10,
        config_sha256="a" * 64,
    )
    second = rerank_cache_key(
        "q",
        list(reversed(candidates())),
        provider="jina",
        model="m",
        max_document_tokens=10,
        config_sha256="a" * 64,
    )
    assert first != second


def test_cache_reuses_provider_result_without_reporting_a_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.9}]})

    adapter = HTTPRerankerAdapter(
        provider_name="jina",
        model_name="m",
        endpoint="https://provider.invalid/rerank",
        api_key="secret",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    cache: dict[str, dict[str, object]] = {}
    cached = CachingReranker(
        adapter,
        cache=cache,
        config_sha256="a" * 64,
        max_document_tokens=1200,
    )
    cached.rerank("query", candidates(), top_n=1)
    replay = cached.rerank("query", candidates(), top_n=1)
    assert calls == 1
    assert replay.usage.request_count == 0
    assert "RERANK_CACHE_HIT" in replay.warnings
