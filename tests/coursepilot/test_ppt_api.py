from pathlib import Path

from pptx import Presentation

import coursepilot.services.ppt_service as ppt_service_module
from core import settings
from coursepilot.schemas.ppt_schema import SlideValidationReport
from tests.coursepilot.task_test_utils import submit_and_complete


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
    submit_and_complete(
        client,
        f"/api/coursepilot/documents/{document['id']}/build-kb",
    )

    lesson = submit_and_complete(
        client,
        f"/api/coursepilot/courses/{course['id']}/lessons/generate",
        json={
            "chapter_range": "Search",
            "total_sessions": 2,
            "session_duration": 45,
            "teaching_template": "standard",
        },
    )
    return course, lesson["lesson_id"]


def test_ppt_generate_export_review_and_write_back(coursepilot_client, monkeypatch):
    course, lesson_id = _create_course_with_lesson(coursepilot_client)

    payload = submit_and_complete(
        coursepilot_client,
        f"/api/coursepilot/lessons/{lesson_id}/ppt/generate",
        json={"slide_count": 6, "style_template": "standard", "include_references": True},
    )
    outline_id = payload["outline_id"]
    assert payload["validation_report"]["slide_count_valid"] is True
    assert payload["validation_report"]["source_session_valid"] is True
    assert payload["validation_report"]["citation_present"] is True
    assert payload["validation_report"]["citation_grounded"] is True
    assert payload["validation_report"]["citation_valid"] is True
    assert len(payload["outline"]["slides"]) == 6

    read = coursepilot_client.get(f"/api/coursepilot/ppt/{outline_id}")
    assert read.status_code == 200
    assert read.json()["id"] == outline_id

    class FailingAgent:
        def invoke(self, *_args, **_kwargs):
            raise AssertionError("PPT export should not invoke the graph")

    monkeypatch.setattr(ppt_service_module, "coursepilot_ppt_agent", FailingAgent())

    export = coursepilot_client.post(f"/api/coursepilot/ppt/{outline_id}/export")
    assert export.status_code == 200
    export_payload = export.json()
    assert export_payload["file_role"] == "pptx"
    assert "ppt_outline" in export_payload["file_name"]
    assert outline_id not in export_payload["file_name"]
    assert Path(export_payload["file_path"]).exists()
    presentation = Presentation(export_payload["file_path"])
    assert len(presentation.slides) == 6
    exported_outline = coursepilot_client.get(f"/api/coursepilot/ppt/{outline_id}").json()
    assert exported_outline["status"] == "draft"
    assert exported_outline["validation_report_json"]["source_session_valid"] is True
    assert exported_outline["validation_report_json"]["citation_present"] is True
    assert exported_outline["validation_report_json"]["citation_grounded"] is True

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


def test_ppt_export_rejects_invalid_outline_without_writing_file(coursepilot_client, monkeypatch):
    course, lesson_id = _create_course_with_lesson(coursepilot_client)

    generated = submit_and_complete(
        coursepilot_client,
        f"/api/coursepilot/lessons/{lesson_id}/ppt/generate",
        json={"slide_count": 6, "style_template": "standard", "include_references": True},
    )
    outline_id = generated["outline_id"]

    def fail_validation(self, outline, **_kwargs):
        return SlideValidationReport(
            slide_count_valid=False,
            slide_type_valid=True,
            content_not_empty=True,
            source_session_valid=True,
            citation_present=True,
            citation_grounded=True,
            citation_valid=True,
            errors=["forced failure"],
        )

    monkeypatch.setattr(ppt_service_module.PPTValidator, "validate", fail_validation)

    export = coursepilot_client.post(f"/api/coursepilot/ppt/{outline_id}/export")
    assert export.status_code == 400
    assert "validation failed" in export.json()["detail"]

    export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / course["id"]
    assert not list(export_dir.glob("*.pptx"))

    read = coursepilot_client.get(f"/api/coursepilot/ppt/{outline_id}")
    assert read.status_code == 200
    assert read.json()["status"] == "needs_review"
