from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.dependencies import get_courserag_service
from courserag.api.http_schema import API_PREFIX
from courserag.api.knowledge_points import CourseRAGAPIError
from courserag.api.principal import trusted_principal
from courserag.contracts import (
    ContextPackage,
    ContextRequest,
    CourseRAGError,
    ErrorCode,
    ErrorResponse,
    QARequest,
    QAResponse,
    RequestContext,
    ResponseMeta,
    SearchRequest,
    SearchResponse,
)
from courserag.security import PrincipalRole, TrustedPrincipal, require_course_role

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Retrieval and QA"])


def _request_context(
    x_request_id: Annotated[str | None, Header()] = None,
    x_trace_id: Annotated[str | None, Header()] = None,
) -> RequestContext:
    values: dict[str, str] = {}
    if x_request_id:
        values["request_id"] = x_request_id
    if x_trace_id:
        values["trace_id"] = x_trace_id
    return RequestContext(**values)


def _bind_context(payload: object, headers: RequestContext) -> None:
    context = getattr(payload, "context", None)
    if isinstance(context, RequestContext):
        if context.request_id.startswith("req_"):
            context.request_id = headers.request_id
        if context.trace_id.startswith("trace_"):
            context.trace_id = headers.trace_id


def _api_error(context: RequestContext, exc: Exception) -> CourseRAGAPIError:
    if isinstance(exc, PermissionError):
        return CourseRAGAPIError(
            403,
            ErrorResponse.model_validate(
                {
                    "meta": ResponseMeta.from_context(context).model_dump(mode="json"),
                    "error": {"code": "FORBIDDEN", "message": str(exc)},
                }
            ),
        )
    if isinstance(exc, ValueError):
        return CourseRAGAPIError(
            422,
            ErrorResponse.model_validate(
                {
                    "meta": ResponseMeta.from_context(context).model_dump(mode="json"),
                    "error": {"code": "INVALID_REQUEST", "message": str(exc)},
                }
            ),
        )
    if isinstance(exc, CourseRAGError):
        code = exc.code
        status = {
            ErrorCode.INVALID_REQUEST: 422,
            ErrorCode.RESOURCE_NOT_FOUND: 404,
            ErrorCode.INDEX_NOT_READY: 503,
            ErrorCode.FEATURE_NOT_AVAILABLE: 501,
            ErrorCode.PROVIDER_RATE_LIMITED: 429,
            ErrorCode.DEADLINE_EXCEEDED: 504,
            ErrorCode.VERSION_CONFLICT: 409,
            ErrorCode.IDEMPOTENCY_CONFLICT: 409,
            ErrorCode.FORBIDDEN: 403,
        }.get(code, 500)
        return CourseRAGAPIError(status, exc.response)
    return CourseRAGAPIError(
        500,
        ErrorResponse.model_validate(
            {
                "meta": ResponseMeta.from_context(context).model_dump(mode="json"),
                "error": {"code": "INTERNAL_ERROR", "message": "CourseRAG request failed"},
            }
        ),
    )


@router.post(
    "/knowledge-bases/{course_id}/search",
    response_model=SearchResponse,
)
def search(
    course_id: str,
    payload: SearchRequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    session: Annotated[Session, Depends(get_session)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
) -> SearchResponse:
    _bind_context(payload, headers)
    if payload.course_id != course_id:
        raise _api_error(headers, ValueError("Path course_id differs from request body"))
    try:
        require_course_role(principal, course_id, PrincipalRole.READER)
        return get_courserag_service(session).search(payload)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc


@router.post(
    "/knowledge-bases/{course_id}/contexts",
    response_model=ContextPackage,
)
def build_context(
    course_id: str,
    payload: ContextRequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    session: Annotated[Session, Depends(get_session)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
) -> ContextPackage:
    _bind_context(payload, headers)
    if payload.course_id != course_id:
        raise _api_error(headers, ValueError("Path course_id differs from request body"))
    try:
        require_course_role(principal, course_id, PrincipalRole.READER)
        return get_courserag_service(session).build_context(payload)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc


@router.post(
    "/knowledge-bases/{course_id}/qa",
    response_model=QAResponse,
)
def answer(
    course_id: str,
    payload: QARequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    session: Annotated[Session, Depends(get_session)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
) -> QAResponse:
    _bind_context(payload, headers)
    if payload.course_id != course_id:
        raise _api_error(headers, ValueError("Path course_id differs from request body"))
    try:
        require_course_role(principal, course_id, PrincipalRole.READER)
        return get_courserag_service(session).answer(payload)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc
