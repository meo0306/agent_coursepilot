from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.dependencies import get_courserag_service
from courserag.api.http_schema import CAPABILITIES_PATH, HEALTH_PATH
from courserag.contracts import (
    CapabilitiesResponse,
    HealthResponse,
    HealthStatus,
)

router = APIRouter(tags=["CourseRAG Service"])


@router.get(HEALTH_PATH, response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status=HealthStatus.HEALTHY, dependencies={"postgres": HealthStatus.UNKNOWN}
    )


@router.get(CAPABILITIES_PATH, response_model=CapabilitiesResponse)
def capabilities(
    session: Annotated[Session, Depends(get_session)],
) -> CapabilitiesResponse:
    return get_courserag_service(session).capabilities()
