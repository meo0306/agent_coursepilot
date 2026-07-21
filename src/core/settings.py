from enum import StrEnum
from typing import Annotated, Any

from dotenv import find_dotenv
from pydantic import BeforeValidator, Field, HttpUrl, SecretStr, TypeAdapter, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

from schema.models import (
    AllModelEnum,
    DeepseekModelName,
    FakeModelName,
    OpenAICompatibleName,
    OpenAIModelName,
    Provider,
)


class DatabaseType(StrEnum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_logging_level(self) -> int:
        import logging

        mapping = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.CRITICAL: logging.CRITICAL,
        }
        return mapping[self]


def check_str_is_http(x: str) -> str:
    http_url_adapter = TypeAdapter(HttpUrl)
    return str(http_url_adapter.validate_python(x))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=find_dotenv(),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        validate_default=False,
    )

    MODE: str | None = None
    HOST: str = "0.0.0.0"
    PORT: int = 8080
    GRACEFUL_SHUTDOWN_TIMEOUT: int = 30
    LOG_LEVEL: LogLevel = LogLevel.WARNING
    AUTH_SECRET: SecretStr | None = None

    OPENAI_API_KEY: SecretStr | None = None
    DEEPSEEK_API_KEY: SecretStr | None = None
    USE_FAKE_MODEL: bool = False

    COMPATIBLE_MODEL: str | None = None
    COMPATIBLE_API_KEY: SecretStr | None = None
    COMPATIBLE_BASE_URL: Annotated[str, BeforeValidator(check_str_is_http)] | None = None

    DEFAULT_MODEL: AllModelEnum | None = None
    AVAILABLE_MODELS: set[AllModelEnum] = Field(default_factory=set)

    DATABASE_TYPE: DatabaseType = DatabaseType.SQLITE
    SQLITE_DB_PATH: str = "checkpoints.db"

    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: SecretStr | None = None
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_APPLICATION_NAME: str = "coursepilot"
    POSTGRES_MIN_CONNECTIONS_PER_POOL: int = 1
    POSTGRES_MAX_CONNECTIONS_PER_POOL: int = 1

    COURSEPILOT_DATABASE_URL: str | None = None
    COURSEPILOT_STORAGE_DIR: str = "./storage"
    COURSEPILOT_CHROMA_DIR: str = "./chroma_db"
    COURSEPILOT_MAX_REPAIR_ROUNDS: int = 2
    COURSEPILOT_DUPLICATE_THRESHOLD: float = 0.85
    COURSEPILOT_ENABLED: bool = True
    COURSEPILOT_GENERATION_MODE: str = "auto"
    COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK: bool = False
    COURSEPILOT_LLM_TIMEOUT_SECONDS: float = 120.0
    COURSEPILOT_LLM_MAX_RETRIES: int = 2
    COURSEPILOT_LLM_HEALTH_CHECK_MODE: str = "http"
    COURSEPILOT_LLM_HEALTH_CHECK_TIMEOUT_SECONDS: float = 5.0
    COURSEPILOT_TOKENIZER_PATH: str = "deepseek_v3_tokenizer/deepseek_v3_tokenizer/tokenizer.json"
    COURSEPILOT_EMBEDDING_PROVIDER: str = "auto"
    COURSEPILOT_EMBEDDING_MODEL: str | None = None
    COURSEPILOT_EMBEDDING_BASE_URL: Annotated[str, BeforeValidator(check_str_is_http)] | None = None
    COURSEPILOT_EMBEDDING_API_KEY: SecretStr | None = None
    COURSEPILOT_EMBEDDING_MAX_RETRIES: int = Field(default=4, ge=0)
    COURSEPILOT_EMBEDDING_RETRY_BASE_SECONDS: float = Field(default=15.0, ge=0)
    COURSEPILOT_EMBEDDING_RETRY_MAX_SECONDS: float = Field(default=120.0, ge=0)
    COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE: str = "auto"
    COURSEPILOT_IDEMPOTENCY_LEASE_SECONDS: int = 14400
    COURSEPILOT_ASYNC_WORKER_ENABLED: bool = True
    COURSEPILOT_ASYNC_WORKER_POLL_SECONDS: float = 1.0
    COURSEPILOT_ASYNC_TASK_LEASE_SECONDS: int = 300
    COURSEPILOT_ASYNC_WORKER_SHUTDOWN_TIMEOUT_SECONDS: int = 10

    def __init__(self, **values: Any) -> None:
        if values.get("_env_file") is None and "_env_file" in values:
            values["_env_file"] = ""
        super().__init__(**values)

    def model_post_init(self, __context: Any) -> None:
        active_providers = []
        if self.OPENAI_API_KEY:
            active_providers.append(Provider.OPENAI)
        if self.COMPATIBLE_BASE_URL and self.COMPATIBLE_MODEL:
            active_providers.append(Provider.OPENAI_COMPATIBLE)
        if self.DEEPSEEK_API_KEY:
            active_providers.append(Provider.DEEPSEEK)
        if self.USE_FAKE_MODEL:
            active_providers.append(Provider.FAKE)

        if not active_providers:
            active_providers.append(Provider.FAKE)

        for provider in active_providers:
            match provider:
                case Provider.OPENAI:
                    if self.DEFAULT_MODEL is None:
                        self.DEFAULT_MODEL = OpenAIModelName.GPT_5_NANO
                    self.AVAILABLE_MODELS.update(set(OpenAIModelName))
                case Provider.OPENAI_COMPATIBLE:
                    if self.DEFAULT_MODEL is None:
                        self.DEFAULT_MODEL = OpenAICompatibleName.OPENAI_COMPATIBLE
                    self.AVAILABLE_MODELS.update(set(OpenAICompatibleName))
                case Provider.DEEPSEEK:
                    if self.DEFAULT_MODEL is None:
                        self.DEFAULT_MODEL = DeepseekModelName.DEEPSEEK_CHAT
                    self.AVAILABLE_MODELS.update(set(DeepseekModelName))
                case Provider.FAKE:
                    if self.DEFAULT_MODEL is None:
                        self.DEFAULT_MODEL = FakeModelName.FAKE
                    self.AVAILABLE_MODELS.update(set(FakeModelName))
                case _:
                    raise ValueError(f"Unsupported provider: {provider}")

    @computed_field  # type: ignore[prop-decorator]
    @property
    def BASE_URL(self) -> str:
        return f"http://{self.HOST}:{self.PORT}"

    def is_dev(self) -> bool:
        return self.MODE == "dev"


settings = Settings()
