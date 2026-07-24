from __future__ import annotations

from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from courserag.api.http_schema import (
    CAPABILITIES_PATH,
    EVIDENCE_BATCH_PATH,
    HEALTH_PATH,
    build_path,
    document_builds_path,
    document_path,
    evidence_path,
    knowledge_base_contexts_path,
    knowledge_base_documents_path,
    knowledge_base_qa_path,
    knowledge_base_search_path,
    revoke_verified_content_path,
    verified_content_path,
)
from courserag.contracts import (
    CONTRACT_API_VERSION,
    BatchGetEvidenceRequest,
    BuildJob,
    CapabilitiesResponse,
    ContextPackage,
    ContextRequest,
    CourseRAGError,
    DeleteDocumentRequest,
    DeleteDocumentResult,
    DocumentPage,
    ErrorCode,
    ErrorResponse,
    EvidenceBatch,
    EvidenceRecord,
    GetEvidenceRequest,
    HealthResponse,
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
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
)

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class RemoteCourseRAGClient:
    """P01 HTTP contract client.

    A caller must inject an ``httpx.Client``. Production transport policy,
    authentication, retries and circuit breaking belong to P17.
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

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
        try:
            response = self._client.request(
                method,
                path,
                json=payload.model_dump(mode="json"),
                headers=headers,
            )
        except httpx.TimeoutException as exc:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.DEADLINE_EXCEEDED,
                message="CourseRAG request timed out.",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.INTERNAL_ERROR,
                message="CourseRAG transport failed.",
                retryable=False,
            ) from exc

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

        try:
            error_response = ErrorResponse.model_validate(response.json())
        except (ValidationError, ValueError) as exc:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.INTERNAL_ERROR,
                message="CourseRAG returned an invalid error response.",
            ) from exc
        self._validate_meta_correlation(error_response.meta, context)
        raise CourseRAGError(
            context=context,
            code=error_response.error.code,
            message=error_response.error.message,
            retryable=error_response.error.retryable,
            retry_after_ms=error_response.error.retry_after_ms,
            details=error_response.error.details,
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
