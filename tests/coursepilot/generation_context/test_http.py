from __future__ import annotations

from fastapi.testclient import TestClient

from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.adapters.mock_courserag import MockCourseRAGService
from coursepilot.services.courserag_runtime import override_courserag_service
from courserag.api.http_schema import knowledge_base_generation_contexts_path
from courserag.contracts import (
    GenerationArtifactType,
    GenerationContextRequest,
    GenerationContextRequirements,
    RequestContext,
)


def test_generation_context_openapi_and_unresolvable_is_http_200(
    coursepilot_client: TestClient,
) -> None:
    request = GenerationContextRequest(
        context=RequestContext(request_id="req-http-gc", trace_id="trace-http-gc"),
        course_id="course-1",
        query="chapter",
        requirements=GenerationContextRequirements(
            artifact_type=GenerationArtifactType.LESSON,
            target_unit_count=1,
            minimum_distinct_sources=1,
            minimum_semantic_units=1,
            max_supplement_rounds=0,
        ),
    )
    service = MockCourseRAGService()
    headers = {
        "X-Request-ID": request.context.request_id,
        "X-Trace-ID": request.context.trace_id,
        "X-CoursePilot-Principal-ID": "coursepilot-test",
        "X-CoursePilot-Course-ID": "course-1",
        "X-CoursePilot-Roles": "reader",
    }
    with override_courserag_service(service):
        response = coursepilot_client.post(
            knowledge_base_generation_contexts_path("course-1"),
            json=request.model_dump(mode="json"),
            headers=headers,
        )
        capabilities = coursepilot_client.get("/api/courserag/v1/capabilities", headers=headers)

    assert response.status_code == 200
    assert response.json()["adequacy"]["status"] == "unresolvable"
    assert response.json()["meta"]["request_id"] == "req-http-gc"
    assert capabilities.status_code == 200
    assert "build_generation_context" in capabilities.json()["supported_operations"]
    assert capabilities.json()["supported_generation_context_versions"] == ["v1"]
    assert (
        knowledge_base_generation_contexts_path("{course_id}").replace(
            "%7Bcourse_id%7D", "{course_id}"
        )
        in coursepilot_client.app.openapi()["paths"]
    )


def test_generation_context_capability_absence_is_http_501(
    coursepilot_client: TestClient,
) -> None:
    request = GenerationContextRequest(
        context=RequestContext(request_id="req-http-missing", trace_id="trace-http-missing"),
        course_id="course-1",
        query="chapter",
        requirements=GenerationContextRequirements(
            artifact_type=GenerationArtifactType.LESSON,
            target_unit_count=1,
            minimum_distinct_sources=1,
            minimum_semantic_units=1,
        ),
    )
    service = LocalCourseRAGAdapter(retrieval_backend="versioned")
    headers = {
        "X-CoursePilot-Principal-ID": "coursepilot-test",
        "X-CoursePilot-Course-ID": "course-1",
        "X-CoursePilot-Roles": "reader",
    }
    with override_courserag_service(service):
        response = coursepilot_client.post(
            knowledge_base_generation_contexts_path("course-1"),
            json=request.model_dump(mode="json"),
            headers=headers,
        )
        capabilities = coursepilot_client.get("/api/courserag/v1/capabilities", headers=headers)

    assert response.status_code == 501
    assert response.json()["error"]["code"] == "FEATURE_NOT_AVAILABLE"
    assert "build_generation_context" not in capabilities.json()["supported_operations"]
    assert capabilities.json()["supported_generation_context_versions"] == []
