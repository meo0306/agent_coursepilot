from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated
from uuid import uuid4

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, JsonValue, field_validator

CONTRACT_API_VERSION = "v1"
SERVICE_VERSION = "0.1.0"


def _require_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("datetime values must include a timezone")
    return value.astimezone(UTC)


UTCDateTime = Annotated[datetime, AfterValidator(_require_utc)]


class ContractModel(BaseModel):
    """Strict base model shared by the public CourseRAG contract."""

    model_config = ConfigDict(extra="forbid")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class RequestContext(ContractModel):
    request_id: str = Field(default_factory=lambda: _new_id("req"), min_length=1)
    trace_id: str = Field(default_factory=lambda: _new_id("trace"), min_length=1)
    caller: str = Field(default="coursepilot", min_length=1)
    api_version: str = Field(default=CONTRACT_API_VERSION, min_length=1)
    idempotency_key: str | None = Field(default=None, max_length=255)
    deadline_ms: int | None = Field(default=None, gt=0)

    @field_validator(
        "request_id",
        "trace_id",
        "caller",
        "api_version",
        "idempotency_key",
        mode="before",
    )
    @classmethod
    def _strip_identifiers(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("identifier values cannot be blank")
        return value


class ResponseMeta(ContractModel):
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)
    api_version: str = Field(default=CONTRACT_API_VERSION, min_length=1)
    service_version: str = Field(default=SERVICE_VERSION, min_length=1)
    duration_ms: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def from_context(
        cls,
        context: RequestContext,
        *,
        duration_ms: int = 0,
        warnings: list[str] | None = None,
    ) -> ResponseMeta:
        return cls(
            request_id=context.request_id,
            trace_id=context.trace_id,
            api_version=context.api_version,
            duration_ms=duration_ms,
            warnings=warnings or [],
        )


class ErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    FORBIDDEN = "FORBIDDEN"
    INDEX_NOT_READY = "INDEX_NOT_READY"
    PROVIDER_RATE_LIMITED = "PROVIDER_RATE_LIMITED"
    DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    FEATURE_NOT_AVAILABLE = "FEATURE_NOT_AVAILABLE"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(ContractModel):
    code: ErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    retry_after_ms: int | None = Field(default=None, ge=0)
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ErrorResponse(ContractModel):
    meta: ResponseMeta
    error: ErrorDetail


class CourseRAGError(Exception):
    """Stable in-process representation of a CourseRAG error response."""

    def __init__(
        self,
        *,
        context: RequestContext,
        code: ErrorCode,
        message: str,
        retryable: bool = False,
        retry_after_ms: int | None = None,
        details: dict[str, JsonValue] | None = None,
    ) -> None:
        self.response = ErrorResponse(
            meta=ResponseMeta.from_context(context),
            error=ErrorDetail(
                code=code,
                message=message,
                retryable=retryable,
                retry_after_ms=retry_after_ms,
                details=details or {},
            ),
        )
        super().__init__(message)

    @property
    def code(self) -> ErrorCode:
        return self.response.error.code


def require_idempotency_key(context: RequestContext) -> str:
    if context.idempotency_key is None:
        raise CourseRAGError(
            context=context,
            code=ErrorCode.INVALID_REQUEST,
            message="This operation requires an idempotency key.",
        )
    return context.idempotency_key
