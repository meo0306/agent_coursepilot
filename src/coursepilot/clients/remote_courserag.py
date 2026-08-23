from __future__ import annotations

import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from courserag.api.http_schema import (
    CAPABILITIES_PATH,
    CONTEXT_BINDING_VALIDATE_PATH,
    EVIDENCE_BATCH_PATH,
    HEALTH_PATH,
    build_path,
    document_builds_path,
    document_path,
    enrichment_batches_path,
    evidence_path,
    knowledge_base_contexts_path,
    knowledge_base_documents_path,
    knowledge_base_qa_path,
    knowledge_base_search_path,
    knowledge_points_snapshot_path,
    revoke_verified_content_path,
    verified_content_path,
)
from courserag.contracts import (
    CONTRACT_API_VERSION,
    BatchGetEvidenceRequest,
    BuildJob,
    CapabilitiesResponse,
    ContextBindingValidationRequest,
    ContextBindingValidationResponse,
    ContextPackage,
    ContextRequest,
    CourseRAGError,
    DeleteDocumentRequest,
    DeleteDocumentResult,
    DocumentPage,
    EnrichmentBatchResult,
    ErrorCode,
    ErrorResponse,
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
    ResponseMeta,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    SearchRequest,
    SearchResponse,
    StartBuildRequest,
    StartEnrichmentBatchRequest,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class RemoteCourseRAGClient:
    """P01 HTTP contract client.

    A caller must inject an ``httpx.Client``. Production transport policy,
    authentication, retries and circuit breaking belong to P17.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        principal_id: str | None = None,
        authorized_course_id: str | None = None,
        roles: tuple[str, ...] = (),
        bearer_token: str | None = None,
        max_attempts: int = 2,
        retry_base_seconds: float = 0.5,
        retry_max_seconds: float = 5.0,
    ) -> None:
        self._client = client
        self._principal_id = principal_id
        self._authorized_course_id = authorized_course_id
        self._roles = roles
        self._bearer_token = bearer_token
        self._max_attempts = max(1, min(max_attempts, 3))
        self._retry_base_seconds = max(0.0, retry_base_seconds)
        self._retry_max_seconds = max(0.0, retry_max_seconds)

    def register_document(self, request: RegisterDocumentRequest) -> RegisterDocumentResponse:
        return self._request(
            "POST",
            knowledge_base_documents_path(request.course_id),
            request,
            RegisterDocumentResponse,
            context=request.context,
        )

    def start_build(self, request: StartBuildRequest) -> BuildJob:
        if len(request.document_ids) != 1:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FEATURE_NOT_AVAILABLE,
                message="The P01 HTTP contract maps one document to one build request.",
            )
        return self._request(
            "POST",
            document_builds_path(request.document_ids[0]),
            request,
            BuildJob,
            context=request.context,
        )

    def get_build_job(self, job_id: str, request_context: RequestContext) -> BuildJob:
        return self._request(
            "GET",
            build_path(job_id),
            request_context,
            BuildJob,
            context=request_context,
        )

    def list_documents(self, request: ListDocumentsRequest) -> DocumentPage:
        return self._request(
            "GET",
            knowledge_base_documents_path(request.course_id),
            request,
            DocumentPage,
            context=request.context,
        )

    def list_knowledge_points(
        self, request: KnowledgePointSnapshotRequest
    ) -> KnowledgePointSnapshot:
        return self._request(
            "GET",
            knowledge_points_snapshot_path(request.course_id),
            request,
            KnowledgePointSnapshot,
            context=request.context,
        )

    def delete_document(self, request: DeleteDocumentRequest) -> DeleteDocumentResult:
        return self._request(
            "DELETE",
            document_path(request.document_id),
            request,
            DeleteDocumentResult,
            context=request.context,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        return self._request(
            "POST",
            knowledge_base_search_path(request.course_id),
            request,
            SearchResponse,
            context=request.context,
        )

    def build_context(self, request: ContextRequest) -> ContextPackage:
        return self._request(
            "POST",
            knowledge_base_contexts_path(request.course_id),
            request,
            ContextPackage,
            context=request.context,
        )

    def answer(self, request: QARequest) -> QAResponse:
        return self._request(
            "POST",
            knowledge_base_qa_path(request.course_id),
            request,
            QAResponse,
            context=request.context,
        )

    def get_evidence(self, request: GetEvidenceRequest) -> EvidenceRecord:
        return self._request(
            "GET",
            evidence_path(request.evidence_id),
            request,
            EvidenceRecord,
            context=request.context,
        )

    def batch_get_evidence(self, request: BatchGetEvidenceRequest) -> EvidenceBatch:
        return self._request(
            "POST",
            EVIDENCE_BATCH_PATH,
            request,
            EvidenceBatch,
            context=request.context,
        )

    def write_verified_content(
        self,
        request: VerifiedContentWriteRequest,
    ) -> VerifiedContentWriteResult:
        return self._request(
            "POST",
            verified_content_path(request.course_id),
            request,
            VerifiedContentWriteResult,
            context=request.context,
        )

    def revoke_verified_content(
        self,
        request: RevokeVerifiedContentRequest,
    ) -> RevokeVerifiedContentResult:
        return self._request(
            "POST",
            revoke_verified_content_path(request.verified_content_id),
            request,
            RevokeVerifiedContentResult,
            context=request.context,
        )

    def start_enrichment_batch(
        self,
        request: StartEnrichmentBatchRequest,
    ) -> EnrichmentBatchResult:
        return self._request(
            "POST",
            enrichment_batches_path(request.course_id),
            request,
            EnrichmentBatchResult,
            context=request.context,
        )

    def health(self) -> HealthResponse:
        context = RequestContext(caller="coursepilot-health")
        return self._request(
            "GET",
            HEALTH_PATH,
            context,
            HealthResponse,
            context=context,
        )

    def capabilities(self) -> CapabilitiesResponse:
        context = RequestContext(caller="coursepilot-capabilities")
        return self._request(
            "GET",
            CAPABILITIES_PATH,
            context,
            CapabilitiesResponse,
            context=context,
        )

    def validate_context_binding(
        self, request: ContextBindingValidationRequest
    ) -> ContextBindingValidationResponse:
        return self._request(
            "POST",
            CONTEXT_BINDING_VALIDATE_PATH,
            request,
            ContextBindingValidationResponse,
            context=request.context,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: BaseModel,
        response_type: type[ResponseT],
        *,
        context: RequestContext,
    ) -> ResponseT:
        if context.api_version != CONTRACT_API_VERSION:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.VERSION_CONFLICT,
                message="The requested CourseRAG API version is not supported.",
                details={
                    "expected_api_version": CONTRACT_API_VERSION,
                    "actual_api_version": context.api_version,
                },
            )
        headers = {
            "X-Request-ID": context.request_id,
            "X-Trace-ID": context.trace_id,
        }
        if context.idempotency_key is not None:
            headers["Idempotency-Key"] = context.idempotency_key
        if self._principal_id is not None:
            headers["X-CoursePilot-Principal-ID"] = self._principal_id
        payload_course_id = getattr(payload, "course_id", None)
        authorized_course_id = self._authorized_course_id or payload_course_id
        if authorized_course_id is not None:
            if payload_course_id is not None and payload_course_id != authorized_course_id:
                raise CourseRAGError(
                    context=context,
                    code=ErrorCode.FORBIDDEN,
                    message="Remote CourseRAG request course differs from the authorized course.",
                )
            headers["X-CoursePilot-Course-ID"] = authorized_course_id
        if self._roles:
            headers["X-CoursePilot-Roles"] = ",".join(self._roles)
        if self._bearer_token:
            headers["Authorization"] = f"Bearer {self._bearer_token}"
        operation = self._operation(path)
        safe_to_retry = operation in {"read", "health"} or (
            context.idempotency_key is not None and operation in {"write", "enrichment"}
        )
        query_params: dict[str, Any] | None = None
        json_payload: dict[str, Any] | None = payload.model_dump(mode="json")
        if method.upper() == "GET":
            query_params = self._query_params(payload)
            # Keep the v1 contract's context body for old peers; new peers may
            # ignore it and consume the query/header fields. This is a
            # compatibility bridge, not a source of request semantics.
        last_error: CourseRAGError | None = None
        for attempt in range(self._max_attempts):
            try:
                timeout = self._timeout_for(context)
                response = self._client.request(
                    method,
                    path,
                    timeout=timeout,
                    headers=headers,
                    params=query_params,
                    json=json_payload,
                )
            except httpx.ConnectError:
                last_error = CourseRAGError(
                    context=context,
                    code=ErrorCode.INTERNAL_ERROR,
                    message="CourseRAG connection failed.",
                    retryable=True,
                    details={"attempt": attempt + 1},
                )
            except httpx.TimeoutException:
                last_error = CourseRAGError(
                    context=context,
                    code=ErrorCode.DEADLINE_EXCEEDED,
                    message="CourseRAG request timed out.",
                    retryable=True,
                    details={"attempt": attempt + 1},
                )
            except httpx.HTTPError:
                last_error = CourseRAGError(
                    context=context,
                    code=ErrorCode.INTERNAL_ERROR,
                    message="CourseRAG transport failed.",
                    retryable=False,
                )
            else:
                if response.is_success:
                    try:
                        result = response_type.model_validate(response.json())
                    except (ValidationError, ValueError) as exc:
                        raise CourseRAGError(
                            context=context,
                            code=ErrorCode.INTERNAL_ERROR,
                            message="CourseRAG returned an invalid success response.",
                        ) from exc
                    self._validate_response_correlation(result, context)
                    return result
                last_error = self._error_from_response(response, context)
                if not (last_error.response.error.retryable and safe_to_retry):
                    raise last_error
            if not safe_to_retry or attempt + 1 >= self._max_attempts:
                break
            delay = min(self._retry_max_seconds, self._retry_base_seconds * (2**attempt))
            retry_after = last_error.response.error.retry_after_ms if last_error else None
            if retry_after is not None:
                delay = min(self._retry_max_seconds, max(delay, retry_after / 1000))
            if delay:
                time.sleep(delay)
        if last_error is not None:
            raise last_error
        raise CourseRAGError(
            context=context, code=ErrorCode.INTERNAL_ERROR, message="CourseRAG request failed."
        )

    @staticmethod
    def _operation(path: str) -> str:
        if path.endswith("/health") or path.endswith("/capabilities"):
            return "health"
        if "/verified-content" in path or "/enrichment-batches" in path:
            return "enrichment" if "enrichment" in path else "write"
        return (
            "read"
            if path.endswith("/documents") or "/evidence/" in path or path.endswith("/snapshot")
            else "query"
        )

    @staticmethod
    def _query_params(payload: BaseModel) -> dict[str, object]:
        return {
            k: v
            for k, v in payload.model_dump(mode="json").items()
            if k != "context" and v is not None
        }

    @staticmethod
    def _timeout_for(context: RequestContext) -> float | None:
        return context.deadline_ms / 1000 if context.deadline_ms else None

    def _error_from_response(
        self, response: httpx.Response, context: RequestContext
    ) -> CourseRAGError:
        try:
            error_response = ErrorResponse.model_validate(response.json())
            self._validate_meta_correlation(error_response.meta, context)
            error = error_response.error
            return CourseRAGError(
                context=context,
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                retry_after_ms=error.retry_after_ms,
                details=error.details,
            )
        except (ValidationError, ValueError):
            retryable = response.status_code in {429, 502, 503, 504}
            code = (
                ErrorCode.PROVIDER_RATE_LIMITED
                if response.status_code == 429
                else ErrorCode.INTERNAL_ERROR
            )
            return CourseRAGError(
                context=context,
                code=code,
                message="CourseRAG returned an invalid error response.",
                retryable=retryable,
            )

    @classmethod
    def _validate_response_correlation(
        cls,
        response: BaseModel,
        context: RequestContext,
    ) -> None:
        meta = getattr(response, "meta", None)
        if isinstance(meta, ResponseMeta):
            cls._validate_meta_correlation(meta, context)
            return
        if isinstance(response, CapabilitiesResponse):
            cls._validate_api_version(response.api_version, context)

    @classmethod
    def _validate_meta_correlation(
        cls,
        meta: ResponseMeta,
        context: RequestContext,
    ) -> None:
        cls._validate_api_version(meta.api_version, context)
        if meta.request_id != context.request_id or meta.trace_id != context.trace_id:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.INTERNAL_ERROR,
                message="CourseRAG returned mismatched request correlation metadata.",
                details={
                    "expected_request_id": context.request_id,
                    "actual_request_id": meta.request_id,
                    "expected_trace_id": context.trace_id,
                    "actual_trace_id": meta.trace_id,
                },
            )

    @staticmethod
    def _validate_api_version(
        api_version: str,
        context: RequestContext,
    ) -> None:
        if api_version != CONTRACT_API_VERSION or api_version != context.api_version:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.VERSION_CONFLICT,
                message="CourseRAG returned an incompatible API version.",
                details={
                    "expected_api_version": context.api_version,
                    "actual_api_version": api_version,
                },
            )
