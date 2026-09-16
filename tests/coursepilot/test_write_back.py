from coursepilot.rag.vector_store import ChromaVectorStore
from tests.coursepilot.task_test_utils import submit_and_complete


def test_rejected_review_does_not_write_to_vector_store(coursepilot_client, monkeypatch):
    calls = []

    def fake_add_verified_texts(self, **kwargs):
        calls.append(kwargs)
        return "coursepilot_test"

    monkeypatch.setattr(ChromaVectorStore, "add_verified_texts", fake_add_verified_texts)

    course = coursepilot_client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()
    missing_target = coursepilot_client.post(
        "/api/coursepilot/reviews",
        json={
            "target_type": "ppt_outline",
            "target_id": course["id"],
            "review_status": "rejected",
        },
    )

    assert missing_target.status_code == 404
    assert calls == []


def _create_course_with_kb(client):
    course = client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()
    document = client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={
            "file": (
                "review.txt",
                b"state space search heuristic search goal test path cost classroom activity",
            )
        },
        data={"source_type": "textbook"},
    ).json()
    submit_and_complete(
        client,
        f"/api/coursepilot/documents/{document['id']}/build-kb",
    )
    return course


def test_legacy_whole_artifacts_require_safe_writeback_selection(coursepilot_client):
    course = _create_course_with_kb(coursepilot_client)

    lesson = submit_and_complete(
        coursepilot_client,
        f"/api/coursepilot/courses/{course['id']}/lessons/generate",
        json={"chapter_range": "Search", "total_sessions": 1, "session_duration": 45},
    )
    lesson_id = lesson["lesson_id"]
    lesson_review = coursepilot_client.post(
        "/api/coursepilot/reviews",
        json={
            "target_type": "lesson_design",
            "target_id": lesson_id,
            "review_status": "approved",
        },
    )
    assert lesson_review.status_code == 200
    lesson_write_back = coursepilot_client.post(
        f"/api/coursepilot/reviews/{lesson_review.json()['id']}/write-back"
    )
    assert lesson_write_back.status_code == 200
    assert lesson_write_back.json()["write_back_status"] == "requires_fragment_selection"
    assert lesson_write_back.json()["written_chunk_ids"] == []

    lesson_search = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/kb/search",
        json={"query": "state space Search", "verified_only": True, "top_k": 10},
    )
    assert lesson_search.status_code == 200
    assert not any(
        result["source_type"] == "reviewed_lesson" for result in lesson_search.json()["results"]
    )

    blueprint = submit_and_complete(
        coursepilot_client,
        f"/api/coursepilot/courses/{course['id']}/exams/blueprint",
        json={"chapter_range": "Search", "question_counts": {"single_choice": 1}},
    )
    blueprint_id = blueprint["blueprint_id"]
    assert (
        coursepilot_client.post(f"/api/coursepilot/exams/{blueprint_id}/confirm").status_code == 200
    )
    submit_and_complete(
        coursepilot_client,
        f"/api/coursepilot/exams/{blueprint_id}/generate",
    )
    question = coursepilot_client.get(f"/api/coursepilot/exams/{blueprint_id}/questions").json()[0]

    question_review = coursepilot_client.post(
        "/api/coursepilot/reviews",
        json={
            "target_type": "question",
            "target_id": question["id"],
            "review_status": "approved",
        },
    )
    assert question_review.status_code == 200
    question_write_back = coursepilot_client.post(
        f"/api/coursepilot/reviews/{question_review.json()['id']}/write-back"
    )
    assert question_write_back.status_code == 200
    assert question_write_back.json()["write_back_status"] == "requires_evidence_migration"
    assert question_write_back.json()["written_chunk_ids"] == []

    question_search = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/kb/search",
        json={"query": question["question_text"], "verified_only": True, "top_k": 10},
    )
    assert question_search.status_code == 200
    assert not any(
        result["source_type"] == "reviewed_question" for result in question_search.json()["results"]
    )
