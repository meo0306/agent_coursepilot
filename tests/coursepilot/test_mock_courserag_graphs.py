from agents.coursepilot.graphs.exam_graph import coursepilot_exam_agent
from agents.coursepilot.graphs.lesson_graph import coursepilot_lesson_agent
from agents.coursepilot.graphs.ppt_graph import coursepilot_ppt_agent
from coursepilot.adapters.mock_courserag import MockCourseRAGService
from coursepilot.services.courserag_runtime import override_courserag_service
from courserag.contracts import ScoreBreakdown, SearchHit, SourceTier


def _service() -> MockCourseRAGService:
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
                section_path=["Search"],
                text="state space search heuristic search path cost",
                scores=ScoreBreakdown(dense=0.9),
                evidence_ids=[],
                source_tier=SourceTier.PRIMARY_SOURCE,
            )
        ],
    )
    return service


def test_lesson_graph_uses_mock_courserag_search() -> None:
    service = _service()

    with override_courserag_service(service):
        result = coursepilot_lesson_agent.invoke(
            {
                "course_id": "course-1",
                "lesson_params": {
                    "course_name": "AI",
                    "chapter_range": "Search",
                    "total_sessions": 1,
                    "session_duration": 45,
                },
            }
        )

    assert result["lesson_design"]["total_sessions"] == 1
    assert result["retrieved_contexts"][0]["chunk_id"] == "chunk-1"
    assert [call[0] for call in service.calls] == ["search"]


def test_exam_graph_uses_mock_courserag_search() -> None:
    service = _service()

    with override_courserag_service(service):
        result = coursepilot_exam_agent.invoke(
            {
                "course_id": "course-1",
                "exam_params": {
                    "course_name": "AI",
                    "chapter_range": "Search",
                    "generation_type": "exam",
                    "question_counts": {
                        "single_choice": 1,
                        "multiple_choice": 1,
                        "judgement": 1,
                        "short_answer": 1,
                    },
                    "score_per_question": {
                        "single_choice": 2,
                        "multiple_choice": 3,
                        "judgement": 1,
                        "short_answer": 10,
                    },
                },
            }
        )

    assert result["exam_blueprint"]["total_score"] == 16
    assert result["retrieved_contexts"][0]["chunk_id"] == "chunk-1"
    assert [call[0] for call in service.calls] == ["search"]


def test_ppt_graph_remains_independent_of_retrieval_port() -> None:
    service = _service()
    lesson_design = {
        "course_name": "AI",
        "chapter": "Search",
        "total_sessions": 1,
        "session_duration": 45,
        "knowledge_points": ["state space", "heuristic"],
        "session_plan": [
            {
                "session_index": 1,
                "session_title": "Search",
                "duration": 45,
                "knowledge_points": ["state space", "heuristic"],
                "teaching_focus": "search",
                "time_allocation": [
                    {"activity": "Intro", "minutes": 5},
                    {"activity": "Lecture", "minutes": 30},
                    {"activity": "Practice", "minutes": 5},
                    {"activity": "Summary", "minutes": 5},
                ],
            }
        ],
        "sessions": [
            {
                "session_index": 1,
                "session_title": "Search",
                "teaching_objectives": ["Explain state space"],
                "key_points": ["state space"],
                "teaching_process": [{"stage": "Intro", "minutes": 5, "content": "case"}],
                "references": [{"chunk_id": "chunk-1", "source_type": "textbook"}],
            }
        ],
    }

    with override_courserag_service(service):
        result = coursepilot_ppt_agent.invoke(
            {
                "ppt_params": {"lesson_id": "lesson-1", "slide_count": 4},
                "lesson_design": lesson_design,
            }
        )

    assert len(result["slide_outline"]["slides"]) == 4
    assert service.calls == []
