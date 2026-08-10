import logging
import os
from unittest.mock import patch

import pytest
from pydantic import SecretStr, ValidationError

from core.settings import LogLevel, Settings, check_str_is_http
from schema.models import DeepseekModelName, FakeModelName, OpenAICompatibleName, OpenAIModelName


def test_check_str_is_http():
    assert check_str_is_http("http://example.com/") == "http://example.com/"
    assert check_str_is_http("https://api.test.com/") == "https://api.test.com/"

    with pytest.raises(ValidationError):
        check_str_is_http("not_a_url")
    with pytest.raises(ValidationError):
        check_str_is_http("ftp://invalid.com")


def test_settings_default_values():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.HOST == "0.0.0.0"
    assert settings.PORT == 8080
    assert settings.USE_FAKE_MODEL is False
    assert settings.DEFAULT_MODEL == FakeModelName.FAKE
    assert settings.AVAILABLE_MODELS == set(FakeModelName)
    assert settings.COURSERAG_OCR_PROVIDER == "rapidocr"
    assert settings.COURSERAG_OCR_PROFILE_PATH == "resources/ocr_profiles/default_v1.json"
    assert settings.COURSERAG_RETRIEVAL_PROFILE_PATH == (
        "resources/retrieval_profiles/default_v1.json"
    )
    assert settings.COURSERAG_OCR_TIMEOUT_SECONDS == 90


def test_settings_with_openai_key():
    with patch.dict(os.environ, {"OPENAI_API_KEY": "test_key"}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.OPENAI_API_KEY == SecretStr("test_key")
    assert settings.DEFAULT_MODEL == OpenAIModelName.GPT_5_NANO
    assert settings.AVAILABLE_MODELS == set(OpenAIModelName)


def test_settings_with_openai_compatible_model():
    with patch.dict(
        os.environ,
        {
            "COMPATIBLE_MODEL": "deepseek-test",
            "COMPATIBLE_BASE_URL": "https://example.test/v1",
            "COMPATIBLE_API_KEY": "test-key",
        },
        clear=True,
    ):
        settings = Settings(_env_file=None)

    assert settings.COMPATIBLE_API_KEY == SecretStr("test-key")
    assert settings.DEFAULT_MODEL == OpenAICompatibleName.OPENAI_COMPATIBLE
    assert settings.AVAILABLE_MODELS == set(OpenAICompatibleName)


def test_settings_with_deepseek_key():
    with patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test_key"}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.DEEPSEEK_API_KEY == SecretStr("test_key")
    assert settings.DEFAULT_MODEL == DeepseekModelName.DEEPSEEK_CHAT
    assert settings.AVAILABLE_MODELS == set(DeepseekModelName)


def test_settings_with_multiple_supported_providers():
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test_openai_key",
            "DEEPSEEK_API_KEY": "test_deepseek_key",
        },
        clear=True,
    ):
        settings = Settings(_env_file=None)

    expected_models = set(OpenAIModelName)
    expected_models.update(set(DeepseekModelName))
    assert settings.DEFAULT_MODEL == OpenAIModelName.GPT_5_NANO
    assert settings.AVAILABLE_MODELS == expected_models


def test_settings_base_url():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(HOST="0.0.0.0", PORT=8000, _env_file=None)

    assert settings.BASE_URL == "http://0.0.0.0:8000"


def test_settings_is_dev():
    with patch.dict(os.environ, {}, clear=True):
        assert Settings(MODE="dev", _env_file=None).is_dev() is True
        assert Settings(MODE="prod", _env_file=None).is_dev() is False


def test_log_level_enum():
    assert LogLevel.DEBUG.to_logging_level() == logging.DEBUG
    assert LogLevel.INFO.to_logging_level() == logging.INFO
    assert LogLevel.WARNING.to_logging_level() == logging.WARNING
    assert LogLevel.ERROR.to_logging_level() == logging.ERROR
    assert LogLevel.CRITICAL.to_logging_level() == logging.CRITICAL


def test_settings_log_level_default():
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.LOG_LEVEL == LogLevel.WARNING
    assert settings.LOG_LEVEL.to_logging_level() == logging.WARNING


def test_settings_log_level_from_env():
    with patch.dict(os.environ, {"LOG_LEVEL": "DEBUG"}, clear=True):
        settings = Settings(_env_file=None)

    assert settings.LOG_LEVEL == LogLevel.DEBUG
    assert settings.LOG_LEVEL.to_logging_level() == logging.DEBUG


def test_settings_log_level_invalid():
    with patch.dict(os.environ, {"LOG_LEVEL": "INVALID"}, clear=True):
        with pytest.raises(ValueError, match="validation error for Settings\nLOG_LEVEL\n"):
            Settings(_env_file=None)


def test_versioned_retrieval_accepts_frozen_local_embedding() -> None:
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(
            COURSERAG_RETRIEVAL_BACKEND="versioned",
            COURSERAG_EMBEDDING_PROVIDER="local_sentence_transformers",
            COURSERAG_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B",
            COURSERAG_EMBEDDING_MODEL_PATH="D:/AI/models/qwen",
            COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256="1" * 64,
            COURSERAG_EMBEDDING_WEIGHTS_SHA256="2" * 64,
            _env_file=None,
        )

    assert settings.COURSERAG_EMBEDDING_DEVICE == "cuda"
    assert settings.COURSERAG_EMBEDDING_DTYPE == "bfloat16"


def test_versioned_retrieval_rejects_unfrozen_local_embedding() -> None:
    with patch.dict(os.environ, {}, clear=True):
        with pytest.raises(
            ValueError, match="Local Embedding requires path and frozen model Hashes"
        ):
            Settings(
                COURSERAG_RETRIEVAL_BACKEND="versioned",
                COURSERAG_EMBEDDING_PROVIDER="local_sentence_transformers",
                COURSERAG_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B",
                COURSERAG_EMBEDDING_MODEL_PATH="D:/AI/models/qwen",
                _env_file=None,
            )
