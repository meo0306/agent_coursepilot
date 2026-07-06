import logging

import pytest
from langchain_core.messages import AIMessage
from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, SecretStr

from coursepilot.llm import (
    build_coursepilot_system_prompt,
    collect_coursepilot_llm_metadata,
    generate_structured,
    get_coursepilot_llm,
    hash_prompt,
)
from coursepilot.prompts.loader import load_prompt
from coursepilot.rag.embeddings import HashingEmbeddings, get_coursepilot_embeddings


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

    assert isinstance(embeddings, OpenAIEmbeddings)
    assert embeddings.model == "text-embedding-test"


def test_coursepilot_llm_enables_deepseek_thinking(monkeypatch):
    get_coursepilot_llm.cache_clear()
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
        assert llm.request_timeout == 12.5
        assert llm.max_retries == 0
    finally:
        get_coursepilot_llm.cache_clear()


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
    assert invocation["usage"] == {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
    assert metadata["prompt_hashes"]["lesson/generate_lesson_design"]["prompt_sha256"]
    assert metadata["llm_usage_summary"]["total_tokens"] == 5


def test_generate_structured_logs_retry_exhaustion_and_fallback(monkeypatch, caplog):
    class FakeRunnable:
        def invoke(self, _messages):
            raise TimeoutError("timed out")

    class FakeLLM:
        def with_structured_output(self, _schema, **_kwargs):
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())
    monkeypatch.setattr("coursepilot.llm.settings.COURSEPILOT_LLM_MAX_RETRIES", 1)
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
    assert invocation["attempt_count"] == 2
    assert invocation["fallback_used"] is True
    assert invocation["fallback_reason"] == "timeout"
    assert invocation["error_category"] == "timeout"
    assert "CoursePilot LLM fallback used" in caplog.text


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
    assert metadata["prompt_hashes"]["lesson/generate_lesson_design"]["prompt_sha256"]
    assert metadata["llm_usage_summary"]["fallback_count"] == 1
