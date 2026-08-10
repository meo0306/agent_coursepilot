"""CourseRAG API schema and review routes."""

from courserag.api.http_schema import API_PREFIX
from courserag.api.knowledge_points import (
    CourseRAGAPIError,
    courserag_api_error_handler,
)
from courserag.api.knowledge_points import (
    router as knowledge_point_router,
)
from courserag.api.retrieval_qa import router as retrieval_qa_router
from courserag.api.verified_content import router as verified_content_router

__all__ = [
    "API_PREFIX",
    "CourseRAGAPIError",
    "courserag_api_error_handler",
    "knowledge_point_router",
    "retrieval_qa_router",
    "verified_content_router",
]
