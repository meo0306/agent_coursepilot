from __future__ import annotations

import json

import httpx
import pytest

from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.adapters.mock_courserag import MockCourseRAGService
from coursepilot.application.feasibility_service import LessonDemandBuilder
from coursepilot.application.generation_context_service import (
    adequacy_report_to_snapshot,
    artifact_demand_to_generation_context_request,
)
from coursepilot.clients.remote_courserag import RemoteCourseRAGClient
from coursepilot.schemas.lesson_schema import LessonGenerationParams
from courserag.api.http_schema import knowledge_base_generation_contexts_path
from courserag.contracts import (
    ContextAdequacyReport,
    ContextAdequacyStatus,
    ContextItem,
    ContextPackage,
    CourseRAGError,
    ErrorCode,
    GenerationArtifactType,
    GenerationContextRequest,
    GenerationContextRequirements,
    GenerationContextResponse,
    PackingReport,
    RequestContext,
    ResponseMeta,
)


def _request() -> GenerationContextRequest:
    return GenerationContextRequest(
        context=RequestContext(request_id="req-gc", trace_id="trace-gc"),
        course_id="course-1",
        query="chapter",
        requirements=GenerationContextRequirements(
            artifact_type=GenerationArtifactType.LESSON,
            target_unit_count=1,
            minimum_distinct_sources=1,
            minimum_semantic_units=1,
        ),
    )


def _response(request: GenerationContextRequest) -> GenerationContextResponse:
    context = ContextPackage(
        meta=ResponseMeta.from_context(request.context),
        query=request.query,
        purpose="generation:lesson",
        items=[
            ContextItem(context_item_id="ctx-1", text="text", evidence_ids=["e-1"], token_count=1)
        ],
        token_count=1,
        retrieval_trace_id="retrieval-1",
        index_version="index-1",
        packing_report=PackingReport(
            candidate_count=1,
            selected_count=1,
            selected_evidence_count=1,
            deduplicated_count=0,
            discarded_for_budget=0,
            token_budget=4000,
            token_count=1,
        ),
    )
    report = ContextAdequacyReport(
        status=ContextAdequacyStatus.UNRESOLVABLE,
        reason_codes=["semantic_unit_capacity_insufficient", "adequacy_unresolvable"],
        evidence_count=1,
        distinct_semantic_units=1,
        distinct_sources=0,
        complete_evidence_group_count=1,
        incomplete_evidence_group_count=0,
        selected_item_count=1,
        selected_evidence_count=1,
        token_count=1,
        token_budget=4000,
        discarded_for_budget=0,
        discarded_for_item_limit=0,
        discarded_for_token_limit=0,
        parent_expansion_count=0,
        neighbor_expansion_count=0,
        missing_requirement_ids=["minimum_semantic_units"],
        supported_target_unit_count=0,
        supplement_allowed=False,
    )
    return GenerationContextResponse(
        meta=ResponseMeta.from_context(request.context), context=context, adequacy=report
    )


def test_artifact_demand_maps_without_losing_requirement_identity() -> None:
    demand = LessonDemandBuilder.build(
        course_id="course-1",
        params=LessonGenerationParams(chapter_range="chapter", total_sessions=2),
    )
    request = artifact_demand_to_generation_context_request(
        demand, context=RequestContext(request_id="req-map", trace_id="trace-map")
    )
    assert request.course_id == demand.course_id
    assert request.requirements.target_unit_count == demand.target_unit_count
    assert [item.requirement_id for item in request.requirements.semantic_requirements] == [
        item.requirement_id
        for item in sorted(demand.semantic_requirements, key=lambda value: value.requirement_id)
    ]


def test_report_maps_to_ep01_snapshot_without_recalculation() -> None:
    report = _response(_request()).adequacy
    snapshot = adequacy_report_to_snapshot(report)
    assert snapshot.status.value == "unresolvable"
    assert snapshot.supported_target_unit_count == 0
    assert snapshot.distinct_semantic_units == 1


def test_local_adapter_requires_explicit_generation_callback_without_fallback() -> None:
    request = _request()
    legacy_called = False

    def legacy_context(_):
        nonlocal legacy_called
        legacy_called = True
        raise AssertionError("legacy context must not be called")

    adapter = LocalCourseRAGAdapter(retrieval_backend="versioned", versioned_context=legacy_context)
    with pytest.raises(CourseRAGError) as exc_info:
        adapter.build_generation_context(request)
    assert exc_info.value.code is ErrorCode.FEATURE_NOT_AVAILABLE
    assert legacy_called is False
    assert "build_generation_context" not in {
        operation.value for operation in adapter.capabilities().supported_operations
    }


def test_local_and_mock_declare_v1_when_generation_is_supported() -> None:
    request = _request()
    response = _response(request)
    local = LocalCourseRAGAdapter(versioned_generation_context=lambda _: response)
    assert local.build_generation_context(request) == response
    assert local.capabilities().supported_generation_context_versions == ["v1"]

    mock = MockCourseRAGService()
    mock.seed_generation_context("course-1", response)
    assert mock.build_generation_context(request).adequacy.status.value == "unresolvable"
    assert mock.capabilities().supported_generation_context_versions == ["v1"]


def test_remote_uses_versioned_generation_context_path_and_correlation() -> None:
    request = _request()
    response = _response(request)

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url.path == knowledge_base_generation_contexts_path("course-1")
        assert json.loads(http_request.content)["requirements"]["contract_version"] == "v1"
        return httpx.Response(200, json=response.model_dump(mode="json"))

    with httpx.Client(
        base_url="https://courserag.invalid", transport=httpx.MockTransport(handler)
    ) as client:
        result = RemoteCourseRAGClient(client).build_generation_context(request)
    assert result.adequacy.status is ContextAdequacyStatus.UNRESOLVABLE
