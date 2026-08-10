from __future__ import annotations

from threading import Lock

import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr

import courserag.infrastructure.knowledge_point_provider as provider_module
from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    KnowledgePointEvidenceRef,
    ProviderUsage,
    sha256_text,
)
from courserag.knowledge_points.provider import (
    InMemoryExtractionCache,
    KnowledgePointExtractionRunner,
    KnowledgePointProviderResponseError,
    KnowledgePointProviderTransientError,
    ProviderExtraction,
)
from tests.courserag.knowledge_points.conftest import evidence, windows


def test_compatible_provider_uses_explicit_json_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    structured_calls: list[dict[str, object]] = []

    class FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            del kwargs

        def with_structured_output(self, schema: object, **kwargs: object) -> object:
            del schema
            structured_calls.append(kwargs)
            return object()

    monkeypatch.setattr(provider_module, "ChatOpenAI", FakeChatOpenAI)

    provider_module.OpenAICompatibleKnowledgePointProvider(
        model="configured-model",
        base_url="https://provider.invalid",
        api_key=SecretStr("configured-secret"),
        timeout_seconds=30,
        structured_output_method="json_mode",
    )

    assert structured_calls == [{"method": "json_mode", "include_raw": True}]


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        ("", "empty_json_content"),
        ("not-json", "invalid_json_content"),
        ('{"candidates":[{"canonical_name":"name"}]}', "schema_mismatch["),
    ],
)
def test_structured_output_error_code_is_content_free(content: str, expected: str) -> None:
    code = provider_module._structured_output_error_code({"raw": AIMessage(content=content)})

    assert code.startswith(expected)
    if content:
        assert content not in code


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-v1"
    structured_output_method = "fake-structured"

    def __init__(self, *, transient_failures: int = 0, bad_reference: bool = False) -> None:
        self.transient_failures = transient_failures
        self.bad_reference = bad_reference
        self.calls = 0
        self._lock = Lock()

    def extract(self, window, prompt: str) -> ProviderExtraction:
        assert prompt == "prompt"
        with self._lock:
            self.calls += 1
            call = self.calls
        if call <= self.transient_failures:
            raise KnowledgePointProviderTransientError("temporary")
        evidence_id = f"ev1_{999:064x}" if self.bad_reference else window.evidence[0].evidence_id
        return ProviderExtraction(
            candidates=(
                KnowledgePointCandidate(
                    canonical_name=f"概念{window.ordinal}",
                    summary="可讲授的知识点",
                    evidence_refs=(
                        KnowledgePointEvidenceRef(
                            evidence_id=evidence_id,
                            role="definition",
                            is_primary=True,
                        ),
                    ),
                    model_confidence=0.01,
                ),
            ),
            usage=ProviderUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def _runner(provider: FakeProvider, cache: InMemoryExtractionCache, **kwargs):
    return KnowledgePointExtractionRunner(
        provider,
        cache,
        prompt="prompt",
        prompt_sha256=sha256_text("prompt"),
        extractor_profile_sha256="e" * 64,
        retry_base_seconds=0,
        sleeper=lambda _: None,
        **kwargs,
    )


def test_cache_prevents_repeat_provider_calls() -> None:
    provider = FakeProvider()
    cache = InMemoryExtractionCache()
    source = windows(evidence(1), evidence(2), maximum=200)
    runner = _runner(provider, cache)

    first = runner.run(source)
    second = runner.run(source)

    assert first == second
    assert provider.calls == 1


def test_transient_failure_retries_only_failed_window() -> None:
    provider = FakeProvider(transient_failures=2)
    source = windows(evidence(1), maximum=200)
    result = _runner(provider, InMemoryExtractionCache(), max_retries=2).run(source)

    assert len(result) == 1
    assert provider.calls == 3


def test_out_of_window_evidence_fails_closed_without_cache() -> None:
    provider = FakeProvider(bad_reference=True)
    cache = InMemoryExtractionCache()
    source = windows(evidence(1), maximum=200)

    with pytest.raises(KnowledgePointProviderResponseError):
        _runner(provider, cache).run(source)
    assert cache._values == {}
