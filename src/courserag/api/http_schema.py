"""Frozen CourseRAG v1 HTTP paths.

P01 defines the wire contract only. FastAPI route mounting and production
remote reliability remain later-phase work.
"""

from urllib.parse import quote

API_PREFIX = "/api/courserag/v1"

HEALTH_PATH = f"{API_PREFIX}/health"
CAPABILITIES_PATH = f"{API_PREFIX}/capabilities"
EVIDENCE_BATCH_PATH = f"{API_PREFIX}/evidence/batch"


def _path_segment(value: str) -> str:
    """Encode an opaque identifier without permitting dot-segment traversal."""
    return quote(value, safe="").replace(".", "%2E")


def knowledge_base_documents_path(course_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(course_id)}/documents"


def knowledge_base_search_path(course_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(course_id)}/search"


def knowledge_base_contexts_path(course_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(course_id)}/contexts"


def knowledge_base_qa_path(course_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(course_id)}/qa"


def document_builds_path(document_id: str) -> str:
    return f"{API_PREFIX}/documents/{_path_segment(document_id)}/builds"


def document_path(document_id: str) -> str:
    return f"{API_PREFIX}/documents/{_path_segment(document_id)}"


def build_path(job_id: str) -> str:
    return f"{API_PREFIX}/builds/{_path_segment(job_id)}"


def evidence_path(evidence_id: str) -> str:
    return f"{API_PREFIX}/evidence/{_path_segment(evidence_id)}"


def verified_content_path(course_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(course_id)}/verified-content"


def enrichment_batches_path(course_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(course_id)}/enrichment-batches"


def revoke_verified_content_path(content_id: str) -> str:
    return f"{API_PREFIX}/verified-content/{_path_segment(content_id)}/revoke"


def knowledge_points_path(knowledge_base_id: str) -> str:
    return f"{API_PREFIX}/knowledge-bases/{_path_segment(knowledge_base_id)}/knowledge-points"


def knowledge_point_path(knowledge_point_id: str) -> str:
    return f"{API_PREFIX}/knowledge-points/{_path_segment(knowledge_point_id)}"
