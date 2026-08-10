from __future__ import annotations

from collections.abc import Iterator

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.knowledge_points import (
    CourseRAGAPIError,
    courserag_api_error_handler,
    router,
)
from tests.courserag.knowledge_points.test_persistence import _facts
from tests.courserag.knowledge_points.test_service import _knowledge_point


def _client(session: Session) -> TestClient:
    app = FastAPI()
    app.add_exception_handler(CourseRAGAPIError, courserag_api_error_handler)
    app.include_router(router)

    def session_override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_session] = session_override
    return TestClient(app)


def test_list_detail_and_review_contract(p03_session: Session) -> None:
    _facts(p03_session)
    _knowledge_point(p03_session, identifier="kp-api", title="Artificial intelligence")
    client = _client(p03_session)

    listed = client.get(
        "/api/courserag/v1/knowledge-bases/kb-1/knowledge-points",
        headers={"X-Request-ID": "req-list", "X-Trace-ID": "trace-list"},
    )
    assert listed.status_code == 200
    assert listed.json()["meta"]["request_id"] == "req-list"
    assert listed.json()["payload"][0]["knowledge_point_id"] == "kp-api"

    approved = client.post(
        "/api/courserag/v1/knowledge-points/kp-api/approve",
        json={"comment": "reviewed"},
        headers={
            "Idempotency-Key": "api-approve-1",
            "If-Match": '"1"',
            "X-Reviewer-ID": "teacher-1",
        },
    )
    assert approved.status_code == 200
    assert approved.json()["payload"]["review_status"] == "approved"
    assert approved.json()["payload"]["version_number"] == 2

    replay = client.post(
        "/api/courserag/v1/knowledge-points/kp-api/approve",
        json={"comment": "reviewed"},
        headers={
            "Idempotency-Key": "api-approve-1",
            "If-Match": "1",
            "X-Reviewer-ID": "teacher-1",
        },
    )
    assert replay.status_code == 200
    assert replay.json()["payload"] == approved.json()["payload"]


def test_review_errors_use_stable_courserag_envelope(p03_session: Session) -> None:
    client = _client(p03_session)
    response = client.get(
        "/api/courserag/v1/knowledge-points/missing",
        headers={"X-Request-ID": "req-error", "X-Trace-ID": "trace-error"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "meta": {
            "request_id": "req-error",
            "trace_id": "trace-error",
            "api_version": "v1",
            "service_version": "0.1.0",
            "duration_ms": 0,
            "warnings": [],
        },
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "Knowledge Point not found",
            "retryable": False,
            "retry_after_ms": None,
            "details": {},
        },
    }
