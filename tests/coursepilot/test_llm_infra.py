from pydantic import SecretStr
from langchain_openai import OpenAIEmbeddings

from coursepilot.prompts.loader import load_prompt
from coursepilot.rag.embeddings import HashingEmbeddings, get_coursepilot_embeddings


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
