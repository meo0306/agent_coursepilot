from unittest.mock import AsyncMock, Mock

import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from schema import AgentInfo

COURSEPILOT_AGENT_KEYS = {
    "coursepilot-lesson-agent",
    "coursepilot-exam-agent",
    "coursepilot-ppt-agent",
}


def test_info_lists_only_coursepilot_agents(test_client):
    response = test_client.get("/info")

    assert response.status_code == 200
    payload = response.json()
    assert {agent["key"] for agent in payload["agents"]} == COURSEPILOT_AGENT_KEYS
    assert payload["default_agent"] == "coursepilot-lesson-agent"


def test_invoke_default_agent_returns_coursepilot_prompt_entry_message(test_client):
    response = test_client.post("/invoke", json={"message": "hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "ai"
    assert "/api/coursepilot/courses/{course_id}/lessons/generate" in payload["content"]


def test_invoke_named_agent_returns_coursepilot_prompt_entry_message(test_client):
    response = test_client.post(
        "/coursepilot-exam-agent/invoke",
        json={"message": "hello"},
    )

    assert response.status_code == 200
    assert "/api/coursepilot/courses/{course_id}/exams/blueprint" in response.json()["content"]


def test_invoke_unknown_agent_returns_404(test_client):
    response = test_client.post("/missing-agent/invoke", json={"message": "hello"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown agent: missing-agent"


def test_invoke_rejects_reserved_agent_config(test_client):
    response = test_client.post(
        "/invoke",
        json={"message": "hello", "agent_config": {"thread_id": "bad"}},
    )

    assert response.status_code == 422
    assert "reserved keys" in response.json()["detail"]


def test_stream_returns_sse_prompt_message(test_client):
    with test_client.stream("POST", "/stream", json={"message": "hello"}) as response:
        body = response.read().decode()

    assert response.status_code == 200
    assert "data: " in body
    assert "/api/coursepilot/courses/{course_id}/lessons/generate" in body
    assert "data: [DONE]" in body


def test_auth_protects_prompt_and_coursepilot_routes(test_client, monkeypatch):
    from service import service

    monkeypatch.setattr(service.settings, "AUTH_SECRET", SecretStr("secret"))

    response = test_client.post("/invoke", json={"message": "hello"})
    assert response.status_code == 401

    response = test_client.post(
        "/invoke",
        json={"message": "hello"},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_lifespan_loads_coursepilot_agents(monkeypatch, caplog):
    from contextlib import asynccontextmanager

    from fastapi import FastAPI

    from service import service

    fake_saver = type("Saver", (), {"setup": AsyncMock()})()
    fake_store = type("Store", (), {"setup": AsyncMock()})()
    fake_agent = type("Agent", (), {"checkpointer": None, "store": None})()

    @asynccontextmanager
    async def fake_initialize_database():
        yield fake_saver

    @asynccontextmanager
    async def fake_initialize_store():
        yield fake_store

    monkeypatch.setattr(service.settings, "COURSEPILOT_GENERATION_MODE", "deterministic")
    monkeypatch.setattr(service.settings, "COURSEPILOT_ASYNC_WORKER_ENABLED", False)
    monkeypatch.setattr(service, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(service, "initialize_store", fake_initialize_store)
    monkeypatch.setattr(service, "get_agent", Mock(return_value=fake_agent))
    monkeypatch.setattr(service, "load_agent", AsyncMock())
    monkeypatch.setattr(
        service,
        "get_all_agent_info",
        lambda: [AgentInfo(key="coursepilot-lesson-agent", description="Lesson")],
    )
    caplog.set_level("INFO", logger=service.logger.name)

    async with service.lifespan(FastAPI()):
        pass

    fake_saver.setup.assert_awaited_once()
    fake_store.setup.assert_awaited_once()
    assert fake_agent.checkpointer is fake_saver
    assert fake_agent.store is fake_store
    assert "Agent loaded: coursepilot-lesson-agent" in caplog.text


@pytest.mark.asyncio
async def test_history_reads_default_agent_state(monkeypatch):
    from service import service

    class Snapshot:
        values = {"messages": [AIMessage(content="hello")]}

    fake_agent = Mock()
    fake_agent.aget_state = AsyncMock(return_value=Snapshot())
    monkeypatch.setattr(service, "get_agent", Mock(return_value=fake_agent))

    result = await service.history(service.ChatHistoryInput(thread_id="thread-1"))

    assert result.messages[0].content == "hello"
