from langchain_openai import OpenAIEmbeddings
from pydantic import BaseModel, SecretStr

from coursepilot.llm import generate_structured, get_coursepilot_llm
from coursepilot.prompts.loader import load_prompt
from coursepilot.rag.embeddings import HashingEmbeddings, get_coursepilot_embeddings


class _StructuredOutput(BaseModel):
    answer: str


def test_prompt_loader_reads_lesson_prompt():
    prompt = load_prompt("lesson/generate_lesson_design")

    assert "LessonDesignContent" in prompt


def test_embedding_factory_defaults_to_hashing(monkeypatch):
    monkeypatch.setattr("coursepilot.rag.embeddings.settings.COURSEPILOT_EMBEDDING_PROVIDER", "auto")
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

    try:
        llm = get_coursepilot_llm()

        assert llm.model_name == "deepseek-v4-pro"
        assert llm.streaming is False
        assert llm.reasoning_effort == "high"
        assert llm.extra_body == {"thinking": {"type": "enabled"}}
    finally:
        get_coursepilot_llm.cache_clear()


def test_generate_structured_uses_json_mode(monkeypatch):
    captured = {}

    class FakeRunnable:
        def invoke(self, messages):
            captured["messages"] = messages
            return {"answer": "ok"}

    class FakeLLM:
        def with_structured_output(self, schema, **kwargs):
            captured["schema"] = schema
            captured["kwargs"] = kwargs
            return FakeRunnable()

    monkeypatch.setattr("coursepilot.llm.use_coursepilot_llm", lambda: True)
    monkeypatch.setattr("coursepilot.llm.get_coursepilot_llm", lambda: FakeLLM())

    result = generate_structured(
        prompt_name="lesson/generate_lesson_design",
        output_schema=_StructuredOutput,
        payload={"question": "hello"},
        fallback=lambda: _StructuredOutput(answer="fallback"),
    )

    assert result == _StructuredOutput(answer="ok")
    assert captured["schema"] is _StructuredOutput
    assert captured["kwargs"] == {"method": "json_mode"}
