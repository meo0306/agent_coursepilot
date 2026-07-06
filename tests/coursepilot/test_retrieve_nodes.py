import pytest

from agents.coursepilot.nodes import retrieve_nodes


def test_retrieve_course_context_fails_fast_for_empty_lesson_context(monkeypatch):
    calls = []

    class EmptyRetriever:
        def search(self, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(retrieve_nodes, "CoursePilotRetriever", EmptyRetriever)

    with pytest.raises(ValueError, match="lesson design"):
        retrieve_nodes.retrieve_course_context(
            {
                "course_id": "course-1",
                "lesson_params": {"chapter_range": "Search"},
            }
        )

    assert calls == [{"course_id": "course-1", "query": "Search", "top_k": 8}]


def test_retrieve_course_context_fails_fast_for_empty_exam_context(monkeypatch):
    calls = []

    class EmptyRetriever:
        def search(self, **kwargs):
            calls.append(kwargs)
            return []

    monkeypatch.setattr(retrieve_nodes, "CoursePilotRetriever", EmptyRetriever)

    with pytest.raises(ValueError, match="exam"):
        retrieve_nodes.retrieve_course_context(
            {
                "course_id": "course-1",
                "workflow_phase": "blueprint",
                "exam_params": {"chapter_range": "Search"},
            }
        )

    assert calls == [{"course_id": "course-1", "query": "Search", "top_k": 8}]


def test_retrieve_course_context_reuses_existing_contexts(monkeypatch):
    class FailingRetriever:
        def search(self, **kwargs):
            raise AssertionError("search should not run when retrieved_contexts are present")

    monkeypatch.setattr(retrieve_nodes, "CoursePilotRetriever", FailingRetriever)
    existing_contexts = [{"chunk_id": "chunk-1", "content": "state space search"}]

    result = retrieve_nodes.retrieve_course_context(
        {
            "course_id": "course-1",
            "lesson_params": {"chapter_range": "Search"},
            "retrieved_contexts": existing_contexts,
        }
    )

    assert result == {"retrieved_contexts": existing_contexts}
