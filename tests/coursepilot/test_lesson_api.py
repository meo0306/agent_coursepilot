from pathlib import Path

from docx import Document


def _create_course_with_kb(client):
    course = client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()
    document = client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={
            "file": (
                "lesson.txt",
                b"state space search heuristic search goal test path cost classroom case",
            )
        },
        data={"source_type": "textbook"},
    ).json()
    build = client.post(f"/api/coursepilot/documents/{document['id']}/build-kb")
    assert build.status_code == 200
    assert build.json()["parse_status"] == "built"
    return course


def test_lesson_generate_revise_and_export(coursepilot_client):
    course = _create_course_with_kb(coursepilot_client)

    generate = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/lessons/generate",
        json={
            "chapter_range": "Search",
            "total_sessions": 2,
            "session_duration": 45,
            "teaching_template": "standard",
        },
    )

    assert generate.status_code == 200
    payload = generate.json()
    assert payload["status"] == "draft"
    assert payload["lesson_design"]["total_sessions"] == 2
    assert payload["validation_report"]["session_count_valid"] is True
    lesson_id = payload["lesson_id"]

    read = coursepilot_client.get(f"/api/coursepilot/lessons/{lesson_id}")
    assert read.status_code == 200
    assert read.json()["id"] == lesson_id

    revise = coursepilot_client.post(
        f"/api/coursepilot/lessons/{lesson_id}/revise",
        json={
            "target_scope": "第1课时",
            "feedback_text": "Add a life-like case.",
            "keep_unchanged_parts": True,
        },
    )
    assert revise.status_code == 200
    assert "Updated session 1" in revise.json()["modification_summary"]

    export = coursepilot_client.post(f"/api/coursepilot/lessons/{lesson_id}/export")
    assert export.status_code == 200
    export_file = export.json()
    assert export_file["file_role"] == "lesson_docx"
    assert Path(export_file["file_path"]).exists()
    doc = Document(export_file["file_path"])
    assert doc.paragraphs


def test_lesson_generate_requires_kb_context(coursepilot_client):
    course = coursepilot_client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()

    response = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/lessons/generate",
        json={"chapter_range": "Search", "total_sessions": 1, "session_duration": 45},
    )

    assert response.status_code == 400
    assert "Build course documents" in response.json()["detail"]

