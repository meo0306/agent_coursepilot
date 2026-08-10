from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
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
