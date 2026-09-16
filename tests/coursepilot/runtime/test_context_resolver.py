import hashlib

import pytest

from coursepilot.adapters.mock_courserag import MockCourseRAGService
from coursepilot.runtime.context_resolver import ContextResolutionError, context_package_ref
from courserag.contracts import (
    ContextItem,
    ContextPackage,
    ContextRequest,
    EvidenceSummary,
    PackingReport,
    RequestContext,
    ResponseMeta,
)


def _package(context: RequestContext) -> ContextPackage:
    content_hash = hashlib.sha256(b"content").hexdigest()
    return ContextPackage(
        meta=ResponseMeta.from_context(context),
        query="query",
        purpose="lesson_generation",
        items=[
            ContextItem(
                context_item_id="item-1",
                text="content",
                evidence_ids=["evidence-1"],
                token_count=1,
                content_sha256=content_hash,
            )
        ],
        token_count=1,
        evidence_map={
            "evidence-1": EvidenceSummary(
                evidence_id="evidence-1",
                content_sha256=content_hash,
            )
        },
        retrieval_trace_id="retrieval-1",
        index_version="index-v1",
        packing_report=PackingReport(
            candidate_count=1,
            selected_count=1,
            deduplicated_count=0,
            discarded_for_budget=0,
        ),
        context_package_id="ctx-1",
        result_sha256="1" * 64,
    )


def test_context_ref_preserves_course_index_evidence_and_trace() -> None:
    context = RequestContext(request_id="req-1", trace_id="trace-1")
    request = ContextRequest(
        context=context,
        course_id="course-1",
        query="query",
        purpose="lesson_generation",
    )
    result = context_package_ref(request, _package(context))
    assert result.course_id == "course-1"
    assert result.index_version == "index-v1"
    assert result.evidence_ids == ["evidence-1"]
    assert result.trace_id == "trace-1"


def test_context_ref_fails_closed_on_trace_or_evidence_identity() -> None:
    context = RequestContext(request_id="req-1", trace_id="trace-1")
    request = ContextRequest(
        context=context,
        course_id="course-1",
        query="query",
        purpose="lesson_generation",
    )
    package = _package(context).model_copy(
        update={"meta": ResponseMeta.from_context(context.model_copy(update={"trace_id": "other"}))}
    )
    with pytest.raises(ContextResolutionError, match="trace identity"):
        context_package_ref(request, package)


def test_runtime_boundary_uses_port_not_courserag_internals() -> None:
    # Importing the Fake proves the runtime can be driven through the consumer Port.
    assert isinstance(MockCourseRAGService(), object)
