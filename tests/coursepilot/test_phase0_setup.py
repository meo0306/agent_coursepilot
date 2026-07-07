from pathlib import Path

from core.settings import Settings
from coursepilot.db.base import Base
from coursepilot.db.session import _build_postgres_url


def test_coursepilot_package_skeleton_exists():
    root = Path("src/coursepilot")
    expected_dirs = [
        "api",
        "db",
        "models",
        "schemas",
        "services",
        "rag/parsers",
        "validators",
        "exporters",
        "evals",
        "ui",
        "utils",
        "prompts/lesson",
        "prompts/exam",
        "prompts/ppt",
        "prompts/repair",
    ]

    for relative_path in expected_dirs:
        assert (root / relative_path).is_dir()


def test_coursepilot_agent_skeleton_exists():
    root = Path("src/agents/coursepilot")
    expected_dirs = ["graphs", "nodes", "states"]

    for relative_path in expected_dirs:
        assert (root / relative_path).is_dir()


def test_coursepilot_settings_defaults():
    settings = Settings(OPENAI_API_KEY="test-key", _env_file=None)

    assert settings.COURSEPILOT_STORAGE_DIR == "./storage"
    assert settings.COURSEPILOT_CHROMA_DIR == "./chroma_db"
    assert settings.COURSEPILOT_MAX_REPAIR_ROUNDS == 2
    assert settings.COURSEPILOT_DUPLICATE_THRESHOLD == 0.85
    assert settings.COURSEPILOT_ENABLED is True
    assert settings.COURSEPILOT_GENERATION_MODE == "auto"
    assert settings.COURSEPILOT_LLM_HEALTH_CHECK_MODE == "http"
    assert settings.COURSEPILOT_LLM_HEALTH_CHECK_TIMEOUT_SECONDS == 5.0
    assert settings.COURSEPILOT_TOKENIZER_PATH.endswith("tokenizer.json")
    assert settings.COURSEPILOT_EMBEDDING_PROVIDER == "auto"


def test_coursepilot_db_base_uses_prefixed_metadata():
    assert Base.metadata.naming_convention["pk"] == "pk_%(table_name)s"
    assert {"coursepilot_courses", "coursepilot_documents", "coursepilot_chunks"}.issubset(
        Base.metadata.tables
    )


def test_coursepilot_database_url_override(monkeypatch):
    monkeypatch.setattr(
        "coursepilot.db.session.settings.COURSEPILOT_DATABASE_URL",
        "postgresql+psycopg://user:pass@localhost:5432/coursepilot",
    )

    assert _build_postgres_url() == "postgresql+psycopg://user:pass@localhost:5432/coursepilot"
