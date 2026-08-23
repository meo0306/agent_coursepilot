from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

import httpx
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.clients.remote_courserag import RemoteCourseRAGClient
from coursepilot.ports.courserag import CourseRAGServicePort
from courserag.contracts import (
    ContextPackage,
    ContextRequest,
    QARequest,
    QAResponse,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    SearchRequest,
    SearchResponse,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
)

_service_override: ContextVar[CourseRAGServicePort | None] = ContextVar(
    "coursepilot_courserag_service_override",
    default=None,
)


@dataclass(frozen=True)
class VersionedCourseRAGRuntime:
    search: Callable[[SearchRequest], SearchResponse]
    build_context: Callable[[ContextRequest], ContextPackage]
    answer: Callable[[QARequest], QAResponse]
    write_verified_content: (
        Callable[[VerifiedContentWriteRequest], VerifiedContentWriteResult] | None
    ) = None
    revoke_verified_content: (
        Callable[[RevokeVerifiedContentRequest], RevokeVerifiedContentResult] | None
    ) = None


_versioned_runtime: VersionedCourseRAGRuntime | None = None


def configure_versioned_courserag_runtime(runtime: VersionedCourseRAGRuntime | None) -> None:
    global _versioned_runtime
    _versioned_runtime = runtime


def get_courserag_service(session: Session | None = None) -> CourseRAGServicePort:
    """Resolve the current CourseRAG boundary implementation.

    The single-process demo profile remains local. Tests can install an
    isolated override without placing service objects in Graph state or trace
    metadata.
    """

    service = _service_override.get()
    if service is not None:
        return service
    runtime = _versioned_runtime
    if settings.COURSEPILOT_COURSERAG_MODE == "remote":
        if (
            not settings.COURSEPILOT_COURSERAG_BASE_URL
            or not settings.COURSEPILOT_COURSERAG_AUTH_TOKEN
        ):
            raise RuntimeError("Remote CourseRAG mode requires base URL and auth token")
        transport = httpx.Client(base_url=settings.COURSEPILOT_COURSERAG_BASE_URL.rstrip("/"))
        return RemoteCourseRAGClient(
            transport,
            principal_id="coursepilot-service",
            roles=("system",),
            bearer_token=settings.COURSEPILOT_COURSERAG_AUTH_TOKEN.get_secret_value(),
            max_attempts=settings.COURSEPILOT_COURSERAG_MAX_ATTEMPTS,
            retry_base_seconds=settings.COURSEPILOT_COURSERAG_RETRY_BASE_SECONDS,
            retry_max_seconds=settings.COURSEPILOT_COURSERAG_RETRY_MAX_SECONDS,
        )
    if settings.COURSEPILOT_COURSERAG_MODE == "mock":
        raise RuntimeError("Mock CourseRAG mode must be installed with override_courserag_service")
    return LocalCourseRAGAdapter(
        session=session,
        retrieval_backend=settings.COURSERAG_RETRIEVAL_BACKEND,
        versioned_search=runtime.search if runtime else None,
        versioned_context=runtime.build_context if runtime else None,
        versioned_answer=runtime.answer if runtime else None,
        versioned_write_verified=runtime.write_verified_content if runtime else None,
        versioned_revoke_verified=runtime.revoke_verified_content if runtime else None,
    )


@contextmanager
def override_courserag_service(service: CourseRAGServicePort) -> Iterator[None]:
    token = _service_override.set(service)
    try:
        yield
    finally:
        _service_override.reset(token)
