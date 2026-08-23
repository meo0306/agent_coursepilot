from __future__ import annotations

from fastapi import APIRouter

from courserag.api.http_schema import CAPABILITIES_PATH, HEALTH_PATH
from courserag.contracts import (
    CapabilitiesResponse,
    CourseRAGOperation,
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
def capabilities() -> CapabilitiesResponse:
    return CapabilitiesResponse(
        supported_operations=list(CourseRAGOperation),
        supports_verified_writeback=True,
        supports_enrichment=True,
        supports_incremental_build=True,
    )
