from enum import StrEnum
from typing import Annotated, Any, Literal

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
    COURSERAG_ARTIFACT_DIR: str = "./storage/courserag/artifacts"
    COURSERAG_ARTIFACT_RETENTION_HOURS: int = Field(default=168, ge=1)
    COURSERAG_STAGING_RETENTION_HOURS: int = Field(default=72, ge=1)
    COURSERAG_RENDERER_PROFILE_PATH: str = (
        "resources/renderers/libreoffice_headless_v1/profile.json"
    )
    COURSERAG_LIBREOFFICE_PATH: str = "soffice"
    COURSERAG_RENDER_TIMEOUT_SECONDS: int = Field(default=300, ge=1, le=1800)
    COURSERAG_MAX_DOCUMENT_BYTES: int = Field(default=100 * 1024 * 1024, ge=1)
    COURSERAG_MAX_PDF_PAGES: int = Field(default=2000, ge=1)
    COURSERAG_OCR_PROVIDER: Literal["disabled", "rapidocr", "tesseract", "paddleocr"] = "rapidocr"
    COURSERAG_OCR_PROFILE_PATH: str | None = "resources/ocr_profiles/default_v1.json"
    COURSERAG_OCR_DPI: int = Field(default=200, ge=72, le=600)
    COURSERAG_OCR_MIN_NATIVE_CHARS: int = Field(default=30, ge=0)
    COURSERAG_OCR_MIN_PRINTABLE_RATIO: float = Field(default=0.80, ge=0, le=1)
    COURSERAG_OCR_MAX_GARBLED_RATIO: float = Field(default=0.20, ge=0, le=1)
    COURSERAG_OCR_HYBRID_MIN_IMAGE_AREA_RATIO: float = Field(default=0.50, ge=0, le=1)
    COURSERAG_OCR_HYBRID_MAX_NATIVE_TEXT_AREA_RATIO: float = Field(default=0.35, ge=0, le=1)
    COURSERAG_OCR_MAX_PIXELS: int = Field(default=20_000_000, ge=1)
    COURSERAG_OCR_TIMEOUT_SECONDS: float = Field(default=90.0, gt=0, le=600)
    COURSERAG_OCR_MAX_MEMORY_BYTES: int = Field(default=1_610_612_736, ge=64 * 1024 * 1024)
    COURSERAG_OCR_MAX_WORKERS: Literal[1] = 1
    COURSERAG_OCR_MIN_CONFIDENCE: float = Field(default=0.75, ge=0, le=1)
    COURSERAG_EVIDENCE_PROFILE_PATH: str = "resources/evidence_profiles/semantic_units_v1.json"
    COURSERAG_CHUNK_PROFILE_PATH: str = "resources/chunk_profiles/parent_child_v1.json"
    COURSERAG_CHUNK_TOKENIZER_PATH: str = (
        "deepseek_v3_tokenizer/deepseek_v3_tokenizer/tokenizer.json"
    )
    COURSERAG_EVIDENCE_BATCH_LIMIT: int = Field(default=100, ge=1, le=1000)
    COURSERAG_SOURCE_PREVIEW_MAX_CHARS: int = Field(default=500, ge=1, le=10000)
    COURSERAG_KP_PROVIDER: Literal["disabled", "openai-compatible"] = "disabled"
    COURSERAG_KP_STRUCTURED_OUTPUT_METHOD: Literal["json_mode", "function_calling"] = "json_mode"
    COURSERAG_KP_MODEL: str | None = None
    COURSERAG_KP_BASE_URL: Annotated[str, BeforeValidator(check_str_is_http)] | None = None
    COURSERAG_KP_API_KEY: SecretStr | None = None
    COURSERAG_KP_CONCURRENCY: int = Field(default=4, ge=1, le=32)
    COURSERAG_KP_MAX_RETRIES: int = Field(default=3, ge=0, le=10)
    COURSERAG_KP_RETRY_BASE_SECONDS: float = Field(default=1.0, ge=0, le=60)
    COURSERAG_KP_RETRY_MAX_SECONDS: float = Field(default=30.0, ge=0, le=600)
    COURSERAG_KP_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0, le=1800)
    COURSERAG_KP_WINDOW_MIN_TOKENS: int = Field(default=1500, ge=1)
    COURSERAG_KP_WINDOW_MAX_TOKENS: int = Field(default=3000, ge=1)
    COURSERAG_KP_PUBLISH_THRESHOLD: float = Field(default=0.75, ge=0, le=1)
    COURSERAG_KP_PROFILE_PATH: str = "resources/knowledge_point_profiles/default_v1.json"
    COURSERAG_RETRIEVAL_BACKEND: Literal["legacy", "versioned"] = "legacy"
    COURSERAG_RETRIEVAL_PROFILE_PATH: str = "resources/retrieval_profiles/default_v1.json"
    COURSERAG_EMBEDDING_PROVIDER: Literal[
        "disabled", "openai-compatible", "local_sentence_transformers"
    ] = "disabled"
    COURSERAG_EMBEDDING_MODEL: str | None = None
    COURSERAG_EMBEDDING_BASE_URL: Annotated[str, BeforeValidator(check_str_is_http)] | None = None
    COURSERAG_EMBEDDING_API_KEY: SecretStr | None = None
    COURSERAG_EMBEDDING_MODEL_PATH: str | None = None
    COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256: str | None = None
    COURSERAG_EMBEDDING_WEIGHTS_SHA256: str | None = None
    COURSERAG_EMBEDDING_DEVICE: Literal["cuda", "cpu"] = "cuda"
    COURSERAG_EMBEDDING_DTYPE: Literal["bfloat16", "float16", "float32"] = "bfloat16"
    COURSERAG_EMBEDDING_MAX_LENGTH: int = Field(default=2048, ge=32, le=32768)
    COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE: int = Field(default=8, ge=1, le=128)
    COURSERAG_EMBEDDING_QUERY_PROMPT_NAME: str = "query"
    COURSERAG_EMBEDDING_BATCH_SIZE: int = Field(default=64, ge=1, le=512)
    COURSERAG_EMBEDDING_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=600)
    COURSERAG_EMBEDDING_EVAL_MAX_TOKENS: int = Field(default=500_000, ge=1)
    COURSERAG_SPARSE_PROFILE_PATH: str = "resources/retrieval_profiles/bm25_v1.json"
    COURSERAG_RRF_K: int = Field(default=60, ge=1)
    COURSERAG_RETRIEVAL_CANDIDATE_K: int = Field(default=30, ge=1, le=500)
    COURSERAG_RETRIEVAL_TOP_N: int = Field(default=8, ge=1, le=100)
    COURSERAG_RERANKER_PROVIDER: Literal[
        "disabled", "jina", "cohere", "voyage", "local_cross_encoder"
    ] = "disabled"
    COURSERAG_RERANKER_MODEL: str | None = None
    COURSERAG_RERANKER_ENDPOINT: Annotated[str, BeforeValidator(check_str_is_http)] | None = None
    COURSERAG_RERANKER_API_KEY: SecretStr | None = None
    COURSERAG_RERANKER_MAX_DOCUMENT_TOKENS: int = Field(default=1200, ge=1)
    COURSERAG_RERANKER_TIMEOUT_SECONDS: float = Field(default=30.0, gt=0, le=600)
    COURSERAG_RERANKER_MAX_RETRIES: int = Field(default=2, ge=0, le=10)
    COURSERAG_RERANKER_EVAL_FAILURE_POLICY: Literal["fail_sample"] = "fail_sample"
    COURSERAG_RERANKER_PRODUCTION_FAILURE_POLICY: Literal["fail_sample", "fusion_order"] = (
        "fusion_order"
    )
    COURSERAG_JINA_MAX_TOKENS: int = Field(default=8_000_000, ge=1)
    COURSERAG_COHERE_MAX_SEARCH_UNITS: int = Field(default=500, ge=1)
    COURSERAG_RERANKER_EVAL_CANDIDATES: str = "jina,cohere"
    COURSERAG_JINA_RERANKER_BASE_URL: Annotated[str, BeforeValidator(check_str_is_http)] | None = (
        None
    )
    COURSERAG_JINA_RERANKER_MODEL: str | None = None
    COURSERAG_JINA_RERANKER_API_KEY: SecretStr | None = None
    COURSERAG_COHERE_RERANKER_BASE_URL: (
        Annotated[str, BeforeValidator(check_str_is_http)] | None
    ) = None
    COURSERAG_COHERE_RERANKER_MODEL: str | None = None
    COURSERAG_COHERE_RERANKER_API_KEY: SecretStr | None = None
    COURSERAG_RERANKER_CANDIDATE_K: int = Field(default=30, ge=1, le=500)
    COURSERAG_RERANKER_TOP_N: int = Field(default=8, ge=1, le=100)
    COURSERAG_RERANKER_MAX_DOC_TOKENS: int = Field(default=1200, ge=1)
    COURSERAG_RERANKER_TRUNCATION: bool = True
    COURSERAG_RERANKER_EVAL_FALLBACK_POLICY: Literal["fail_sample"] = "fail_sample"
    COURSERAG_RERANKER_PRODUCTION_FALLBACK_POLICY: Literal["fail_sample", "fusion_order"] = (
        "fusion_order"
    )
    COURSERAG_JINA_RERANKER_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=16)
    COURSERAG_COHERE_RERANKER_MAX_CONCURRENCY: int = Field(default=1, ge=1, le=16)
    COURSERAG_COHERE_RERANKER_MAX_RPM: int = Field(default=10, ge=1)
    COURSERAG_QUERY_PROFILE_PATH: str = "resources/query_profiles/b7_candidate_v1.json"
    COURSERAG_QUERY_PROVIDER: Literal["disabled", "openai-compatible"] = "disabled"
    COURSERAG_QUERY_MULTI_REWRITE: Literal["disabled", "route_based"] = "route_based"
    COURSERAG_QUERY_MAX_REWRITES: int = Field(default=3, ge=0, le=3)
    COURSERAG_QUERY_LOW_RECALL_RETRY: bool = True
    COURSERAG_QUERY_MAX_RETRIES: Literal[1] = 1
    COURSERAG_CONTEXT_PROFILE_PATH: str = "resources/context_profiles/b8_qa_v1.json"
    COURSERAG_CONTEXT_TOKENIZER_PATH: str = (
        "deepseek_v3_tokenizer/deepseek_v3_tokenizer/tokenizer.json"
    )
    COURSERAG_CONTEXT_MAX_ITEMS: int = Field(default=8, ge=1, le=100)
    COURSERAG_CONTEXT_MAX_TOKENS: int = Field(default=4000, ge=1, le=32768)
    COURSERAG_QA_PROVIDER: Literal["disabled", "openai-compatible"] = "disabled"
    COURSERAG_QA_MODEL: str | None = None
    COURSERAG_QA_BASE_URL: Annotated[str, BeforeValidator(check_str_is_http)] | None = None
    COURSERAG_QA_API_KEY: SecretStr | None = None
    COURSERAG_QA_CAPABILITY_PROFILE: str = "deepseek_v4"
    COURSERAG_QA_STRUCTURED_OUTPUT_METHOD: Literal["json_mode"] = "json_mode"
    COURSERAG_QA_THINKING_MODE: Literal["disabled"] = "disabled"
    COURSERAG_QA_TEMPERATURE: Literal[0] = 0
    COURSERAG_QA_MAX_OUTPUT_TOKENS: int = Field(default=600, ge=1, le=4096)
    COURSERAG_QA_LIST_MAX_OUTPUT_TOKENS: int = Field(default=3200, ge=1, le=8192)
    COURSERAG_QA_TIMEOUT_SECONDS: float = Field(default=120.0, gt=0, le=600)
    COURSERAG_QA_MAX_RETRIES: int = Field(default=2, ge=0, le=10)
    COURSERAG_QA_MAX_REPAIR_ATTEMPTS: Literal[1] = 1
    COURSERAG_QA_EVAL_MAX_TOTAL_TOKENS: int = Field(default=2_500_000, ge=1)
    COURSERAG_P09_COHERE_MAX_SEARCH_UNITS: int = Field(default=180, ge=1)
    COURSERAG_INCREMENTAL_ENABLED: bool = True
    COURSERAG_INCREMENTAL_PROFILE_PATH: str = "resources/incremental_profiles/default_v1.json"
    COURSERAG_CITATION_MIGRATION_PROFILE_PATH: str = "resources/migration_profiles/default_v1.json"
    COURSERAG_CITATION_AUTO_SIMILARITY: float = Field(default=0.92, ge=0, le=1)
    COURSERAG_CITATION_REVIEW_SIMILARITY: float = Field(default=0.75, ge=0, le=1)
    COURSERAG_CITATION_MIN_MARGIN: float = Field(default=0.08, ge=0, le=1)
    COURSERAG_VERIFIED_WRITEBACK_ENABLED: bool = True
    COURSERAG_VERIFIED_OVERLAY_ENABLED: bool = True
    COURSERAG_ENRICHMENT_RECORD_THRESHOLD: int = Field(default=10, ge=1)
    COURSERAG_ENRICHMENT_TOKEN_THRESHOLD: int = Field(default=3000, ge=1)
    COURSERAG_ENRICHMENT_MAX_AGE_SECONDS: int = Field(default=86400, ge=1)
    COURSERAG_ACL_ENFORCEMENT: Literal["required"] = "required"
    COURSERAG_TRUSTED_IDENTITY_HEADERS: Literal[True] = True
    COURSERAG_MAX_DOCX_ENTRIES: int = Field(default=20_000, ge=1)
    COURSERAG_MAX_DOCX_UNCOMPRESSED_BYTES: int = Field(default=512 * 1024 * 1024, ge=1)
    COURSERAG_MAX_DOCX_COMPRESSION_RATIO: float = Field(default=200, gt=1)
    COURSERAG_MAX_OCR_DPI: int = Field(default=600, ge=72, le=1200)
    COURSERAG_PARSE_TIMEOUT_SECONDS: int = Field(default=300, ge=1, le=3600)
    COURSERAG_P10_DEV_MAX_DEEPSEEK_TOKENS: int = Field(default=180_000, ge=1)
    COURSERAG_P10_DEV_MAX_COHERE_SEARCH_UNITS: Literal[0] = 0

    def __init__(self, **values: Any) -> None:
        if values.get("_env_file") is None and "_env_file" in values:
            values["_env_file"] = ""
        super().__init__(**values)

    def model_post_init(self, __context: Any) -> None:
        if self.COURSERAG_OCR_PROVIDER != "disabled" and not self.COURSERAG_OCR_PROFILE_PATH:
            raise ValueError("COURSERAG_OCR_PROFILE_PATH is required when OCR is enabled")
        if self.COURSERAG_KP_WINDOW_MIN_TOKENS > self.COURSERAG_KP_WINDOW_MAX_TOKENS:
            raise ValueError("COURSERAG_KP Window minimum cannot exceed maximum")
        if self.COURSERAG_KP_RETRY_BASE_SECONDS > self.COURSERAG_KP_RETRY_MAX_SECONDS:
            raise ValueError("COURSERAG_KP retry base cannot exceed retry maximum")
        if self.COURSERAG_CITATION_REVIEW_SIMILARITY > self.COURSERAG_CITATION_AUTO_SIMILARITY:
            raise ValueError("Citation review threshold cannot exceed auto-migration threshold")
        if self.COURSERAG_RETRIEVAL_TOP_N > self.COURSERAG_RETRIEVAL_CANDIDATE_K:
            raise ValueError("CourseRAG retrieval Top-N cannot exceed Candidate-K")
        if self.COURSERAG_RERANKER_TOP_N > self.COURSERAG_RERANKER_CANDIDATE_K:
            raise ValueError("CourseRAG Reranker Top-N cannot exceed Candidate-K")
        if self.COURSERAG_RETRIEVAL_BACKEND == "versioned":
            if (
                self.COURSERAG_EMBEDDING_PROVIDER == "disabled"
                or not self.COURSERAG_EMBEDDING_MODEL
            ):
                raise ValueError("Versioned retrieval requires an explicit Embedding Provider")
            if self.COURSERAG_EMBEDDING_PROVIDER == "openai-compatible" and (
                not self.COURSERAG_EMBEDDING_BASE_URL or not self.COURSERAG_EMBEDDING_API_KEY
            ):
                raise ValueError("OpenAI-compatible Embedding requires endpoint and API key")
            if self.COURSERAG_EMBEDDING_PROVIDER == "local_sentence_transformers" and (
                not self.COURSERAG_EMBEDDING_MODEL_PATH
                or not self.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256
                or not self.COURSERAG_EMBEDDING_WEIGHTS_SHA256
            ):
                raise ValueError("Local Embedding requires path and frozen model Hashes")
        if self.COURSERAG_RERANKER_PROVIDER in {"jina", "cohere", "voyage"} and (
            not self.COURSERAG_RERANKER_MODEL
            or not self.COURSERAG_RERANKER_ENDPOINT
            or not self.COURSERAG_RERANKER_API_KEY
        ):
            raise ValueError("Enabled remote Reranker requires model, endpoint, and API key")
        if self.COURSERAG_QA_PROVIDER == "openai-compatible" and not (
            (self.COURSERAG_QA_MODEL or self.COMPATIBLE_MODEL)
            and (self.COURSERAG_QA_BASE_URL or self.COMPATIBLE_BASE_URL)
            and (self.COURSERAG_QA_API_KEY or self.COMPATIBLE_API_KEY)
        ):
            raise ValueError("Enabled CourseRAG QA requires model, endpoint, and API key")
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
