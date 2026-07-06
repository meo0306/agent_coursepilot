from httpx import Request, Response
from unittest.mock import patch

from client import CoursePilotClient


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
