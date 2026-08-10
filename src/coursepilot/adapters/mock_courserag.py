from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from courserag.contracts import (
    BatchGetEvidenceRequest,
    BuildJob,
    BuildProgress,
    BuildStatus,
    CapabilitiesResponse,
    ContextItem,
    ContextPackage,
    ContextRequest,
    CourseRAGError,
    CourseRAGOperation,
    DeleteDocumentRequest,
    DeleteDocumentResult,
    DocumentDescriptor,
    DocumentPage,
    DocumentStatus,
    DocumentSummary,
    ErrorCode,
    EvidenceBatch,
    EvidenceRecord,
    GetEvidenceRequest,
    HealthResponse,
    HealthStatus,
    ListDocumentsRequest,
    PackingReport,
    QARequest,
    QAResponse,
    QueryTrace,
    RegisterDocumentRequest,
    RegisterDocumentResponse,
    RequestContext,
    ResponseMeta,
    RetrievalTrace,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    SearchHit,
    SearchRequest,
    SearchResponse,
    StartBuildRequest,
    VerifiedContentStatus,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
    require_idempotency_key,
)


class MockCourseRAGService:
    """Deterministic in-memory CourseRAG implementation for workflow tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self._documents: dict[str, DocumentSummary] = {}
        self._search_hits: dict[str, list[SearchHit]] = {}
        self._evidence: dict[str, EvidenceRecord] = {}
        self._build_jobs: dict[str, BuildJob] = {}
        self._register_idempotency: dict[str, tuple[str, RegisterDocumentResponse]] = {}
        self._build_idempotency: dict[str, tuple[str, str]] = {}
        self._delete_idempotency: dict[str, tuple[str, DeleteDocumentResult]] = {}
        self._verified_idempotency: dict[str, tuple[str, VerifiedContentWriteResult]] = {}
        self._verified_results: dict[str, VerifiedContentWriteResult] = {}
        self._verified_courses: dict[str, str] = {}
        self._revoke_idempotency: dict[str, tuple[str, RevokeVerifiedContentResult]] = {}
        self._failures: dict[str, tuple[ErrorCode, str, bool]] = {}

    def seed_search(self, course_id: str, hits: list[SearchHit]) -> None:
        self._search_hits[course_id] = list(hits)

    def seed_evidence(self, record: EvidenceRecord) -> None:
        self._evidence[record.evidence_id] = record

    def fail_next(
        self,
        operation: CourseRAGOperation,
        *,
        code: ErrorCode,
        message: str,
        retryable: bool = False,
    ) -> None:
        self._failures[operation.value] = (code, message, retryable)

    def register_document(self, request: RegisterDocumentRequest) -> RegisterDocumentResponse:
        self._record(CourseRAGOperation.REGISTER_DOCUMENT, request.context)
        self._maybe_fail(CourseRAGOperation.REGISTER_DOCUMENT, request.context)
        key = require_idempotency_key(request.context)
        request_hash = self._request_hash(request.model_dump(mode="json", exclude={"context"}))
        existing = self._register_idempotency.get(key)
        if existing is not None:
            existing_hash, response = existing
            if existing_hash != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Idempotency key was reused with a different document request.",
                )
            return response.model_copy(update={"meta": ResponseMeta.from_context(request.context)})

        document_digest = hashlib.sha256(
            f"{request.course_id}:{request.file.sha256}".encode()
        ).hexdigest()
        document_id = f"doc_{document_digest[:24]}"
        now = datetime.now(UTC)
        self._documents[document_id] = DocumentSummary(
            document_id=document_id,
            course_id=request.course_id,
            filename=request.file.filename,
            document_type=request.document_type,
            status=DocumentStatus.REGISTERED,
            document_version="v1",
            created_at=now,
            updated_at=now,
        )
        response = RegisterDocumentResponse(
            meta=ResponseMeta.from_context(request.context),
            document=DocumentDescriptor(
                document_id=document_id,
                document_version="v1",
                status=DocumentStatus.REGISTERED,
                content_hash=request.file.sha256,
            ),
        )
        self._register_idempotency[key] = (request_hash, response)
        return response

    def start_build(self, request: StartBuildRequest) -> BuildJob:
        self._record(CourseRAGOperation.START_BUILD, request.context)
        self._maybe_fail(CourseRAGOperation.START_BUILD, request.context)
        key = require_idempotency_key(request.context)
        request_hash = self._request_hash(
            {
                "course_id": request.course_id,
                "document_ids": request.document_ids,
                "build_mode": request.build_mode.value,
                "parser_profile": request.parser_profile,
                "chunking_profile": request.chunking_profile,
                "retrieval_profile": request.retrieval_profile,
                "force_rebuild": request.force_rebuild,
            }
        )
        existing = self._build_idempotency.get(key)
        if existing is not None:
            existing_hash, job_id = existing
            if existing_hash != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Idempotency key was reused with a different build request.",
                )
            return self._build_jobs[job_id].model_copy(
                update={"meta": ResponseMeta.from_context(request.context)}
            )

        now = datetime.now(UTC)
        job_id = f"build_{uuid4().hex}"
        job = BuildJob(
            meta=ResponseMeta.from_context(request.context),
            job_id=job_id,
            course_id=request.course_id,
            status=BuildStatus.QUEUED,
            progress=BuildProgress(completed_units=0, total_units=100, percent=0),
            document_versions={document_id: "v1" for document_id in request.document_ids},
            target_index_version="mock-index-v1",
            created_at=now,
            updated_at=now,
        )
        self._build_jobs[job_id] = job
        self._build_idempotency[key] = (request_hash, job_id)
        return job

    def get_build_job(self, job_id: str, request_context: RequestContext) -> BuildJob:
        self._record(CourseRAGOperation.GET_BUILD_JOB, request_context)
        self._maybe_fail(CourseRAGOperation.GET_BUILD_JOB, request_context)
        job = self._build_jobs.get(job_id)
        if job is None:
            raise CourseRAGError(
                context=request_context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Build job not found.",
                details={"job_id": job_id},
            )
        return job.model_copy(update={"meta": ResponseMeta.from_context(request_context)})

    def list_documents(self, request: ListDocumentsRequest) -> DocumentPage:
        self._record(CourseRAGOperation.LIST_DOCUMENTS, request.context)
        self._maybe_fail(CourseRAGOperation.LIST_DOCUMENTS, request.context)
        documents = [
            document
            for document in self._documents.values()
            if document.course_id == request.course_id
        ][: request.page_size]
        return DocumentPage(
            meta=ResponseMeta.from_context(request.context),
            documents=documents,
        )

    def delete_document(self, request: DeleteDocumentRequest) -> DeleteDocumentResult:
        self._record(CourseRAGOperation.DELETE_DOCUMENT, request.context)
        self._maybe_fail(CourseRAGOperation.DELETE_DOCUMENT, request.context)
        key = require_idempotency_key(request.context)
        request_hash = self._request_hash(request.model_dump(mode="json", exclude={"context"}))
        existing = self._delete_idempotency.get(key)
        if existing is not None:
            existing_hash, result = existing
            if existing_hash != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Idempotency key was reused with a different delete request.",
                )
            return result.model_copy(update={"meta": ResponseMeta.from_context(request.context)})

        document = self._documents.get(request.document_id)
        deleted = document is not None and document.course_id == request.course_id
        if deleted:
            del self._documents[request.document_id]
        result = DeleteDocumentResult(
            meta=ResponseMeta.from_context(request.context),
            document_id=request.document_id,
            deleted=deleted,
        )
        self._delete_idempotency[key] = (request_hash, result)
        return result

    def search(self, request: SearchRequest) -> SearchResponse:
        self._record(CourseRAGOperation.SEARCH, request.context)
        self._maybe_fail(CourseRAGOperation.SEARCH, request.context)
        hits = [
            hit.model_copy(update={"rank": rank})
            for rank, hit in enumerate(
                self._search_hits.get(request.course_id, [])[: request.retrieval.return_top_n],
                start=1,
            )
        ]
        return SearchResponse(
            meta=ResponseMeta.from_context(request.context),
            query=QueryTrace(
                original=request.query,
                normalized=" ".join(request.query.split()),
            ),
            hits=hits,
            retrieval=RetrievalTrace(
                retrieval_config_version="mock-retrieval-v1",
                index_version="mock-index-v1",
                candidate_count=len(hits),
                returned_count=len(hits),
            ),
        )

    def build_context(self, request: ContextRequest) -> ContextPackage:
        self._record(CourseRAGOperation.BUILD_CONTEXT, request.context)
        self._maybe_fail(CourseRAGOperation.BUILD_CONTEXT, request.context)
        search_request = request.search_request or SearchRequest(
            context=request.context,
            course_id=request.course_id,
            query=request.query,
        )
        response = self.search(search_request)
        selected = response.hits[: request.packing.max_items]
        items = [
            ContextItem(
                context_item_id=f"ctx_{hit.chunk_id}",
                text=hit.text,
                document_id=hit.document_id,
                section_path=hit.section_path,
                page_start=hit.page_start,
                page_end=hit.page_end,
                evidence_ids=hit.evidence_ids,
                token_count=len(hit.text.split()),
            )
            for hit in selected
        ]
        return ContextPackage(
            meta=ResponseMeta.from_context(request.context),
            query=request.query,
            purpose=request.purpose,
            items=items,
            token_count=sum(item.token_count for item in items),
            retrieval_trace_id=f"retrieval_{request.context.request_id}",
            index_version=response.retrieval.index_version,
            packing_report=PackingReport(
                candidate_count=len(response.hits),
                selected_count=len(items),
                deduplicated_count=0,
                discarded_for_budget=max(0, len(response.hits) - len(items)),
            ),
        )

    def answer(self, request: QARequest) -> QAResponse:
        self._record(CourseRAGOperation.QA, request.context)
        self._maybe_fail(CourseRAGOperation.QA, request.context)
        return QAResponse(
            meta=ResponseMeta.from_context(request.context),
            question=request.question,
            answer_status="abstained_insufficient_evidence",
        )

    def get_evidence(self, request: GetEvidenceRequest) -> EvidenceRecord:
        self._record(CourseRAGOperation.GET_EVIDENCE, request.context)
        self._maybe_fail(CourseRAGOperation.GET_EVIDENCE, request.context)
        record = self._evidence.get(request.evidence_id)
        if record is None:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Evidence not found.",
                details={"evidence_id": request.evidence_id},
            )
        return record.model_copy(update={"meta": ResponseMeta.from_context(request.context)})

    def batch_get_evidence(self, request: BatchGetEvidenceRequest) -> EvidenceBatch:
        self._record(CourseRAGOperation.BATCH_GET_EVIDENCE, request.context)
        self._maybe_fail(CourseRAGOperation.BATCH_GET_EVIDENCE, request.context)
        records = [
            self._evidence[evidence_id].model_copy(
                update={"meta": ResponseMeta.from_context(request.context)}
            )
            for evidence_id in request.evidence_ids
            if evidence_id in self._evidence
        ]
        missing = [
            evidence_id for evidence_id in request.evidence_ids if evidence_id not in self._evidence
        ]
        return EvidenceBatch(
            meta=ResponseMeta.from_context(request.context),
            records=records,
            missing_ids=missing,
        )

    def write_verified_content(
        self,
        request: VerifiedContentWriteRequest,
    ) -> VerifiedContentWriteResult:
        self._record(CourseRAGOperation.WRITE_VERIFIED_CONTENT, request.context)
        self._maybe_fail(CourseRAGOperation.WRITE_VERIFIED_CONTENT, request.context)
        key = require_idempotency_key(request.context)
        request_hash = self._request_hash(request.model_dump(mode="json", exclude={"context"}))
        existing = self._verified_idempotency.get(key)
        if existing is not None:
            existing_hash, result = existing
            if existing_hash != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Idempotency key was reused with different verified content.",
                )
            return result.model_copy(
                update={
                    "meta": ResponseMeta.from_context(request.context),
                    "created": False,
                }
            )
        content_id = f"verified_{uuid4().hex}"
        result = VerifiedContentWriteResult(
            meta=ResponseMeta.from_context(request.context),
            verified_content_id=content_id,
            version="v1",
            status=VerifiedContentStatus.INDEXED,
            index_version="mock-index-v1",
            created=True,
        )
        self._verified_results[content_id] = result
        self._verified_courses[content_id] = request.course_id
        self._verified_idempotency[key] = (request_hash, result)
        return result

    def revoke_verified_content(
        self,
        request: RevokeVerifiedContentRequest,
    ) -> RevokeVerifiedContentResult:
        self._record(CourseRAGOperation.REVOKE_VERIFIED_CONTENT, request.context)
        self._maybe_fail(CourseRAGOperation.REVOKE_VERIFIED_CONTENT, request.context)
        key = require_idempotency_key(request.context)
        request_hash = self._request_hash(request.model_dump(mode="json", exclude={"context"}))
        existing = self._revoke_idempotency.get(key)
        if existing is not None:
            existing_hash, result = existing
            if existing_hash != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Idempotency key was reused with a different revoke request.",
                )
            return result.model_copy(update={"meta": ResponseMeta.from_context(request.context)})

        stored = self._verified_results.get(request.verified_content_id)
        belongs_to_course = (
            self._verified_courses.get(request.verified_content_id) == request.course_id
        )
        revoked = (
            stored is not None
            and belongs_to_course
            and stored.status != VerifiedContentStatus.REVOKED
        )
        if revoked and stored is not None:
            self._verified_results[request.verified_content_id] = stored.model_copy(
                update={"status": VerifiedContentStatus.REVOKED}
            )
        result = RevokeVerifiedContentResult(
            meta=ResponseMeta.from_context(request.context),
            verified_content_id=request.verified_content_id,
            status=VerifiedContentStatus.REVOKED,
            revoked=revoked,
        )
        self._revoke_idempotency[key] = (request_hash, result)
        return result

    def health(self) -> HealthResponse:
        return HealthResponse(
            status=HealthStatus.HEALTHY,
            dependencies={
                "postgres": HealthStatus.HEALTHY,
                "vector_store": HealthStatus.HEALTHY,
                "object_store": HealthStatus.HEALTHY,
                "message_broker": HealthStatus.HEALTHY,
            },
        )

    def capabilities(self) -> CapabilitiesResponse:
        return CapabilitiesResponse(
            supported_retrieval_modes=["dense", "sparse", "hybrid"],
            supported_operations=list(CourseRAGOperation),
            supports_rerank=True,
            supports_query_rewrite=True,
            supports_streaming_progress=True,
            supports_verified_writeback=True,
            supports_enrichment=True,
            supports_incremental_build=True,
        )

    def _record(self, operation: CourseRAGOperation, context: RequestContext) -> None:
        self.calls.append((operation.value, context.request_id))

    def _maybe_fail(self, operation: CourseRAGOperation, context: RequestContext) -> None:
        failure = self._failures.pop(operation.value, None)
        if failure is None:
            return
        code, message, retryable = failure
        raise CourseRAGError(
            context=context,
            code=code,
            message=message,
            retryable=retryable,
        )

    @staticmethod
    def _request_hash(payload: object) -> str:
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()
