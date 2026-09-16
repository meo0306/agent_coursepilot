"""Application-owned CourseRAG service dependency seam."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

_factory: Callable[[Any], Any] | None = None


def configure_service_factory(factory: Callable[[Any], Any]) -> None:
    global _factory
    _factory = factory


def get_courserag_service(session: Any = None) -> Any:
    if _factory is None:
        raise RuntimeError("CourseRAG service factory has not been configured")
    return _factory(session)
