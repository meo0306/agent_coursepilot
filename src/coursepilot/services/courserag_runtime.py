from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.ports.courserag import CourseRAGServicePort

_service_override: ContextVar[CourseRAGServicePort | None] = ContextVar(
    "coursepilot_courserag_service_override",
    default=None,
)


def get_courserag_service() -> CourseRAGServicePort:
    """Resolve the current CourseRAG boundary implementation.

    The single-process demo profile remains local. Tests can install an
    isolated override without placing service objects in Graph state or trace
    metadata.
    """

    service = _service_override.get()
    if service is not None:
        return service
    return LocalCourseRAGAdapter()


@contextmanager
def override_courserag_service(service: CourseRAGServicePort) -> Iterator[None]:
    token = _service_override.set(service)
    try:
        yield
    finally:
        _service_override.reset(token)
