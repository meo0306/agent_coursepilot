import pytest

from agents.coursepilot.nodes import retrieve_nodes
from coursepilot.adapters.mock_courserag import MockCourseRAGService
from coursepilot.services.courserag_runtime import override_courserag_service
from courserag.contracts import (
    ScoreBreakdown,
    SearchHit,
    SourceTier,
)


def test_retrieve_course_context_fails_fast_for_empty_lesson_context():
    service = MockCourseRAGService()
    with override_courserag_service(service):
        with pytest.raises(ValueError, match="lesson design"):
            retrieve_nodes.retrieve_course_context(
                {
                    "course_id": "course-1",
                    "lesson_params": {"chapter_range": "Search"},
                }
            )

    assert [call[0] for call in service.calls] == ["search"]


def test_retrieve_course_context_fails_fast_for_empty_exam_context():
    service = MockCourseRAGService()
    with override_courserag_service(service):
        with pytest.raises(ValueError, match="exam"):
            retrieve_nodes.retrieve_course_context(
                {
                    "course_id": "course-1",
                    "workflow_phase": "blueprint",
                    "exam_params": {"chapter_range": "Search"},
                }
            )

    assert [call[0] for call in service.calls] == ["search"]


def test_retrieve_course_context_reuses_existing_contexts():
    service = MockCourseRAGService()
    existing_contexts = [{"chunk_id": "chunk-1", "content": "state space search"}]

    with override_courserag_service(service):
        result = retrieve_nodes.retrieve_course_context(
            {
                "course_id": "course-1",
                "lesson_params": {"chapter_range": "Search"},
                "retrieved_contexts": existing_contexts,
            }
        )

    assert result == {"retrieved_contexts": existing_contexts}
    assert service.calls == []


def test_retrieve_course_context_maps_mock_hit_to_legacy_graph_state():
    service = MockCourseRAGService()
    service.seed_search(
        "course-1",
        [
            SearchHit(
                rank=1,
                chunk_id="chunk-1",
                document_id="doc-1",
                document_version="v1",
                document_type="textbook",
                section_path=["第1章", "1.1"],
                page_start=2,
                page_end=2,
                title="搜索",
                text="启发式搜索",
                scores=ScoreBreakdown(dense=0.9),
                evidence_ids=["evidence-1"],
                source_tier=SourceTier.PRIMARY_SOURCE,
            )
        ],
    )

    with override_courserag_service(service):
        result = retrieve_nodes.retrieve_course_context(
            {
                "course_id": "course-1",
                "lesson_params": {"chapter_range": "Search"},
            }
        )

    assert result["retrieved_contexts"][0] == {
        "chunk_id": "chunk-1",
        "course_id": "course-1",
        "document_id": "doc-1",
        "source_type": "textbook",
        "chapter": "第1章",
        "section": "1.1",
        "page": 2,
        "title": "搜索",
        "content": "启发式搜索",
        "score": 0.9,
        "verified": False,
    }
