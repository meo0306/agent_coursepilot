from __future__ import annotations

from typing import Protocol, runtime_checkable

from courserag.contracts import (
    BatchGetEvidenceRequest,
    BuildJob,
    CapabilitiesResponse,
    ContextBindingValidationRequest,
    ContextBindingValidationResponse,
    ContextPackage,
    ContextRequest,
    DeleteDocumentRequest,
    DeleteDocumentResult,
    DocumentPage,
    EvidenceBatch,
    EvidenceRecord,
    GetEvidenceRequest,
    HealthResponse,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotRequest,
    ListDocumentsRequest,
    QARequest,
    QAResponse,
    RegisterDocumentRequest,
    RegisterDocumentResponse,
    RequestContext,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    SearchRequest,
    SearchResponse,
    StartBuildRequest,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
)


@runtime_checkable
class KnowledgeBasePort(Protocol):
    def register_document(self, request: RegisterDocumentRequest) -> RegisterDocumentResponse: ...

    def start_build(self, request: StartBuildRequest) -> BuildJob: ...

    def get_build_job(self, job_id: str, request_context: RequestContext) -> BuildJob: ...

    def list_documents(self, request: ListDocumentsRequest) -> DocumentPage: ...

    def delete_document(self, request: DeleteDocumentRequest) -> DeleteDocumentResult: ...


@runtime_checkable
class KnowledgePointPort(Protocol):
    def list_knowledge_points(
        self, request: KnowledgePointSnapshotRequest
    ) -> KnowledgePointSnapshot: ...


@runtime_checkable
class RetrievalPort(Protocol):
    def search(self, request: SearchRequest) -> SearchResponse: ...

    def build_context(self, request: ContextRequest) -> ContextPackage: ...


@runtime_checkable
class QuestionAnsweringPort(Protocol):
    def answer(self, request: QARequest) -> QAResponse: ...


@runtime_checkable
class EvidencePort(Protocol):
    def get_evidence(self, request: GetEvidenceRequest) -> EvidenceRecord: ...

    def batch_get_evidence(self, request: BatchGetEvidenceRequest) -> EvidenceBatch: ...


@runtime_checkable
class VerifiedContentPort(Protocol):
    def write_verified_content(
        self,
        request: VerifiedContentWriteRequest,
    ) -> VerifiedContentWriteResult: ...

    def revoke_verified_content(
        self,
        request: RevokeVerifiedContentRequest,
    ) -> RevokeVerifiedContentResult: ...


@runtime_checkable
class ServiceInfoPort(Protocol):
    def health(self) -> HealthResponse: ...

    def capabilities(self) -> CapabilitiesResponse: ...


@runtime_checkable
class ContextBindingPort(Protocol):
    def validate_context_binding(
        self, request: ContextBindingValidationRequest
    ) -> ContextBindingValidationResponse: ...


@runtime_checkable
class CourseRAGServicePort(
    KnowledgeBasePort,
    KnowledgePointPort,
    RetrievalPort,
    QuestionAnsweringPort,
    EvidencePort,
    VerifiedContentPort,
    ServiceInfoPort,
    ContextBindingPort,
    Protocol,
):
    """Complete consumer-facing CourseRAG boundary."""
