"""CourseRAG public package.

Only :mod:`courserag.contracts` is a supported cross-boundary import for
CoursePilot. Runtime implementation modules remain internal to CourseRAG.
"""

from courserag.contracts import CONTRACT_API_VERSION, SERVICE_VERSION

__all__ = ["CONTRACT_API_VERSION", "SERVICE_VERSION"]
