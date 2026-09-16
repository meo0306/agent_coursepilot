"""CourseRAG API schema and review routes."""

from courserag.api.bindings import router as bindings_router
from courserag.api.documents import router as documents_router
from courserag.api.evidence import router as evidence_router
from courserag.api.generation_context import router as generation_context_router
from courserag.api.http_schema import API_PREFIX
from courserag.api.knowledge_points import (
    CourseRAGAPIError,
    courserag_api_error_handler,
)
from courserag.api.knowledge_points import (
    router as knowledge_point_router,
)
from courserag.api.retrieval_qa import router as retrieval_qa_router
from courserag.api.service_info import router as service_info_router
from courserag.api.verified_content import router as verified_content_router

__all__ = [
    "API_PREFIX",
    "CourseRAGAPIError",
    "courserag_api_error_handler",
    "knowledge_point_router",
    "retrieval_qa_router",
    "verified_content_router",
    "service_info_router",
    "documents_router",
    "evidence_router",
    "generation_context_router",
    "bindings_router",
]
