from unittest.mock import patch

import pytest
from httpx import Request, Response

from client import AgentClientError, CoursePilotClient


def test_coursepilot_client_wraps_course_api():
    response = Response(
        200,
        json={"id": "course-1", "course_name": "AI"},
        request=Request("POST", "http://test/api/coursepilot/courses"),
    )
    client = CoursePilotClient(base_url="http://test", headers={"Authorization": "Bearer token"})
    with patch("httpx.request", return_value=response) as mocked:
        payload = client.create_course({"course_name": "AI"})

    assert payload["id"] == "course-1"
    _, args, kwargs = mocked.mock_calls[0]
    assert args[:2] == ("POST", "http://test/api/coursepilot/courses")
    assert kwargs["headers"] == {"Authorization": "Bearer token"}
    assert kwargs["json"] == {"course_name": "AI"}


def test_coursepilot_client_upload_document():
    response = Response(
        200,
        json={"id": "doc-1"},
        request=Request("POST", "http://test/api/coursepilot/courses/course-1/documents/upload"),
    )
    client = CoursePilotClient(base_url="http://test")
    with patch("httpx.request", return_value=response) as mocked:
        payload = client.upload_document(
            "course-1",
            filename="lesson.txt",
            content=b"content",
            source_type="textbook",
        )

    assert payload["id"] == "doc-1"
    _, args, kwargs = mocked.mock_calls[0]
    assert args[:2] == ("POST", "http://test/api/coursepilot/courses/course-1/documents/upload")
    assert kwargs["files"] == {"file": ("lesson.txt", b"content")}
    assert kwargs["data"] == {"source_type": "textbook"}


def test_coursepilot_client_sends_idempotency_key_without_losing_auth_header():
    accepted = Response(
        202,
        json={"task_id": "task-1", "status": "pending", "status_url": "/tasks/task-1"},
        request=Request("POST", "http://test/api/coursepilot/documents/doc-1/build-kb"),
    )
    completed = Response(
        200,
        json={
            "task_id": "task-1",
            "status": "completed",
            "result": {"document_id": "doc-1", "parse_status": "built"},
        },
        request=Request("GET", "http://test/api/coursepilot/tasks/task-1"),
    )
    client = CoursePilotClient(
        base_url="http://test",
        headers={"Authorization": "Bearer token"},
    )
    with patch("httpx.request", side_effect=[accepted, completed]) as mocked:
        result = client.build_kb(
            "doc-1",
            timeout=7200,
            idempotency_key="coursepilot-eval:run:build",
        )

    assert result["parse_status"] == "built"
    _, enqueue_args, enqueue_kwargs = mocked.mock_calls[0]
    assert enqueue_args[:2] == (
        "POST",
        "http://test/api/coursepilot/documents/doc-1/build-kb",
    )
    assert enqueue_kwargs["headers"] == {
        "Authorization": "Bearer token",
        "Idempotency-Key": "coursepilot-eval:run:build",
    }
    assert enqueue_kwargs["timeout"] == 30
    _, poll_args, poll_kwargs = mocked.mock_calls[1]
    assert poll_args[:2] == ("GET", "http://test/api/coursepilot/tasks/task-1")
    assert poll_kwargs["headers"] == {"Authorization": "Bearer token"}
    assert poll_kwargs["timeout"] <= 30
    assert poll_kwargs["trust_env"] is False


def test_coursepilot_client_includes_error_detail():
    response = Response(
        400,
        json={"detail": "missing thread_id"},
        request=Request("POST", "http://test/api/coursepilot/courses/course-1/lessons/generate"),
    )
    client = CoursePilotClient(base_url="http://test")

    with patch("httpx.request", return_value=response), pytest.raises(AgentClientError) as exc:
        client.generate_lesson("course-1", {"chapter_range": "Search"})

    assert "missing thread_id" in str(exc.value)
