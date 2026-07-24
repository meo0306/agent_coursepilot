from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from courserag.contracts.common import (
    ContractModel,
    ErrorDetail,
    RequestContext,
    ResponseMeta,
    UTCDateTime,
)


class DocumentStatus(StrEnum):
    REGISTERED = "registered"
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"
    DELETED = "deleted"


class BuildMode(StrEnum):
    INCREMENTAL = "incremental"
    FULL = "full"


class BuildStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BuildStage(StrEnum):
    PARSING = "parsing"
    NORMALIZING = "normalizing"
    CHUNKING = "chunking"
    EXTRACTING_METADATA = "extracting_metadata"
    EMBEDDING = "embedding"
    BUILDING_SPARSE_INDEX = "building_sparse_index"
    VALIDATING = "validating"
    PUBLISHING = "publishing"


class FileReference(ContractModel):
    object_uri: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(min_length=1)


class DocumentMetadata(ContractModel):
    title: str | None = None
    language: str = "zh-CN"


class RegisterDocumentRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    file: FileReference
    document_type: str = Field(min_length=1)
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)


class DocumentDescriptor(ContractModel):
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    status: DocumentStatus
    content_hash: str = Field(min_length=1)


class RegisterDocumentResponse(ContractModel):
    meta: ResponseMeta
    document: DocumentDescriptor


class StartBuildRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    document_ids: list[str] = Field(min_length=1)
    build_mode: BuildMode = BuildMode.INCREMENTAL
    parser_profile: str = Field(default="legacy_parser_v1", min_length=1)
    chunking_profile: str = Field(default="legacy_chunker_v1", min_length=1)
    retrieval_profile: str = Field(default="legacy_dense_v1", min_length=1)
    force_rebuild: bool = False


class BuildProgress(ContractModel):
    completed_units: int = Field(ge=0)
    total_units: int = Field(ge=0)
    percent: float = Field(ge=0, le=100)


class BuildJob(ContractModel):
    meta: ResponseMeta
    job_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    status: BuildStatus
    stage: BuildStage | None = None
    progress: BuildProgress
    document_versions: dict[str, str] = Field(default_factory=dict)
    target_index_version: str | None = None
    error: ErrorDetail | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime


class ListDocumentsRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    page_size: int = Field(default=50, ge=1, le=200)
    page_token: str | None = None


class DocumentSummary(ContractModel):
    document_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    document_type: str = Field(min_length=1)
    status: DocumentStatus
    document_version: str = Field(min_length=1)
    created_at: UTCDateTime
    updated_at: UTCDateTime


class DocumentPage(ContractModel):
    meta: ResponseMeta
    documents: list[DocumentSummary] = Field(default_factory=list)
    next_page_token: str | None = None


class DeleteDocumentRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)


class DeleteDocumentResult(ContractModel):
    meta: ResponseMeta
    document_id: str = Field(min_length=1)
    deleted: bool
