from __future__ import annotations

import pytest

from coursepilot.adapters.mock_courserag import MockCourseRAGService
from courserag.contracts import (
    BuildStatus,
    CourseRAGError,
    CourseRAGOperation,
    DeleteDocumentRequest,
    ErrorCode,
    FileReference,
    RegisterDocumentRequest,
    RequestContext,
    RevokeVerifiedContentRequest,
    ScoreBreakdown,
    SearchHit,
    SearchRequest,
    SourceTier,
    StartBuildRequest,
    VerifiedContentType,
    VerifiedContentWriteRequest,
)


def _hit() -> SearchHit:
    return SearchHit(
        rank=1,
        chunk_id="chunk-1",
        document_id="doc-1",
        document_version="v1",
        document_type="textbook",
        section_path=["第1章"],
        text="启发式搜索",
        scores=ScoreBreakdown(dense=0.9),
        evidence_ids=["evidence-1"],
        source_tier=SourceTier.PRIMARY_SOURCE,
    )


def test_mock_returns_seeded_search_and_records_call() -> None:
    service = MockCourseRAGService()
    service.seed_search("course-1", [_hit()])
    request = SearchRequest(course_id="course-1", query="启发式")

    response = service.search(request)

    assert [hit.chunk_id for hit in response.hits] == ["chunk-1"]
    assert response.meta.request_id == request.context.request_id
    assert service.calls == [("search", request.context.request_id)]


def test_mock_build_idempotency_replays_and_rejects_conflict() -> None:
    service = MockCourseRAGService()
    context = RequestContext(idempotency_key="build-key")
    first = service.start_build(
        StartBuildRequest(
            context=context,
            course_id="course-1",
            document_ids=["doc-1"],
        )
    )
    replay = service.start_build(
        StartBuildRequest(
            context=RequestContext(
                trace_id=context.trace_id,
                idempotency_key="build-key",
            ),
            course_id="course-1",
            document_ids=["doc-1"],
        )
    )

    assert first.job_id == replay.job_id
    assert first.status == BuildStatus.QUEUED
    with pytest.raises(CourseRAGError) as exc_info:
        service.start_build(
            StartBuildRequest(
                context=RequestContext(idempotency_key="build-key"),
                course_id="course-1",
                document_ids=["doc-2"],
            )
        )
    assert exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


def test_mock_register_idempotency_replays_and_rejects_conflict() -> None:
    service = MockCourseRAGService()
    request = RegisterDocumentRequest(
        context=RequestContext(idempotency_key="register-key"),
        course_id="course-1",
        file=FileReference(
            object_uri="memory://document.pdf",
            filename="document.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            sha256="a" * 64,
        ),
        document_type="textbook",
    )

    first = service.register_document(request)
    replay = service.register_document(
        request.model_copy(
            update={
                "context": RequestContext(
                    request_id="req-register-replay",
                    idempotency_key="register-key",
                )
            }
        )
    )

    assert replay.document == first.document
    assert replay.meta.request_id == "req-register-replay"
    with pytest.raises(CourseRAGError) as exc_info:
        service.register_document(
            request.model_copy(
                update={
                    "context": RequestContext(idempotency_key="register-key"),
                    "course_id": "course-2",
                }
            )
        )
    assert exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT

    other_course = service.register_document(
        request.model_copy(
            update={
                "context": RequestContext(idempotency_key="register-other-course"),
                "course_id": "course-2",
            }
        )
    )
    assert other_course.document.document_id != first.document.document_id


def test_mock_delete_idempotency_replays_first_result_and_rejects_conflict() -> None:
    service = MockCourseRAGService()
    registered = service.register_document(
        RegisterDocumentRequest(
            context=RequestContext(idempotency_key="register-delete-target"),
            course_id="course-1",
            file=FileReference(
                object_uri="memory://delete.pdf",
                filename="delete.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                sha256="b" * 64,
            ),
            document_type="textbook",
        )
    )
    request = DeleteDocumentRequest(
        context=RequestContext(idempotency_key="delete-key"),
        course_id="course-1",
        document_id=registered.document.document_id,
    )

    first = service.delete_document(request)
    replay = service.delete_document(
        request.model_copy(
            update={
                "context": RequestContext(
                    request_id="req-delete-replay",
                    idempotency_key="delete-key",
                )
            }
        )
    )

    assert first.deleted is True
    assert replay.deleted is True
    assert replay.meta.request_id == "req-delete-replay"
    with pytest.raises(CourseRAGError) as exc_info:
        service.delete_document(
            request.model_copy(
                update={
                    "context": RequestContext(idempotency_key="delete-key"),
                    "course_id": "course-2",
                }
            )
        )
    assert exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


def test_mock_revoke_idempotency_replays_and_rejects_conflict() -> None:
    service = MockCourseRAGService()
    write_request = VerifiedContentWriteRequest(
        context=RequestContext(idempotency_key="write-key"),
        course_id="course-1",
        content_type=VerifiedContentType.VERIFIED_QUESTION,
        content={"question": "What is search?"},
        evidence_ids=["evidence-1"],
        approved_by="teacher-1",
        task_id="task-1",
        approval_record_id="approval-1",
    )
    written = service.write_verified_content(write_request)
    write_replay = service.write_verified_content(
        write_request.model_copy(
            update={
                "context": RequestContext(
                    request_id="req-write-replay",
                    idempotency_key="write-key",
                )
            }
        )
    )
    assert write_replay.verified_content_id == written.verified_content_id
    assert write_replay.created is False
    assert write_replay.meta.request_id == "req-write-replay"
    with pytest.raises(CourseRAGError) as write_exc_info:
        service.write_verified_content(
            write_request.model_copy(
                update={
                    "context": RequestContext(idempotency_key="write-key"),
                    "content": {"question": "Different"},
                }
            )
        )
    assert write_exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT

    request = RevokeVerifiedContentRequest(
        context=RequestContext(idempotency_key="revoke-key"),
        course_id="course-1",
        verified_content_id=written.verified_content_id,
        revoked_by="teacher-1",
        reason="incorrect",
    )

    first = service.revoke_verified_content(request)
    replay = service.revoke_verified_content(
        request.model_copy(
            update={
                "context": RequestContext(
                    request_id="req-revoke-replay",
                    idempotency_key="revoke-key",
                )
            }
        )
    )

    assert first.revoked is True
    assert replay.revoked is True
    assert replay.meta.request_id == "req-revoke-replay"
    with pytest.raises(CourseRAGError) as exc_info:
        service.revoke_verified_content(
            request.model_copy(
                update={
                    "context": RequestContext(idempotency_key="revoke-key"),
                    "reason": "different",
                }
            )
        )
    assert exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


def test_mock_supports_one_shot_failure_injection() -> None:
    service = MockCourseRAGService()
    service.fail_next(
        CourseRAGOperation.SEARCH,
        code=ErrorCode.INDEX_NOT_READY,
        message="building",
        retryable=True,
    )
    request = SearchRequest(course_id="course-1", query="query")

    with pytest.raises(CourseRAGError) as exc_info:
        service.search(request)

    assert exc_info.value.code == ErrorCode.INDEX_NOT_READY
    assert exc_info.value.response.error.retryable is True
    assert service.search(request).hits == []
