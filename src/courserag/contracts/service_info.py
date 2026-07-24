from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from courserag.contracts.common import CONTRACT_API_VERSION, SERVICE_VERSION, ContractModel


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CourseRAGOperation(StrEnum):
    REGISTER_DOCUMENT = "register_document"
    START_BUILD = "start_build"
    GET_BUILD_JOB = "get_build_job"
    LIST_DOCUMENTS = "list_documents"
    DELETE_DOCUMENT = "delete_document"
    SEARCH = "search"
    BUILD_CONTEXT = "build_context"
    QA = "qa"
    GET_EVIDENCE = "get_evidence"
    BATCH_GET_EVIDENCE = "batch_get_evidence"
    WRITE_VERIFIED_CONTENT = "write_verified_content"
    REVOKE_VERIFIED_CONTENT = "revoke_verified_content"


class HealthResponse(ContractModel):
    status: HealthStatus
    dependencies: dict[str, HealthStatus] = Field(default_factory=dict)


class CapabilitiesResponse(ContractModel):
    api_version: str = CONTRACT_API_VERSION
    service_version: str = SERVICE_VERSION
    supported_document_types: list[str] = Field(default_factory=lambda: ["pdf", "docx"])
    supported_retrieval_modes: list[str] = Field(default_factory=lambda: ["dense"])
    supported_operations: list[CourseRAGOperation] = Field(default_factory=list)
    supports_rerank: bool = False
    supports_query_rewrite: bool = False
    supports_streaming_progress: bool = False
    supports_verified_writeback: bool = False
