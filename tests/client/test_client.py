from unittest.mock import patch

import pytest
from httpx import Request, Response

from client import AgentClient, AgentClientError
from client.coursepilot_client import CoursePilotClient
from schema import AgentInfo, ChatHistory, ChatMessage, ServiceMetadata
from schema.models import FakeModelName

INFO = ServiceMetadata(
    agents=[
        AgentInfo(key="coursepilot-lesson-agent", description="Lesson"),
        AgentInfo(key="coursepilot-exam-agent", description="Exam"),
        AgentInfo(key="coursepilot-ppt-agent", description="PPT"),
    ],
    models=[FakeModelName.FAKE],
    default_agent="coursepilot-lesson-agent",
    default_model=FakeModelName.FAKE,
)


def _response(status_code: int, json_data, method: str, url: str) -> Response:
    return Response(status_code, json=json_data, request=Request(method, url))


def test_retrieve_info_sets_default_agent():
    with patch(
        "httpx.get",
        return_value=_response(200, INFO.model_dump(mode="json"), "GET", "http://test/info"),
    ):
        client = AgentClient(base_url="http://test")

    assert client.info == INFO
    assert client.agent == "coursepilot-lesson-agent"


def test_update_agent_validates_available_agent():
    client = AgentClient(base_url="http://test", get_info=False)
    client.info = INFO

    client.update_agent("coursepilot-exam-agent")

    assert client.agent == "coursepilot-exam-agent"


def test_update_agent_rejects_unknown_agent():
    client = AgentClient(base_url="http://test", get_info=False)
    client.info = INFO

    with pytest.raises(AgentClientError, match="Agent missing not found"):
        client.update_agent("missing")


def test_invoke_posts_to_selected_coursepilot_agent():
    response = _response(
        200,
        ChatMessage(type="ai", content="Use /api/coursepilot/*").model_dump(mode="json"),
        "POST",
        "http://test/coursepilot-lesson-agent/invoke",
    )
    client = AgentClient(base_url="http://test", get_info=False)
    client.update_agent("coursepilot-lesson-agent", verify=False)

    with patch("httpx.post", return_value=response) as mocked:
        message = client.invoke("hello", thread_id="thread-1")

    assert message.content == "Use /api/coursepilot/*"
    _, args, kwargs = mocked.mock_calls[0]
    assert args[0] == "http://test/coursepilot-lesson-agent/invoke"
    assert kwargs["json"]["message"] == "hello"
    assert kwargs["json"]["thread_id"] == "thread-1"


@pytest.mark.asyncio
async def test_ainvoke_wraps_http_errors():
    client = AgentClient(base_url="http://test", get_info=False)
    client.update_agent("coursepilot-lesson-agent", verify=False)

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, *args, **kwargs):
            return _response(500, {"detail": "boom"}, "POST", "http://test/invoke")

    with patch("httpx.AsyncClient", return_value=FakeAsyncClient()):
        with pytest.raises(AgentClientError, match="Error:"):
            await client.ainvoke("hello")


def test_stream_parses_message_events():
    client = AgentClient(base_url="http://test", get_info=False)
    client.update_agent("coursepilot-lesson-agent", verify=False)
    lines = [
        'data: {"type": "message", "content": {"type": "ai", "content": "hello"}}',
        "data: [DONE]",
    ]

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(lines)

    with patch("httpx.stream", return_value=FakeStream()):
        messages = list(client.stream("hello"))

    assert messages == [ChatMessage(type="ai", content="hello")]


def test_get_history():
    history = ChatHistory(messages=[ChatMessage(type="ai", content="hello")])
    response = _response(200, history.model_dump(mode="json"), "POST", "http://test/history")
    client = AgentClient(base_url="http://test", get_info=False)

    with patch("httpx.post", return_value=response):
        result = client.get_history("thread-1")

    assert result == history


def test_coursepilot_build_kb_uses_custom_timeout_and_ignores_proxy_env():
    response = _response(
        202,
        {"task_id": "task-1", "status": "pending"},
        "POST",
        "http://test/api/coursepilot/documents/document-1/build-kb",
    )
    client = CoursePilotClient(base_url="http://test")

    with (
        patch("httpx.request", return_value=response) as mocked,
        patch.object(
            client,
            "wait_for_task",
            return_value={"result": {"chunk_count": 1}},
        ) as wait_for_task,
    ):
        result = client.build_kb("document-1", timeout=3600)

    assert result == {"result": {"chunk_count": 1}}
    wait_for_task.assert_called_once_with("task-1", timeout=3600)
    assert mocked.call_args.kwargs["timeout"] == 30
    assert mocked.call_args.kwargs["trust_env"] is False
