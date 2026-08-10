import pytest

from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from courserag.contracts import (
    AnswerStatus,
    ContextPackage,
    ContextRequest,
    CourseRAGError,
    ErrorCode,
    PackingReport,
    QARequest,
    QAResponse,
    ResponseMeta,
)


def _context_response(request: ContextRequest) -> ContextPackage:
    return ContextPackage(
        meta=ResponseMeta.from_context(request.context),
        query=request.query,
        purpose=request.purpose,
        token_count=0,
        retrieval_trace_id="run",
        index_version="index",
        packing_report=PackingReport(
            candidate_count=0,
            selected_count=0,
            deduplicated_count=0,
            discarded_for_budget=0,
        ),
    )


def _qa_response(request: QARequest) -> QAResponse:
    return QAResponse(
        meta=ResponseMeta.from_context(request.context),
        question=request.question,
        answer_status=AnswerStatus.ABSTAINED_INSUFFICIENT_EVIDENCE,
    )


def test_versioned_adapter_exposes_context_and_qa_callbacks() -> None:
    adapter = LocalCourseRAGAdapter(
        retrieval_backend="versioned",
        versioned_context=_context_response,
        versioned_answer=_qa_response,
    )
    context = adapter.build_context(
        ContextRequest(course_id="course", query="question", purpose="question_answering")
    )
    answer = adapter.answer(QARequest(course_id="course", question="question"))
    assert context.index_version == "index"
    assert answer.answer_status == AnswerStatus.ABSTAINED_INSUFFICIENT_EVIDENCE


def test_versioned_adapter_fails_closed_without_runtime() -> None:
    adapter = LocalCourseRAGAdapter(retrieval_backend="versioned")
    with pytest.raises(CourseRAGError) as context_error:
        adapter.build_context(
            ContextRequest(course_id="course", query="question", purpose="question_answering")
        )
    assert context_error.value.code == ErrorCode.INDEX_NOT_READY
    with pytest.raises(CourseRAGError) as qa_error:
        adapter.answer(QARequest(course_id="course", question="question"))
    assert qa_error.value.code == ErrorCode.FEATURE_NOT_AVAILABLE


def test_stable_p09_routes_are_mounted() -> None:
    from service.service import app

    paths = {route.path for route in app.routes}
    assert "/api/courserag/v1/knowledge-bases/{course_id}/search" in paths
    assert "/api/courserag/v1/knowledge-bases/{course_id}/contexts" in paths
    assert "/api/courserag/v1/knowledge-bases/{course_id}/qa" in paths
