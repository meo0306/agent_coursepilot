from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.dependencies import get_courserag_service
from courserag.api.http_schema import API_PREFIX
from courserag.api.principal import trusted_principal
from courserag.api.retrieval_qa import _api_error, _bind_context, _request_context
from courserag.contracts import (
    GenerationContextRequest,
    GenerationContextResponse,
    RequestContext,
)
from courserag.security import PrincipalRole, TrustedPrincipal, require_course_role

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Generation Context"])


@router.post(
    "/knowledge-bases/{course_id}/generation-contexts",
    response_model=GenerationContextResponse,
)
def build_generation_context(
    course_id: str,
    payload: GenerationContextRequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    session: Annotated[Session, Depends(get_session)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
) -> GenerationContextResponse:
    _bind_context(payload, headers)
    if payload.course_id != course_id:
        raise _api_error(headers, ValueError("Path course_id differs from request body"))
    try:
        require_course_role(principal, course_id, PrincipalRole.READER)
        return get_courserag_service(session).build_generation_context(payload)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc
