import logging
from types import SimpleNamespace

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import OpenAIEmbeddings
from openai import RateLimitError
from pydantic import BaseModel, SecretStr

from coursepilot.llm import (
    CoursePilotLLMCallError,
    build_coursepilot_system_prompt,
    check_coursepilot_llm_health,
    collect_coursepilot_llm_metadata,
    extract_token_usage,
    generate_structured,
    get_coursepilot_llm,
    hash_prompt,
    summarize_llm_invocations,
)
from coursepilot.prompts.loader import load_prompt
from coursepilot.rag.embeddings import (
    HashingEmbeddings,
    RateLimitRetryEmbeddings,
    get_coursepilot_embeddings,
)
from coursepilot.token_usage import estimate_token_usage, get_deepseek_tokenizer


class _StructuredOutput(BaseModel):
    answer: str


class _NumericOutput(BaseModel):
    answer: int


def _raw_message(*, finish_reason: str = "stop") -> AIMessage:
    return AIMessage(
        content='{"answer": "ok"}',
        response_metadata={
            "finish_reason": finish_reason,
            "token_usage": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
            },
        },
    )


def _raw_message_without_usage(*, content: str = '{"answer": "ok"}') -> AIMessage:
    return AIMessage(content=content, response_metadata={"finish_reason": "stop"})


def _set_llm_health_config(monkeypatch, mode: str) -> None:
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_GENERATION_MODE", "llm")
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_HEALTH_CHECK_MODE", mode)
    monkeypatch.setattr("coursepilot.llm.settings.COMPATIBLE_MODEL", "deepseek-test")
    monkeypatch.setattr("coursepilot.llm.settings.COMPATIBLE_BASE_URL", "https://example.test/v1")
    monkeypatch.setattr("coursepilot.llm.settings.COMPATIBLE_API_KEY", SecretStr("test-key"))


def test_prompt_loader_reads_lesson_prompt():
    prompt = load_prompt("lesson/generate_lesson_design")

    assert "LessonDesignContent" in prompt


def test_embedding_factory_defaults_to_hashing(monkeypatch):
    monkeypatch.setattr(
        "coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_PROVIDER",
        "auto",
    )
    monkeypatch.setattr("coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_MODEL", None)
    monkeypatch.setattr("coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_BASE_URL", None)
    monkeypatch.setattr("coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_API_KEY", None)
    monkeypatch.setattr("coursepilot.rag.embeddings.settings.COMPATIBLE_BASE_URL", None)
    monkeypatch.setattr("coursepilot.rag.embeddings.settings.COMPATIBLE_API_KEY", None)

    assert isinstance(get_coursepilot_embeddings(), HashingEmbeddings)


def test_embedding_factory_openai_compatible(monkeypatch):
    monkeypatch.setattr(
        "coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_PROVIDER",
        "openai-compatible",
    )
    monkeypatch.setattr(
        "coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_MODEL",
        "text-embedding-test",
    )
    monkeypatch.setattr(
        "coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_BASE_URL",
        "https://example.test/v1",
    )
    monkeypatch.setattr(
        "coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_API_KEY",
        SecretStr("test-key"),
    )

    embeddings = get_coursepilot_embeddings()

    assert isinstance(embeddings, RateLimitRetryEmbeddings)
    assert isinstance(embeddings.backend, OpenAIEmbeddings)
    assert embeddings.backend.model == "text-embedding-test"
    assert embeddings.backend.max_retries == 0


def test_embedding_rate_limit_uses_long_exponential_backoff():
    request = httpx.Request("POST", "https://example.test/v1/embeddings")
    response = httpx.Response(429, request=request)
    rate_limit_error = RateLimitError(
        "rate limited",
        response=response,
        body=None,
    )

    class FlakyEmbeddings(HashingEmbeddings):
        def __init__(self):
            super().__init__()
            self.calls = 0

        def embed_query(self, text: str) -> list[float]:
            self.calls += 1
            if self.calls < 3:
                raise rate_limit_error
            return super().embed_query(text)

    backend = FlakyEmbeddings()
    delays = []
    embeddings = RateLimitRetryEmbeddings(
        backend,
        max_retries=4,
        base_delay_seconds=15,
        max_delay_seconds=120,
        sleep=delays.append,
    )

    result = embeddings.embed_query("search")

    assert backend.calls == 3
    assert delays == [15, 30]
    assert result == backend._embed("search")


def test_embedding_rate_limit_honors_retry_after_with_maximum():
    request = httpx.Request("POST", "https://example.test/v1/embeddings")
    response = httpx.Response(429, headers={"retry-after": "300"}, request=request)
    rate_limit_error = RateLimitError(
        "rate limited",
        response=response,
        body=None,
    )

    class OnceRateLimitedEmbeddings(HashingEmbeddings):
        calls = 0

        def embed_query(self, text: str) -> list[float]:
            self.calls += 1
            if self.calls == 1:
                raise rate_limit_error
            return super().embed_query(text)

    delays = []
    embeddings = RateLimitRetryEmbeddings(
        OnceRateLimitedEmbeddings(),
        max_retries=1,
        base_delay_seconds=15,
        max_delay_seconds=120,
        sleep=delays.append,
    )

    embeddings.embed_query("search")

    assert delays == [120]


def test_coursepilot_llm_uses_capability_manifest(monkeypatch):
    get_coursepilot_llm.cache_clear()
    from coursepilot.llm import _configured_model_gateway

    _configured_model_gateway.cache_clear()
    monkeypatch.setattr("coursepilot.llm.settings.COMPATIBLE_MODEL", "deepseek-v4-pro")
    monkeypatch.setattr("coursepilot.llm.settings.COMPATIBLE_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setattr("coursepilot.llm.settings.COMPATIBLE_API_KEY", SecretStr("test-key"))
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_TIMEOUT_SECONDS", 12.5)

    try:
        llm = get_coursepilot_llm()

        assert llm.model_name == "deepseek-v4-pro"
        assert llm.streaming is False
        assert llm.reasoning_effort == "high"
        assert llm.extra_body == {"thinking": {"type": "enabled"}}
        assert isinstance(llm.request_timeout, httpx.Timeout)
        assert llm.request_timeout.read == 120.0
        assert llm.request_timeout.connect == 15.0
        assert llm.request_timeout.write == 30.0
        assert llm.request_timeout.pool == 10.0
        assert llm.max_retries == 0
    finally:
        get_coursepilot_llm.cache_clear()
        _configured_model_gateway.cache_clear()


def test_prompt_hash_and_language_policy_are_stable():
    prompt = build_coursepilot_system_prompt("Return JSON only.")
    prompt_hash = hash_prompt(prompt)

    assert len(prompt_hash) == 64
    assert hash_prompt(prompt) == prompt_hash
    assert "主体内容必须使用中文" in prompt


def test_generate_structured_records_prompt_hash_usage_and_json_mode(monkeypatch):
    captured = {}

    class FakeRunnable:
        def invoke(self, messages):
            captured["messages"] = messages
            return {
                "raw": _raw_message(),
                "parsed": {"answer": "ok"},
                "parsing_error": None,
            }

    class FakeLLM:
        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured["kwargs"] = kwargs
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())

    with collect_coursepilot_llm_metadata(thread_id="thread-1") as collector:
        result = generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=_StructuredOutput,
            payload={"question": "hello"},
            fallback=lambda: _StructuredOutput(answer="fallback"),
        )

    metadata = collector.to_task_metadata()
    invocation = metadata["llm_invocations"][0]

    assert result == _StructuredOutput(answer="ok")
    assert captured["schema"] is _StructuredOutput
    assert captured["kwargs"] == {"method": "json_mode", "include_raw": True}
    assert "主体内容必须使用中文" in captured["messages"][0].content
    assert invocation["prompt_name"] == "lesson/generate_lesson_design"
    assert invocation["fallback_used"] is False
    assert invocation["usage"] == {
        "input_tokens": 3,
        "output_tokens": 2,
        "total_tokens": 5,
        "usage_source": "provider",
        "usage_estimated": False,
    }
    assert metadata["prompt_hashes"]["lesson/generate_lesson_design"]["prompt_sha256"]
    assert metadata["llm_usage_summary"]["total_tokens"] == 5
    assert metadata["llm_usage_summary"]["usage_source_counts"]["provider"] == 1


def test_generate_structured_estimates_usage_when_provider_usage_missing(monkeypatch):
    estimated = {
        "input_tokens": 11,
        "output_tokens": 7,
        "total_tokens": 18,
        "usage_source": "deepseek_v3_tokenizer",
        "usage_estimated": True,
    }

    class FakeRunnable:
        def invoke(self, _messages):
            return {
                "raw": _raw_message_without_usage(),
                "parsed": {"answer": "ok"},
                "parsing_error": None,
            }

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr(
        "coursepilot.llm.estimate_token_usage",
        lambda _messages, _output: estimated,
    )

    with collect_coursepilot_llm_metadata(thread_id="thread-estimated") as collector:
        generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=_StructuredOutput,
            payload={"question": "hello"},
            fallback=lambda: _StructuredOutput(answer="fallback"),
        )

    invocation = collector.to_task_metadata()["llm_invocations"][0]

    assert invocation["usage"] == estimated
    assert invocation["usage"]["usage_estimated"] is True
    assert invocation["usage"]["usage_source"] == "deepseek_v3_tokenizer"


def test_generate_structured_does_not_retry_read_timeout(monkeypatch, caplog):
    class FakeRunnable:
        def invoke(self, _messages):
            raise TimeoutError("timed out")

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_MAX_RETRIES", 1)
    monkeypatch.setattr(
        "coursepilot.llm.estimate_token_usage",
        lambda _messages, _output: {
            "input_tokens": 9,
            "output_tokens": 0,
            "total_tokens": 9,
            "usage_source": "deepseek_v3_tokenizer",
            "usage_estimated": True,
        },
    )
    caplog.set_level(logging.WARNING, logger="coursepilot.llm")

    with collect_coursepilot_llm_metadata(thread_id="thread-timeout") as collector:
        result = generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=_StructuredOutput,
            payload={"question": "hello"},
            fallback=lambda: _StructuredOutput(answer="fallback"),
        )

    invocation = collector.to_task_metadata()["llm_invocations"][0]

    assert result == _StructuredOutput(answer="fallback")
    assert invocation["attempt_count"] == 1
    assert invocation["fallback_used"] is True
    assert invocation["fallback_reason"] == "timeout"
    assert invocation["error_category"] == "timeout"
    assert invocation["attempts"][0]["usage"]["output_tokens"] == 0
    assert invocation["attempts"][0]["usage"]["usage_estimated"] is True
    assert invocation["attempts"][0]["will_retry"] is False
    assert invocation["attempts"][0]["billing_status"] == "unknown_pending_reconciliation"
    assert "CoursePilot LLM fallback used" in caplog.text


def test_generate_structured_retries_proven_connection_failure(monkeypatch):
    calls = 0

    class FakeRunnable:
        def invoke(self, _messages):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise httpx.ConnectError("connection refused")
            return {
                "raw": _raw_message(),
                "parsed": {"answer": "ok"},
                "parsing_error": None,
            }

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_MAX_RETRIES", 1)

    with collect_coursepilot_llm_metadata(thread_id="thread-connect") as collector:
        result = generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=_StructuredOutput,
            payload={"question": "hello"},
            fallback=lambda: _StructuredOutput(answer="fallback"),
        )

    invocation = collector.to_task_metadata()["llm_invocations"][0]
    assert result == _StructuredOutput(answer="ok")
    assert calls == 2
    assert invocation["attempt_count"] == 2
    assert invocation["attempts"][0]["error_category"] == "connection_error"
    assert invocation["attempts"][0]["billing_status"] == "not_sent"
    assert invocation["attempts"][0]["will_retry"] is True


def test_generate_structured_reuses_successful_response_checkpoint(monkeypatch):
    calls = 0

    class MemoryCheckpoint:
        def __init__(self):
            self.responses = {}
            self.invocations = []

        def load(self, request_sha256):
            return self.responses.get(request_sha256)

        def save(self, request_sha256, payload):
            self.responses[request_sha256] = payload

        def record_invocation(self, invocation):
            self.invocations.append(invocation)

    class FakeRunnable:
        def invoke(self, _messages):
            nonlocal calls
            calls += 1
            return {
                "raw": _raw_message(),
                "parsed": {"answer": "ok"},
                "parsing_error": None,
            }

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    checkpoint = MemoryCheckpoint()
    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr("coursepilot.llm._structured_request_sha256", lambda **_kwargs: "request-1")

    for _ in range(2):
        with collect_coursepilot_llm_metadata(
            thread_id="thread-cache", checkpoint=checkpoint
        ) as collector:
            result = generate_structured(
                prompt_name="lesson/generate_lesson_design",
                output_schema=_StructuredOutput,
                payload={"question": "hello"},
                fallback=lambda: _StructuredOutput(answer="fallback"),
            )
        assert result == _StructuredOutput(answer="ok")

    summary = summarize_llm_invocations(collector.invocations)
    assert calls == 1
    assert checkpoint.invocations[-1]["cache_hit"] is True
    assert summary["provider_request_count"] == 0
    assert summary["cache_hit_count"] == 1


def test_generate_structured_authorizes_paid_request_after_cache_miss(monkeypatch):
    authorizations = []

    class GuardCheckpoint:
        def load(self, _request_sha256):
            return None

        def save(self, _request_sha256, _payload):
            return None

        def record_invocation(self, _invocation):
            return None

        def authorize_request(self, **payload):
            authorizations.append(payload)

    class FakeRunnable:
        def invoke(self, _messages):
            return {
                "raw": _raw_message(),
                "parsed": {"answer": "ok"},
                "parsing_error": None,
            }

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    class FakeGateway:
        def resolve(self, _profile_id):
            return SimpleNamespace(request_parameters={"max_tokens": 4096})

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda *_args: FakeLLM())
    monkeypatch.setattr("coursepilot.llm._configured_model_gateway", lambda: FakeGateway())
    monkeypatch.setattr("coursepilot.llm._structured_request_sha256", lambda **_kwargs: "r1")
    monkeypatch.setattr(
        "coursepilot.llm.estimate_token_usage",
        lambda _messages, _output: {
            "input_tokens": 11,
            "output_tokens": 0,
            "total_tokens": 11,
        },
    )

    with collect_coursepilot_llm_metadata(checkpoint=GuardCheckpoint(), thread_id="budgeted"):
        generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=_StructuredOutput,
            payload={"question": "hello"},
            fallback=lambda: _StructuredOutput(answer="fallback"),
        )

    assert authorizations == [
        {
            "request_sha256": "r1",
            "prompt_name": "lesson/generate_lesson_design",
            "profile_id": "generator_main",
            "estimated_input_tokens": 11,
            "configured_max_output_tokens": 4096,
        }
    ]


@pytest.mark.parametrize(
    ("raw_result", "schema", "fallback", "expected_category"),
    [
        (
            {"raw": None, "parsed": None, "parsing_error": None},
            _StructuredOutput,
            lambda: _StructuredOutput(answer="fallback"),
            "choices_none",
        ),
        (
            {"raw": _raw_message(), "parsed": None, "parsing_error": ValueError("bad json")},
            _StructuredOutput,
            lambda: _StructuredOutput(answer="fallback"),
            "structured_parse_error",
        ),
        (
            {"raw": _raw_message(), "parsed": {"answer": "not-int"}, "parsing_error": None},
            _NumericOutput,
            lambda: _NumericOutput(answer=0),
            "pydantic_validation_error",
        ),
        (
            {
                "raw": _raw_message(finish_reason="length"),
                "parsed": {"answer": "ok"},
                "parsing_error": None,
            },
            _StructuredOutput,
            lambda: _StructuredOutput(answer="fallback"),
            "generation_interrupted",
        ),
    ],
)
def test_generate_structured_classifies_fallback_reasons(
    monkeypatch,
    raw_result,
    schema,
    fallback,
    expected_category,
):
    class FakeRunnable:
        def invoke(self, _messages):
            return raw_result

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(
        "coursepilot.llm.estimate_token_usage",
        lambda _messages, _output: {
            "input_tokens": 1,
            "output_tokens": 0,
            "total_tokens": 1,
            "usage_source": "deepseek_v3_tokenizer",
            "usage_estimated": True,
        },
    )

    with collect_coursepilot_llm_metadata(thread_id="thread-category") as collector:
        generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=schema,
            payload={"question": "hello"},
            fallback=fallback,
        )

    invocation = collector.to_task_metadata()["llm_invocations"][0]

    assert invocation["fallback_used"] is True
    assert invocation["fallback_reason"] == expected_category
    assert invocation["attempts"][0]["error_category"] == expected_category


def test_deterministic_mode_still_records_prompt_metadata(monkeypatch):
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_GENERATION_MODE", "deterministic")

    with collect_coursepilot_llm_metadata(thread_id="thread-deterministic") as collector:
        result = generate_structured(
            prompt_name="lesson/generate_lesson_design",
            output_schema=_StructuredOutput,
            payload={"question": "hello"},
            fallback=lambda: _StructuredOutput(answer="fallback"),
        )

    metadata = collector.to_task_metadata()
    invocation = metadata["llm_invocations"][0]

    assert result == _StructuredOutput(answer="fallback")
    assert invocation["fallback_reason"] == "generation_mode_disabled"
    assert invocation["usage"] is None
    assert metadata["prompt_hashes"]["lesson/generate_lesson_design"]["prompt_sha256"]
    assert metadata["llm_usage_summary"]["fallback_count"] == 1


def test_strict_mode_rejects_generation_mode_fallback(monkeypatch):
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_GENERATION_MODE", "deterministic")
    monkeypatch.setattr(
        "coursepilot.llm.settings.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK",
        True,
    )

    def forbidden_fallback():
        raise AssertionError("fallback should not run in strict mode")

    with collect_coursepilot_llm_metadata(thread_id="thread-strict-disabled") as collector:
        with pytest.raises(CoursePilotLLMCallError, match="fallback is disabled"):
            generate_structured(
                prompt_name="lesson/generate_lesson_design",
                output_schema=_StructuredOutput,
                payload={"question": "hello"},
                fallback=forbidden_fallback,
            )

    metadata = collector.to_task_metadata()
    invocation = metadata["llm_invocations"][0]

    assert invocation["status"] == "failed"
    assert invocation["fallback_used"] is False
    assert invocation["error_category"] == "deterministic_fallback_disabled"
    assert metadata["llm_usage_summary"]["fallback_count"] == 0
    assert metadata["llm_usage_summary"]["failed_call_count"] == 1


def test_strict_mode_rejects_retry_exhaustion_fallback(monkeypatch):
    class FakeRunnable:
        def invoke(self, _messages):
            raise TimeoutError("timed out")

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_MAX_RETRIES", 0)
    monkeypatch.setattr(
        "coursepilot.llm.settings.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK",
        True,
    )
    monkeypatch.setattr(
        "coursepilot.llm.estimate_token_usage",
        lambda _messages, _output: {
            "input_tokens": 9,
            "output_tokens": 0,
            "total_tokens": 9,
            "usage_source": "deepseek_v3_tokenizer",
            "usage_estimated": True,
        },
    )

    def forbidden_fallback():
        raise AssertionError("fallback should not run in strict mode")

    with collect_coursepilot_llm_metadata(thread_id="thread-strict-timeout") as collector:
        with pytest.raises(CoursePilotLLMCallError, match="fallback is disabled"):
            generate_structured(
                prompt_name="lesson/generate_lesson_design",
                output_schema=_StructuredOutput,
                payload={"question": "hello"},
                fallback=forbidden_fallback,
            )

    metadata = collector.to_task_metadata()
    invocation = metadata["llm_invocations"][0]

    assert invocation["status"] == "failed"
    assert invocation["attempt_count"] == 1
    assert invocation["fallback_used"] is False
    assert invocation["error_category"] == "timeout"
    assert invocation["attempts"][0]["error_category"] == "timeout"
    assert metadata["llm_usage_summary"]["fallback_count"] == 0
    assert metadata["llm_usage_summary"]["failed_call_count"] == 1


def test_tokenizer_missing_marks_usage_unavailable(monkeypatch, tmp_path, caplog):
    get_deepseek_tokenizer.cache_clear()
    monkeypatch.setattr(
        "coursepilot.token_usage.settings.COURSEPILOT_TOKENIZER_PATH",
        str(tmp_path / "missing-tokenizer.json"),
    )
    caplog.set_level(logging.WARNING, logger="coursepilot.token_usage")

    try:
        usage = estimate_token_usage([HumanMessage(content="hello")], "world")
    finally:
        get_deepseek_tokenizer.cache_clear()

    assert usage["usage_source"] == "unavailable"
    assert usage["input_tokens"] is None
    assert "tokenizer file not found" in caplog.text


def test_extract_token_usage_prefers_provider_metadata():
    usage = extract_token_usage(_raw_message())

    assert usage == {
        "input_tokens": 3,
        "output_tokens": 2,
        "total_tokens": 5,
        "usage_source": "provider",
        "usage_estimated": False,
    }


def test_summarize_llm_invocations_counts_provider_and_estimated_usage():
    summary = summarize_llm_invocations(
        [
            {
                "prompt_name": "a",
                "fallback_used": False,
                "latency_ms": 10,
                "attempts": [],
                "usage": {
                    "input_tokens": 3,
                    "output_tokens": 2,
                    "total_tokens": 5,
                    "usage_source": "provider",
                    "usage_estimated": False,
                },
            },
            {
                "prompt_name": "a",
                "fallback_used": True,
                "latency_ms": 20,
                "attempts": [{"status": "failed"}],
                "usage": {
                    "input_tokens": 7,
                    "output_tokens": 0,
                    "total_tokens": 7,
                    "usage_source": "deepseek_v3_tokenizer",
                    "usage_estimated": True,
                },
            },
            {
                "prompt_name": "b",
                "fallback_used": True,
                "latency_ms": 5,
                "attempts": [],
                "usage": {
                    "input_tokens": None,
                    "output_tokens": None,
                    "total_tokens": None,
                    "usage_source": "unavailable",
                    "usage_estimated": True,
                },
            },
        ]
    )

    assert summary["call_count"] == 3
    assert summary["failed_attempt_count"] == 1
    assert summary["fallback_count"] == 2
    assert summary["total_tokens"] == 12
    assert summary["usage_source_counts"] == {
        "provider": 1,
        "deepseek_v3_tokenizer": 1,
        "unavailable": 1,
    }


def test_llm_health_check_config_mode_is_zero_network(monkeypatch):
    _set_llm_health_config(monkeypatch, "config")
    monkeypatch.setattr(
        "coursepilot.llm.httpx.get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("called http")),
    )
    monkeypatch.setattr(
        "coursepilot.llm.get_coursepilot_llm",
        lambda: (_ for _ in ()).throw(AssertionError("called chat")),
    )

    check_coursepilot_llm_health()


def test_llm_health_check_http_mode_calls_models(monkeypatch):
    _set_llm_health_config(monkeypatch, "http")
    calls = []

    def fake_get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return httpx.Response(200)

    monkeypatch.setattr("coursepilot.llm.httpx.get", fake_get)

    check_coursepilot_llm_health()

    assert calls == [
        (
            "https://example.test/v1/models",
            {"Authorization": "Bearer test-key"},
            5.0,
        )
    ]


def test_llm_health_check_http_mode_fails_for_unauthorized(monkeypatch):
    _set_llm_health_config(monkeypatch, "http")
    monkeypatch.setattr(
        "coursepilot.llm.httpx.get",
        lambda *_args, **_kwargs: httpx.Response(401),
    )

    with pytest.raises(RuntimeError, match="status=401"):
        check_coursepilot_llm_health()


def test_llm_health_check_http_mode_allows_unsupported_models_endpoint(
    monkeypatch,
    caplog,
):
    _set_llm_health_config(monkeypatch, "http")
    monkeypatch.setattr(
        "coursepilot.llm.httpx.get",
        lambda *_args, **_kwargs: httpx.Response(404),
    )
    caplog.set_level(logging.WARNING, logger="coursepilot.llm")

    check_coursepilot_llm_health()

    assert "health endpoint unsupported" in caplog.text


def test_llm_health_check_chat_mode_uses_structured_output(monkeypatch):
    _set_llm_health_config(monkeypatch, "chat")
    called = {}

    class FakeRunnable:
        def invoke(self, _messages):
            called["invoke"] = True
            return {
                "raw": AIMessage(
                    content='{"ok": true, "message": "正常"}',
                    response_metadata={
                        "finish_reason": "stop",
                        "token_usage": {
                            "prompt_tokens": 1,
                            "completion_tokens": 1,
                            "total_tokens": 2,
                        },
                    },
                ),
                "parsed": {"ok": True, "message": "正常"},
                "parsing_error": None,
            }

    class FakeLLM:
        def with_structured_output(self, _schema, **kwargs):
            called["kwargs"] = kwargs
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())

    check_coursepilot_llm_health()

    assert called["kwargs"] == {"method": "json_mode", "include_raw": True}
    assert called["invoke"] is True
