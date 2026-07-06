from pathlib import Path

from docx import Document


def _create_course_with_kb(client):
    course = client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()
    document = client.post(
        f"/api/coursepilot/courses/{course['id']}/documents/upload",
        files={
            "file": (
                "exam.txt",
                b"state space search heuristic search goal test path cost admissible heuristic graph search",
            )
        },
        data={"source_type": "textbook"},
    ).json()
    build = client.post(f"/api/coursepilot/documents/{document['id']}/build-kb")
    assert build.status_code == 200
    assert build.json()["parse_status"] == "built"
    return course


def test_exam_blueprint_generate_questions_and_export(coursepilot_client):
    course = _create_course_with_kb(coursepilot_client)

    blueprint = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/exams/blueprint",
        json={
            "chapter_range": "Search",
            "generation_type": "exam",
            "question_counts": {
                "single_choice": 2,
                "multiple_choice": 1,
                "judgement": 1,
                "short_answer": 1,
            },
            "score_per_question": {
                "single_choice": 2,
                "multiple_choice": 4,
                "judgement": 1,
                "short_answer": 10,
            },
        },
    )

    assert blueprint.status_code == 200
    blueprint_payload = blueprint.json()
    blueprint_id = blueprint_payload["blueprint_id"]
    assert blueprint_payload["status"] == "draft"
    assert blueprint_payload["blueprint"]["total_score"] == 19

    confirm = coursepilot_client.post(f"/api/coursepilot/exams/{blueprint_id}/confirm")
    assert confirm.status_code == 200
    assert confirm.json()["status"] == "confirmed"

    generated = coursepilot_client.post(f"/api/coursepilot/exams/{blueprint_id}/generate")
    assert generated.status_code == 200
    generated_payload = generated.json()
    assert generated_payload["validation_report"]["question_count_valid"] is True
    assert generated_payload["validation_report"]["score_valid"] is True
    assert len(generated_payload["questions"]) == 5

    questions = coursepilot_client.get(f"/api/coursepilot/exams/{blueprint_id}/questions")
    assert questions.status_code == 200
    assert len(questions.json()) == 5

    export = coursepilot_client.post(f"/api/coursepilot/exams/{blueprint_id}/export")
    assert export.status_code == 200
    files = export.json()["files"]
    assert {item["file_role"] for item in files} == {
        "student_exam",
        "teacher_answer",
        "detailed_explanation",
        "answer_sheet",
    }

    student_file = next(item for item in files if item["file_role"] == "student_exam")
    assert Path(student_file["file_path"]).exists()
    student_text = "\n".join(paragraph.text for paragraph in Document(student_file["file_path"]).paragraphs)
    assert "Answer: __________________" in student_text
    assert "Explanation:" not in student_text
    assert "Answer: A" not in student_text


def test_exam_blueprint_requires_kb_context(coursepilot_client):
    course = coursepilot_client.post("/api/coursepilot/courses", json={"course_name": "AI"}).json()

    response = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/exams/blueprint",
        json={"chapter_range": "Search"},
    )

    assert response.status_code == 400
    assert "Build course documents" in response.json()["detail"]


def test_exam_questions_require_confirmed_blueprint(coursepilot_client):
    course = _create_course_with_kb(coursepilot_client)

    blueprint = coursepilot_client.post(
        f"/api/coursepilot/courses/{course['id']}/exams/blueprint",
        json={"chapter_range": "Search"},
    )
    assert blueprint.status_code == 200
    blueprint_id = blueprint.json()["blueprint_id"]

    generated = coursepilot_client.post(f"/api/coursepilot/exams/{blueprint_id}/generate")

    assert generated.status_code == 409
    assert "must be confirmed" in generated.json()["detail"]
