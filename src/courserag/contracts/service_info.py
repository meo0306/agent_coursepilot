from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

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
    LIST_KNOWLEDGE_POINTS = "list_knowledge_points"
    DELETE_DOCUMENT = "delete_document"
    SEARCH = "search"
    BUILD_CONTEXT = "build_context"
    BUILD_GENERATION_CONTEXT = "build_generation_context"
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
    supported_generation_context_versions: list[str] = Field(default_factory=list)
    supports_rerank: bool = False
    supports_query_rewrite: bool = False
    supports_streaming_progress: bool = False
    supports_verified_writeback: bool = False
    supports_enrichment: bool = False
    supports_incremental_build: bool = False

    @model_validator(mode="after")
    def validate_generation_context_capability(self) -> CapabilitiesResponse:
        supports_operation = (
            CourseRAGOperation.BUILD_GENERATION_CONTEXT in self.supported_operations
        )
        supports_version = "v1" in self.supported_generation_context_versions
        if supports_operation != supports_version:
            raise ValueError(
                "generation context operation and supported v1 contract must be declared together"
            )
        if len(self.supported_generation_context_versions) != len(
            set(self.supported_generation_context_versions)
        ):
            raise ValueError("generation context versions must be unique")
        return self
