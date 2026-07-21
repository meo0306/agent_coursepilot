from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from coursepilot.db.base import Base
from coursepilot.models import IdempotencyRecord
from coursepilot.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyService,
    InvalidIdempotencyKeyError,
)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_same_key_and_payload_replays_success(session):
    calls = []
    service = IdempotencyService(session)

    first = service.execute(
        operation="course.create",
        idempotency_key="eval-course",
        request_payload={"course_name": "AI"},
        fn=lambda: calls.append("called") or {"id": "course-1"},
        response_status=201,
    )
    replay = service.execute(
        operation="course.create",
        idempotency_key="eval-course",
        request_payload={"course_name": "AI"},
        fn=lambda: calls.append("called-again") or {"id": "course-2"},
        response_status=201,
    )

    assert calls == ["called"]
    assert first.replayed is False
    assert replay.replayed is True
    assert replay.value == {"id": "course-1"}
    record = session.scalar(select(IdempotencyRecord))
    assert record is not None
    assert record.status == "succeeded"
    assert record.response_status == 201
    assert record.attempt_count == 1


def test_same_key_with_different_payload_conflicts(session):
    service = IdempotencyService(session)
    service.execute(
        operation="lesson.generate",
        idempotency_key="eval-lesson",
        request_payload={"sessions": 1},
        fn=lambda: {"lesson_id": "lesson-1"},
    )

    with pytest.raises(IdempotencyConflictError, match="different request payload"):
        service.execute(
            operation="lesson.generate",
            idempotency_key="eval-lesson",
            request_payload={"sessions": 2},
            fn=lambda: {"lesson_id": "lesson-2"},
        )


def test_active_lease_reports_request_in_progress(session):
    record = IdempotencyRecord(
        operation="document.build_kb",
        idempotency_key="eval-build",
        request_hash=IdempotencyService.request_hash({"document_id": "document-1"}),
        status="in_progress",
        attempt_count=1,
        locked_until=datetime.now(UTC) + timedelta(minutes=5),
    )
    session.add(record)
    session.commit()

    with pytest.raises(IdempotencyInProgressError, match="still in progress"):
        IdempotencyService(session).execute(
            operation="document.build_kb",
            idempotency_key="eval-build",
            request_payload={"document_id": "document-1"},
            fn=lambda: {"document_id": "document-1"},
        )


def test_failed_attempt_can_be_retried_with_same_key(session):
    service = IdempotencyService(session)

    with pytest.raises(RuntimeError, match="temporary failure"):
        service.execute(
            operation="ppt.generate",
            idempotency_key="eval-ppt",
            request_payload={"lesson_id": "lesson-1"},
            fn=lambda: (_ for _ in ()).throw(RuntimeError("temporary failure")),
        )

    retry = service.execute(
        operation="ppt.generate",
        idempotency_key="eval-ppt",
        request_payload={"lesson_id": "lesson-1"},
        fn=lambda: {"outline_id": "outline-1"},
    )

    assert retry.replayed is False
    assert retry.value == {"outline_id": "outline-1"}
    record = session.scalar(select(IdempotencyRecord))
    assert record is not None
    assert record.status == "succeeded"
    assert record.attempt_count == 2


@pytest.mark.parametrize("key", ["", "   ", "x" * 256])
def test_invalid_idempotency_key_is_rejected(session, key):
    with pytest.raises(InvalidIdempotencyKeyError):
        IdempotencyService(session).execute(
            operation="course.create",
            idempotency_key=key,
            request_payload={},
            fn=lambda: {},
        )
