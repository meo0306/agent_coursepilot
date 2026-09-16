from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Never, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from coursepilot.adapters.courserag_mapping import (
    LEGACY_DOCUMENT_VERSION,
    LEGACY_INDEX_VERSION,
    LEGACY_RETRIEVAL_CONFIG_VERSION,
    LEGACY_SEARCH_WARNINGS,
    legacy_result_to_search_hit,
)
from coursepilot.models import Document, GenerationTask, KnowledgeChunk
from coursepilot.rag.chunker import Chunker
from coursepilot.rag.parsers import UnsupportedParserError, get_parser
from coursepilot.rag.retriever import CoursePilotRetriever
from coursepilot.rag.vector_store import ChromaVectorStore
from coursepilot.schemas.document_schema import DocumentBuildResponse
from coursepilot.schemas.task_schema import AsyncTaskAccepted
from courserag.contracts import (
    BatchGetEvidenceRequest,
    BuildJob,
    BuildProgress,
    BuildStage,
    BuildStatus,
    CapabilitiesResponse,
    ContextBindingValidationRequest,
    ContextBindingValidationResponse,
    ContextPackage,
    ContextRequest,
    CourseRAGError,
    CourseRAGOperation,
    DeleteDocumentRequest,
    DeleteDocumentResult,
    DocumentPage,
    DocumentStatus,
    DocumentSummary,
    ErrorCode,
    ErrorDetail,
    EvidenceBatch,
    EvidenceRecord,
    GenerationContextRequest,
    GenerationContextResponse,
    GetEvidenceRequest,
    HealthResponse,
    HealthStatus,
    KnowledgePointEvidenceLink,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotItem,
    KnowledgePointSnapshotRequest,
    ListDocumentsRequest,
    QARequest,
    QAResponse,
    QueryTrace,
    RegisterDocumentRequest,
    RegisterDocumentResponse,
    RequestContext,
    ResponseMeta,
    RetrievalMode,
    RetrievalTrace,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    SearchRequest,
    SearchResponse,
    SourceTier,
    StartBuildRequest,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
    require_idempotency_key,
)

ResultT = TypeVar("ResultT")


class LocalCourseRAGAdapter:
    """P01 adapter over the current CoursePilot ORM and dense Chroma runtime."""

    def __init__(
        self,
        session: Session | None = None,
        *,
        chunker: Chunker | None = None,
        vector_store: ChromaVectorStore | None = None,
        retrieval_backend: str = "legacy",
        versioned_search: Callable[[SearchRequest], SearchResponse] | None = None,
        versioned_context: Callable[[ContextRequest], ContextPackage] | None = None,
        versioned_generation_context: (
            Callable[[GenerationContextRequest], GenerationContextResponse] | None
        ) = None,
        versioned_answer: Callable[[QARequest], QAResponse] | None = None,
        versioned_write_verified: Callable[
            [VerifiedContentWriteRequest], VerifiedContentWriteResult
        ]
        | None = None,
        versioned_revoke_verified: Callable[
            [RevokeVerifiedContentRequest], RevokeVerifiedContentResult
        ]
        | None = None,
    ) -> None:
        self.session = session
        self._chunker = chunker
        self._vector_store = vector_store
        if retrieval_backend not in {"legacy", "versioned"}:
            raise ValueError("Unsupported CourseRAG retrieval backend")
        self.retrieval_backend = retrieval_backend
        self.versioned_search = versioned_search
        self.versioned_context = versioned_context
        self.versioned_generation_context = versioned_generation_context
        self.versioned_answer = versioned_answer
        self.versioned_write_verified = versioned_write_verified
        self.versioned_revoke_verified = versioned_revoke_verified

    @property
    def chunker(self) -> Chunker:
        if self._chunker is None:
            self._chunker = Chunker()
        return self._chunker

    @property
    def vector_store(self) -> ChromaVectorStore:
        if self._vector_store is None:
            self._vector_store = ChromaVectorStore()
        return self._vector_store

    def register_document(self, request: RegisterDocumentRequest) -> RegisterDocumentResponse:
        self._unsupported(request.context, CourseRAGOperation.REGISTER_DOCUMENT)

    def start_build(self, request: StartBuildRequest) -> BuildJob:
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.START_BUILD,
            lambda: self._start_build(request),
        )

    def _start_build(self, request: StartBuildRequest) -> BuildJob:
        from coursepilot.services.async_task_service import AsyncTaskService
        from coursepilot.services.idempotency_service import (
            IdempotencyConflictError,
            IdempotencyInProgressError,
            IdempotencyService,
            InvalidIdempotencyKeyError,
        )

        session = self._require_session(request.context)
        idempotency_key = require_idempotency_key(request.context)
        if len(request.document_ids) != 1:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FEATURE_NOT_AVAILABLE,
                message="The legacy adapter supports one document per build job.",
                details={"document_count": len(request.document_ids)},
            )
        document_id = request.document_ids[0]
        document = session.get(Document, document_id)
        if document is None or document.course_id != request.course_id:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Document not found for the requested course.",
                details={"course_id": request.course_id, "document_id": document_id},
            )

        payload = {
            "course_id": request.course_id,
            "document_ids": request.document_ids,
            "build_mode": request.build_mode.value,
            "parser_profile": request.parser_profile,
            "chunking_profile": request.chunking_profile,
            "retrieval_profile": request.retrieval_profile,
            "force_rebuild": request.force_rebuild,
        }
        try:
            execution = IdempotencyService(session).execute(
                operation="courserag.start_build",
                idempotency_key=idempotency_key,
                request_payload=payload,
                fn=lambda: AsyncTaskService(session).enqueue(
                    course_id=request.course_id,
                    task_type="build_kb",
                    input_params={"document_id": document_id},
                ),
                response_status=202,
                resource_type="async_task",
                resource_id_field="task_id",
                retry_if_resource_failed=True,
            )
        except IdempotencyConflictError as exc:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.IDEMPOTENCY_CONFLICT,
                message=str(exc),
            ) from exc
        except IdempotencyInProgressError as exc:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.IDEMPOTENCY_CONFLICT,
                message=str(exc),
                retryable=True,
            ) from exc
        except InvalidIdempotencyKeyError as exc:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.INVALID_REQUEST,
                message=str(exc),
            ) from exc

        accepted = AsyncTaskAccepted.model_validate(execution.value)
        return self.get_build_job(accepted.task_id, request.context)

    def get_build_job(self, job_id: str, request_context: RequestContext) -> BuildJob:
        return self._with_structured_errors(
            request_context,
            CourseRAGOperation.GET_BUILD_JOB,
            lambda: self._get_build_job(job_id, request_context),
        )

    def _get_build_job(self, job_id: str, request_context: RequestContext) -> BuildJob:
        session = self._require_session(request_context)
        task = session.get(GenerationTask, job_id)
        if task is None or task.task_type != "build_kb":
            raise CourseRAGError(
                context=request_context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Build job not found.",
                details={"job_id": job_id},
            )
        return self._task_to_build_job(task, request_context)

    def list_documents(self, request: ListDocumentsRequest) -> DocumentPage:
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.LIST_DOCUMENTS,
            lambda: self._list_documents(request),
        )

    def list_knowledge_points(
        self, request: KnowledgePointSnapshotRequest
    ) -> KnowledgePointSnapshot:
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.LIST_KNOWLEDGE_POINTS,
            lambda: self._list_knowledge_points(request),
        )

    def _list_knowledge_points(
        self, request: KnowledgePointSnapshotRequest
    ) -> KnowledgePointSnapshot:
        session = self._require_session(request.context)
        from courserag.application.knowledge_point_service import KnowledgePointService

        rows = KnowledgePointService(session).list(
            request.course_id,
            status=None if request.include_unreviewed else "approved",
            limit=request.limit,
            offset=0,
        )
        items = [
            KnowledgePointSnapshotItem(
                knowledge_point_id=row.knowledge_point_id,
                course_id=request.course_id,
                canonical_name=row.canonical_name,
                aliases=list(row.aliases),
                summary=row.summary,
                review_status=str(row.review_status),
                version=row.version_number,
                section_ids=list(row.section_ids),
                evidence_links=[
                    KnowledgePointEvidenceLink(
                        evidence_id=link.evidence_id,
                        role=link.role,
                        strength=link.strength,
                    )
                    for link in row.evidence_links
                ],
            )
            for row in rows
            if not request.section_ids or set(request.section_ids).intersection(row.section_ids)
        ]
        payload = [item.model_dump(mode="json") for item in items]
        import hashlib
        import json

        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        return KnowledgePointSnapshot(
            meta=ResponseMeta.from_context(request.context),
            course_id=request.course_id,
            items=items,
            snapshot_sha256=digest,
        )

    def _list_documents(self, request: ListDocumentsRequest) -> DocumentPage:
        session = self._require_session(request.context)
        try:
            offset = int(request.page_token or "0")
        except ValueError as exc:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.INVALID_REQUEST,
                message="page_token must be a non-negative integer offset.",
            ) from exc
        if offset < 0:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.INVALID_REQUEST,
                message="page_token must be a non-negative integer offset.",
            )
        statement = (
            select(Document)
            .where(Document.course_id == request.course_id)
            .order_by(Document.created_at.desc())
            .offset(offset)
            .limit(request.page_size + 1)
        )
        rows = list(session.scalars(statement))
        has_next = len(rows) > request.page_size
        rows = rows[: request.page_size]
        return DocumentPage(
            meta=ResponseMeta.from_context(
                request.context,
                warnings=["LEGACY_DOCUMENTS_HAVE_NO_STABLE_VERSIONS"],
            ),
            documents=[
                DocumentSummary(
                    document_id=document.id,
                    course_id=document.course_id,
                    filename=document.file_name,
                    document_type=document.file_type,
                    status=self._document_status(document.parse_status),
                    document_version=LEGACY_DOCUMENT_VERSION,
                    created_at=self._as_utc(document.created_at),
                    updated_at=self._as_utc(document.updated_at),
                )
                for document in rows
            ],
            next_page_token=str(offset + request.page_size) if has_next else None,
        )

    def delete_document(self, request: DeleteDocumentRequest) -> DeleteDocumentResult:
        self._unsupported(request.context, CourseRAGOperation.DELETE_DOCUMENT)

    def search(self, request: SearchRequest) -> SearchResponse:
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.SEARCH,
            lambda: self._search(request),
        )

    def _search(self, request: SearchRequest) -> SearchResponse:
        if self.retrieval_backend == "versioned":
            if self.versioned_search is None:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.INDEX_NOT_READY,
                    message="Versioned retrieval has no valid Active Index.",
                )
            return self.versioned_search(request)
        self._validate_legacy_search(request)
        started = perf_counter()
        chapter = (
            request.filters.section_paths[0][0]
            if request.filters.section_paths and request.filters.section_paths[0]
            else None
        )
        source_type = request.filters.document_types[0] if request.filters.document_types else None
        verified_only: bool | None = None
        if request.filters.source_tiers == [SourceTier.TEACHER_VERIFIED]:
            verified_only = True
        elif request.filters.source_tiers == [SourceTier.PRIMARY_SOURCE]:
            verified_only = False

        results = CoursePilotRetriever(self.vector_store).search(
            course_id=request.course_id,
            query=request.query,
            chapter=chapter,
            source_type=source_type,
            verified_only=verified_only,
            top_k=request.retrieval.return_top_n,
        )
        hits = [
            legacy_result_to_search_hit(result, rank=rank)
            for rank, result in enumerate(results, start=1)
        ]
        duration_ms = max(0, round((perf_counter() - started) * 1000))
        return SearchResponse(
            meta=ResponseMeta.from_context(
                request.context,
                duration_ms=duration_ms,
                warnings=list(LEGACY_SEARCH_WARNINGS),
            ),
            query=QueryTrace(
                original=request.query,
                normalized=" ".join(request.query.split()),
            ),
            hits=hits,
            retrieval=RetrievalTrace(
                retrieval_config_version=LEGACY_RETRIEVAL_CONFIG_VERSION,
                index_version=LEGACY_INDEX_VERSION,
                candidate_count=len(results),
                returned_count=len(hits),
            ),
        )

    def build_context(self, request: ContextRequest) -> ContextPackage:
        if self.retrieval_backend == "versioned":
            callback = self.versioned_context
            if callback is None:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.INDEX_NOT_READY,
                    message="Versioned Context runtime is not configured.",
                )
            return self._with_structured_errors(
                request.context,
                CourseRAGOperation.BUILD_CONTEXT,
                lambda: callback(request),
            )
        self._unsupported(request.context, CourseRAGOperation.BUILD_CONTEXT)

    def answer(self, request: QARequest) -> QAResponse:
        if self.retrieval_backend == "versioned":
            callback = self.versioned_answer
            if callback is None:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.FEATURE_NOT_AVAILABLE,
                    message="Versioned QA runtime is not configured.",
                )
            return self._with_structured_errors(
                request.context,
                CourseRAGOperation.QA,
                lambda: callback(request),
            )
        self._unsupported(request.context, CourseRAGOperation.QA)

    def build_generation_context(
        self, request: GenerationContextRequest
    ) -> GenerationContextResponse:
        callback = self.versioned_generation_context
        if callback is None:
            self._unsupported(
                request.context,
                CourseRAGOperation.BUILD_GENERATION_CONTEXT,
            )
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.BUILD_GENERATION_CONTEXT,
            lambda: callback(request),
        )

    def get_evidence(self, request: GetEvidenceRequest) -> EvidenceRecord:
        self._unsupported(request.context, CourseRAGOperation.GET_EVIDENCE)

    def batch_get_evidence(self, request: BatchGetEvidenceRequest) -> EvidenceBatch:
        self._unsupported(request.context, CourseRAGOperation.BATCH_GET_EVIDENCE)

    def write_verified_content(
        self,
        request: VerifiedContentWriteRequest,
    ) -> VerifiedContentWriteResult:
        callback = self.versioned_write_verified
        if callback is None:
            self._unsupported(request.context, CourseRAGOperation.WRITE_VERIFIED_CONTENT)
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.WRITE_VERIFIED_CONTENT,
            lambda: callback(request),
        )

    def revoke_verified_content(
        self,
        request: RevokeVerifiedContentRequest,
    ) -> RevokeVerifiedContentResult:
        callback = self.versioned_revoke_verified
        if callback is None:
            self._unsupported(request.context, CourseRAGOperation.REVOKE_VERIFIED_CONTENT)
        return self._with_structured_errors(
            request.context,
            CourseRAGOperation.REVOKE_VERIFIED_CONTENT,
            lambda: callback(request),
        )

    def health(self) -> HealthResponse:
        return HealthResponse(
            status=HealthStatus.HEALTHY,
            dependencies={
                "postgres": (
                    HealthStatus.HEALTHY if self.session is not None else HealthStatus.UNKNOWN
                ),
                "vector_store": (
                    HealthStatus.HEALTHY if self._vector_store is not None else HealthStatus.UNKNOWN
                ),
                "object_store": HealthStatus.UNKNOWN,
                "message_broker": HealthStatus.UNKNOWN,
            },
        )

    def capabilities(self) -> CapabilitiesResponse:
        supported = [
            CourseRAGOperation.START_BUILD,
            CourseRAGOperation.GET_BUILD_JOB,
            CourseRAGOperation.LIST_DOCUMENTS,
            CourseRAGOperation.SEARCH,
        ]
        if self.versioned_write_verified is not None:
            supported.append(CourseRAGOperation.WRITE_VERIFIED_CONTENT)
        if self.versioned_revoke_verified is not None:
            supported.append(CourseRAGOperation.REVOKE_VERIFIED_CONTENT)
        if self.versioned_generation_context is not None:
            supported.append(CourseRAGOperation.BUILD_GENERATION_CONTEXT)
        return CapabilitiesResponse(
            supported_operations=supported,
            supported_generation_context_versions=(
                ["v1"] if self.versioned_generation_context is not None else []
            ),
            supports_verified_writeback=self.versioned_write_verified is not None,
            supports_enrichment=self.versioned_write_verified is not None,
            supports_incremental_build=self.retrieval_backend == "versioned",
        )

    def validate_context_binding(
        self, request: ContextBindingValidationRequest
    ) -> ContextBindingValidationResponse:
        batch = self.batch_get_evidence(
            BatchGetEvidenceRequest(
                context=request.context,
                course_id=request.course_id,
                evidence_ids=list(request.evidence_versions),
            )
        )
        actual = {record.evidence_id: record.content_hash for record in batch.records}
        changed = sorted(
            evidence_id
            for evidence_id, expected_hash in request.evidence_versions.items()
            if actual.get(evidence_id) != expected_hash
        )
        status = "changed_evidence" if changed else "compatible"
        if request.index_version != LEGACY_INDEX_VERSION and self.retrieval_backend == "legacy":
            status = "stale_primary_index"
        return ContextBindingValidationResponse(
            meta=ResponseMeta.from_context(request.context),
            status=status,
            stale=status != "compatible",
            changed_evidence_ids=changed,
        )

    def execute_legacy_build(
        self,
        document_id: str,
        *,
        task_id: str | None = None,
    ) -> DocumentBuildResponse | None:
        """Run the unchanged B0 parser/chunker/Chroma build pipeline."""
        from coursepilot.services.async_task_service import (
            complete_execution_task,
            prepare_execution_task,
        )

        session = self._require_session(RequestContext())
        document = session.get(Document, document_id)
        if document is None:
            return None
        task = None
        if task_id is not None:
            task = prepare_execution_task(
                session,
                task_id=task_id,
                course_id=document.course_id,
                task_type="build_kb",
                input_params={"document_id": document.id},
            )

        try:
            parser = get_parser(document.file_path)
            parsed = parser.parse(document.file_path)
            chunks = self.chunker.split(
                parsed,
                course_id=document.course_id,
                document_id=document.id,
                source_type=document.source_type,
            )
            if not chunks:
                raise ValueError("No text chunks were extracted from this document")

            old_chunk_ids = list(
                session.scalars(
                    select(KnowledgeChunk.chroma_doc_id).where(
                        KnowledgeChunk.document_id == document.id
                    )
                )
            )
            self.vector_store.delete_chunks(document.course_id, old_chunk_ids)
            session.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document.id))
            collection_name = self.vector_store.add_chunks(chunks)
            for chunk in chunks:
                session.add(
                    KnowledgeChunk(
                        id=chunk.id,
                        course_id=chunk.course_id,
                        document_id=chunk.document_id,
                        source_type=chunk.source_type,
                        chapter=chunk.chapter,
                        section=chunk.section,
                        page=chunk.page,
                        title=chunk.title,
                        content_preview=chunk.content[:1000],
                        knowledge_points_json=chunk.knowledge_points,
                        verified=chunk.verified,
                        chroma_collection=collection_name,
                        chroma_doc_id=chunk.id,
                    )
                )
            document.parse_status = "built"
            document.error_message = None
            response = DocumentBuildResponse(
                document_id=document.id,
                course_id=document.course_id,
                parse_status=document.parse_status,
                chunk_count=len(chunks),
            )
            if task is not None:
                complete_execution_task(task, response)
            session.commit()
            return response
        except Exception as exc:
            session.rollback()
            document = session.get(Document, document_id)
            if document is not None:
                document.parse_status = "failed"
                document.error_message = self._format_error(exc)
                response = DocumentBuildResponse(
                    document_id=document.id,
                    course_id=document.course_id,
                    parse_status=document.parse_status,
                    chunk_count=0,
                    error_message=document.error_message,
                )
                if task is not None:
                    complete_execution_task(
                        task,
                        response,
                        status="failed",
                        error_message=document.error_message,
                    )
                session.commit()
                return response
            raise

    def _validate_legacy_search(self, request: SearchRequest) -> None:
        unsupported = (
            request.retrieval.mode != RetrievalMode.DENSE
            or request.retrieval.enable_query_rewrite
            or request.retrieval.enable_parent_expansion
            or request.retrieval.candidate_k != request.retrieval.return_top_n
            or request.retrieval.rerank_top_n != request.retrieval.return_top_n
            or bool(request.filters.document_ids)
            or bool(request.filters.document_version_ids)
            or bool(request.filters.knowledge_point_ids)
            or request.filters.index_version is not None
            or len(request.filters.document_types) > 1
            or len(request.filters.section_paths) > 1
            or any(len(path) != 1 for path in request.filters.section_paths)
            or request.filters.page_range is not None
            or len(request.filters.source_tiers) > 1
            or any(
                tier not in {SourceTier.PRIMARY_SOURCE, SourceTier.TEACHER_VERIFIED}
                for tier in request.filters.source_tiers
            )
        )
        if unsupported:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FEATURE_NOT_AVAILABLE,
                message="The requested search options are not supported by the legacy adapter.",
            )

    @staticmethod
    def _with_structured_errors(
        context: RequestContext,
        operation: CourseRAGOperation,
        callback: Callable[[], ResultT],
    ) -> ResultT:
        try:
            return callback()
        except CourseRAGError:
            raise
        except Exception as exc:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.INTERNAL_ERROR,
                message="The local CourseRAG adapter operation failed.",
                details={"operation": operation.value},
            ) from exc

    def _require_session(self, context: RequestContext) -> Session:
        if self.session is None:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.FEATURE_NOT_AVAILABLE,
                message="This local operation requires a database session.",
            )
        return self.session

    @staticmethod
    def _unsupported(context: RequestContext, operation: CourseRAGOperation) -> Never:
        raise CourseRAGError(
            context=context,
            code=ErrorCode.FEATURE_NOT_AVAILABLE,
            message=f"The local P01 adapter does not support {operation.value}.",
            details={"operation": operation.value},
        )

    @staticmethod
    def _document_status(value: str) -> DocumentStatus:
        return {
            "uploaded": DocumentStatus.REGISTERED,
            "building": DocumentStatus.BUILDING,
            "built": DocumentStatus.READY,
            "failed": DocumentStatus.FAILED,
        }.get(value, DocumentStatus.REGISTERED)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _task_to_build_job(
        self,
        task: GenerationTask,
        context: RequestContext,
    ) -> BuildJob:
        status = {
            "pending": BuildStatus.QUEUED,
            "running": BuildStatus.RUNNING,
            "completed": BuildStatus.SUCCEEDED,
            "needs_review": BuildStatus.SUCCEEDED,
            "failed": BuildStatus.FAILED,
        }.get(task.status, BuildStatus.FAILED)
        percent = {
            BuildStatus.QUEUED: 0.0,
            BuildStatus.RUNNING: 50.0,
            BuildStatus.SUCCEEDED: 100.0,
            BuildStatus.FAILED: 100.0,
            BuildStatus.CANCELLED: 100.0,
        }[status]
        document_id = str((task.input_params_json or {}).get("document_id", "unknown"))
        error = (
            ErrorDetail(
                code=ErrorCode.INTERNAL_ERROR,
                message=task.error_message or "Legacy build failed.",
                retryable=False,
            )
            if status == BuildStatus.FAILED
            else None
        )
        return BuildJob(
            meta=ResponseMeta.from_context(
                context,
                warnings=["LEGACY_BUILD_JOB_HAS_STAGE_LEVEL_PROGRESS_ONLY"],
            ),
            job_id=task.id,
            course_id=task.course_id,
            status=status,
            stage=(
                None
                if status == BuildStatus.QUEUED
                else (
                    BuildStage.PARSING if status == BuildStatus.RUNNING else BuildStage.PUBLISHING
                )
            ),
            progress=BuildProgress(
                completed_units=round(percent),
                total_units=100,
                percent=percent,
            ),
            document_versions={document_id: LEGACY_DOCUMENT_VERSION},
            target_index_version=LEGACY_INDEX_VERSION,
            error=error,
            created_at=self._as_utc(task.created_at),
            updated_at=self._as_utc(task.updated_at),
        )

    @staticmethod
    def _format_error(exc: Exception) -> str:
        if isinstance(exc, UnsupportedParserError):
            suffix = Path(str(exc)).suffix
            return str(exc) if not suffix else f"Unsupported parser for file type: {suffix}"
        return str(exc)
