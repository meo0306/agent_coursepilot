"""Review API for persistent CourseRAG Knowledge Point assets."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse
from pydantic import Field
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.application.knowledge_point_service import (
    KnowledgePointApplicationError,
    KnowledgePointIdempotencyConflict,
    KnowledgePointNotFound,
    KnowledgePointService,
    KnowledgePointUpdate,
    KnowledgePointValidationError,
    KnowledgePointVersionConflict,
    KnowledgePointView,
    MergeKnowledgePoints,
    SplitKnowledgePoint,
)
from courserag.contracts.common import (
    ContractModel,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    RequestContext,
    ResponseMeta,
)
from courserag.contracts.knowledge_points import (
    KnowledgePointEvidenceLink,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotItem,
)

from .http_schema import API_PREFIX

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Knowledge Points"])


class KnowledgePointResponse(ContractModel):
    meta: ResponseMeta
    payload: KnowledgePointView


class KnowledgePointListResponse(ContractModel):
    meta: ResponseMeta
    payload: tuple[KnowledgePointView, ...]


class KnowledgePointSplitResponse(ContractModel):
    meta: ResponseMeta
    payload: tuple[KnowledgePointView, ...]


class ReviewActionRequest(ContractModel):
    comment: str | None = Field(default=None, max_length=4000)


class CourseRAGAPIError(Exception):
    """HTTP status paired with the frozen CourseRAG error envelope."""

    def __init__(self, status_code: int, response: ErrorResponse) -> None:
        self.status_code = status_code
        self.response = response
        super().__init__(response.error.message)


async def courserag_api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, CourseRAGAPIError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.response.model_dump(mode="json"),
    )


def _context(
    request_id: str | None,
    trace_id: str | None,
    idempotency_key: str | None = None,
) -> RequestContext:
    values: dict[str, str] = {}
    if request_id:
        values["request_id"] = request_id
    if trace_id:
        values["trace_id"] = trace_id
    if idempotency_key:
        values["idempotency_key"] = idempotency_key
    return RequestContext(**values)


def _expected_version(if_match: str) -> int:
    value = if_match.strip()
    if value.startswith("W/"):
        value = value[2:]
    value = value.strip('"')
    try:
        version = int(value)
    except ValueError as exc:
        raise ValueError("If-Match must contain an integer version") from exc
    if version < 1:
        raise ValueError("If-Match version must be positive")
    return version


def _error(context: RequestContext, exc: Exception) -> CourseRAGAPIError:
    if isinstance(exc, KnowledgePointNotFound):
        status_code, code = 404, ErrorCode.RESOURCE_NOT_FOUND
    elif isinstance(exc, KnowledgePointVersionConflict):
        status_code, code = 409, ErrorCode.VERSION_CONFLICT
    elif isinstance(exc, KnowledgePointIdempotencyConflict):
        status_code, code = 409, ErrorCode.IDEMPOTENCY_CONFLICT
    elif isinstance(exc, (KnowledgePointValidationError, ValueError)):
        status_code, code = 422, ErrorCode.INVALID_REQUEST
    else:
        status_code, code = 500, ErrorCode.INTERNAL_ERROR
    message = str(exc) if status_code != 500 else "Knowledge Point operation failed"
    return CourseRAGAPIError(
        status_code,
        ErrorResponse(
            meta=ResponseMeta.from_context(context),
            error=ErrorDetail(code=code, message=message),
        ),
    )


def _headers(
    x_request_id: Annotated[str | None, Header()] = None,
    x_trace_id: Annotated[str | None, Header()] = None,
) -> RequestContext:
    return _context(x_request_id, x_trace_id)


@router.get(
    "/knowledge-bases/{knowledge_base_id}/knowledge-points",
    response_model=KnowledgePointListResponse,
)
def list_knowledge_points(
    knowledge_base_id: str,
    context: Annotated[RequestContext, Depends(_headers)],
    session: Annotated[Session, Depends(get_session)],
    review_status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> KnowledgePointListResponse:
    try:
        items = KnowledgePointService(session).list(
            knowledge_base_id, status=review_status, limit=limit, offset=offset
        )
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    return KnowledgePointListResponse(meta=ResponseMeta.from_context(context), payload=items)


@router.get(
    "/knowledge-bases/{knowledge_base_id}/knowledge-points/snapshot",
    response_model=KnowledgePointSnapshot,
)
def knowledge_point_snapshot(
    knowledge_base_id: str,
    context: Annotated[RequestContext, Depends(_headers)],
    session: Annotated[Session, Depends(get_session)],
    review_status: Annotated[str | None, Query()] = "approved",
    limit: Annotated[int, Query(ge=1, le=500)] = 500,
) -> KnowledgePointSnapshot:
    try:
        items = KnowledgePointService(session).list(
            knowledge_base_id, status=review_status, limit=limit, offset=0
        )
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    snapshot_items = [
        KnowledgePointSnapshotItem(
            knowledge_point_id=item.knowledge_point_id,
            course_id=knowledge_base_id,
            canonical_name=item.canonical_name,
            aliases=list(item.aliases),
            summary=item.summary,
            review_status=str(item.review_status),
            version=item.version_number,
            section_ids=list(item.section_ids),
            evidence_links=[
                KnowledgePointEvidenceLink(
                    evidence_id=link.evidence_id,
                    role=link.role,
                    strength=link.strength,
                )
                for link in item.evidence_links
            ],
        )
        for item in items
    ]
    return KnowledgePointSnapshot(
        meta=ResponseMeta.from_context(context),
        course_id=knowledge_base_id,
        items=snapshot_items,
        snapshot_sha256=hashlib.sha256(
            json.dumps(
                [item.model_dump(mode="json") for item in snapshot_items],
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest(),
    )


@router.get("/knowledge-points/{knowledge_point_id}", response_model=KnowledgePointResponse)
def get_knowledge_point(
    knowledge_point_id: str,
    context: Annotated[RequestContext, Depends(_headers)],
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgePointResponse:
    try:
        item = KnowledgePointService(session).get(knowledge_point_id)
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    return KnowledgePointResponse(meta=ResponseMeta.from_context(context), payload=item)


def _write_context(
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    x_reviewer_id: Annotated[str, Header(alias="X-Reviewer-ID")],
    if_match: Annotated[str, Header(alias="If-Match")],
    x_request_id: Annotated[str | None, Header()] = None,
    x_trace_id: Annotated[str | None, Header()] = None,
) -> tuple[RequestContext, str, int]:
    context = _context(x_request_id, x_trace_id, idempotency_key)
    try:
        version = _expected_version(if_match)
    except ValueError as exc:
        raise _error(context, exc) from exc
    return context, x_reviewer_id.strip(), version


WriteContext = Annotated[tuple[RequestContext, str, int], Depends(_write_context)]


@router.patch("/knowledge-points/{knowledge_point_id}", response_model=KnowledgePointResponse)
def modify_knowledge_point(
    knowledge_point_id: str,
    payload: KnowledgePointUpdate,
    write: WriteContext,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgePointResponse:
    context, reviewer_id, expected_version = write
    try:
        item = KnowledgePointService(session).modify(
            knowledge_point_id,
            payload,
            expected_version=expected_version,
            idempotency_key=context.idempotency_key or "",
            reviewer_id=reviewer_id,
        )
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    return KnowledgePointResponse(meta=ResponseMeta.from_context(context), payload=item)


@router.post(
    "/knowledge-points/{knowledge_point_id}/merge",
    response_model=KnowledgePointResponse,
)
def merge_knowledge_points(
    knowledge_point_id: str,
    payload: MergeKnowledgePoints,
    write: WriteContext,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgePointResponse:
    context, reviewer_id, expected_version = write
    try:
        item = KnowledgePointService(session).merge(
            knowledge_point_id,
            payload,
            expected_version=expected_version,
            idempotency_key=context.idempotency_key or "",
            reviewer_id=reviewer_id,
        )
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    return KnowledgePointResponse(meta=ResponseMeta.from_context(context), payload=item)


@router.post(
    "/knowledge-points/{knowledge_point_id}/split",
    response_model=KnowledgePointSplitResponse,
)
def split_knowledge_point(
    knowledge_point_id: str,
    payload: SplitKnowledgePoint,
    write: WriteContext,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgePointSplitResponse:
    context, reviewer_id, expected_version = write
    try:
        items = KnowledgePointService(session).split(
            knowledge_point_id,
            payload,
            expected_version=expected_version,
            idempotency_key=context.idempotency_key or "",
            reviewer_id=reviewer_id,
        )
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    return KnowledgePointSplitResponse(meta=ResponseMeta.from_context(context), payload=items)


@router.post(
    "/knowledge-points/{knowledge_point_id}/{action}",
    response_model=KnowledgePointResponse,
)
def transition_knowledge_point(
    knowledge_point_id: str,
    action: Literal["approve", "reject", "deprecate"],
    payload: ReviewActionRequest,
    write: WriteContext,
    session: Annotated[Session, Depends(get_session)],
) -> KnowledgePointResponse:
    context, reviewer_id, expected_version = write
    try:
        item = KnowledgePointService(session).transition(
            knowledge_point_id,
            action=action,
            expected_version=expected_version,
            idempotency_key=context.idempotency_key or "",
            reviewer_id=reviewer_id,
            comment=payload.comment,
        )
    except KnowledgePointApplicationError as exc:
        raise _error(context, exc) from exc
    return KnowledgePointResponse(meta=ResponseMeta.from_context(context), payload=item)
