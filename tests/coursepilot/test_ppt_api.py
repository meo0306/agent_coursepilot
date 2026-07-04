from pathlib import Path

from pptx import Presentation


def _create_course_with_lesson(client):
    course = client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()
    document = client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={
            "file": (
                "ppt.txt",
                b"state space search heuristic search goal test path cost classroom activity",
            )
        },
        data={"source_type": "textbook"},
    ).json()
    build = client.post(f"/api/coursepilot/documents/{document['id']}/build-kb")
    assert build.status_code == 200

    lesson = client.post(
        f"/api/coursepilot/courses/{course['id']}/lessons/generate",
        json={
            "chapter_range": "Search",
            "total_sessions": 2,
            "session_duration": 45,
            "teaching_template": "standard",
        },
    )
    assert lesson.status_code == 200
    return course, lesson.json()["lesson_id"]


def test_ppt_generate_export_review_and_write_back(coursepilot_client):
    course, lesson_id = _create_course_with_lesson(coursepilot_client)

    generated = coursepilot_client.post(
        f"/api/coursepilot/lessons/{lesson_id}/ppt/generate",
        json={"slide_count": 6, "style_template": "standard", "include_references": True},
    )
    assert generated.status_code == 200
    payload = generated.json()
    outline_id = payload["outline_id"]
    assert payload["validation_report"]["slide_count_valid"] is True
    assert payload["validation_report"]["citation_valid"] is True
    assert len(payload["outline"]["slides"]) == 6

    read = coursepilot_client.get(f"/api/coursepilot/ppt/{outline_id}")
    assert read.status_code == 200
    assert read.json()["id"] == outline_id

    export = coursepilot_client.post(f"/api/coursepilot/ppt/{outline_id}/export")
    assert export.status_code == 200
    export_payload = export.json()
    assert export_payload["file_role"] == "pptx"
    assert Path(export_payload["file_path"]).exists()
    presentation = Presentation(export_payload["file_path"])
    assert len(presentation.slides) == 6

    rejected = coursepilot_client.post(
        "/api/coursepilot/reviews",
        json={
            "target_type": "ppt_outline",
            "target_id": outline_id,
            "review_status": "rejected",
            "comment": "Needs revision.",
        },
    )
    assert rejected.status_code == 200
    rejected_write_back = coursepilot_client.post(
        f"/api/coursepilot/reviews/{rejected.json()['id']}/write-back"
    )
    assert rejected_write_back.status_code == 200
    assert rejected_write_back.json()["write_back_status"] == "skipped"

    approved = coursepilot_client.post(
        "/api/coursepilot/reviews",
        json={
            "target_type": "ppt_outline",
            "target_id": outline_id,
            "review_status": "approved",
            "comment": "Approved.",
        },
    )
    assert approved.status_code == 200
    write_back = coursepilot_client.post(
        f"/api/coursepilot/reviews/{approved.json()['id']}/write-back"
    )
    assert write_back.status_code == 200
    write_back_payload = write_back.json()
    assert write_back_payload["write_back_status"] == "written"
    assert write_back_payload["written_chunk_ids"]

    search = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/kb/search",
        json={"query": "Session Objectives Search", "verified_only": True, "top_k": 5},
    )
    assert search.status_code == 200
    results = search.json()["results"]
    assert results
    assert all(result["verified"] is True for result in results)
    assert any(result["source_type"] == "reviewed_ppt" for result in results)


def test_ppt_generate_requires_lesson(coursepilot_client):
    response = coursepilot_client.post(
        "/api/coursepilot/lessons/missing/ppt/generate",
        json={"slide_count": 6},
    )

    assert response.status_code == 404
