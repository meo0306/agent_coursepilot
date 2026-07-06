import logging
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from schema import AgentInfo


@pytest.mark.asyncio
async def test_lifespan(monkeypatch, caplog) -> None:
    """Test that the lifespan sets up the database and store, loads the agents, and logs errors."""
    from service import service

    fake_saver_setup = False
    fake_store_setup = False

    class FakeSaver:
        async def setup(self) -> None:
            nonlocal fake_saver_setup
            fake_saver_setup = True

    class FakeStore:
        async def setup(self) -> None:
            nonlocal fake_store_setup
            fake_store_setup = True

    fake_saver = FakeSaver()
    fake_store = FakeStore()

    @asynccontextmanager
    async def fake_initialize_database():
        yield fake_saver

    @asynccontextmanager
    async def fake_initialize_store():
        yield fake_store

    agents = {
        "good": type("Agent", (), {"checkpointer": None, "store": None})(),
        "bad": type("Agent", (), {"checkpointer": None, "store": None})(),
    }

    async def fake_load_agent(agent_key: str) -> None:
        if agent_key == "bad":
            raise RuntimeError("boom")

    def fake_get_agent(agent_key: str):
        return agents[agent_key]

    health_checks = 0

    def fake_health_check() -> None:
        nonlocal health_checks
        health_checks += 1

    monkeypatch.setattr(service.settings, "COURSEPILOT_GENERATION_MODE", "deterministic")
    monkeypatch.setattr(service, "check_coursepilot_llm_health", fake_health_check)
    monkeypatch.setattr(service, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(service, "initialize_store", fake_initialize_store)
    monkeypatch.setattr(service, "load_agent", fake_load_agent)
    monkeypatch.setattr(service, "get_agent", fake_get_agent)
    monkeypatch.setattr(
        service,
        "get_all_agent_info",
        lambda: [
            AgentInfo(key="good", description=""),
            AgentInfo(key="bad", description=""),
        ],
    )

    caplog.set_level(logging.INFO, logger=service.logger.name)

    async with service.lifespan(FastAPI()):
        pass

    assert fake_saver_setup
    assert fake_store_setup
    assert agents["good"].checkpointer is fake_saver
    assert agents["good"].store is fake_store
    assert agents["bad"].checkpointer is fake_saver
    assert agents["bad"].store is fake_store
    assert health_checks == 0

    assert "Agent loaded: good" in caplog.text
    assert "Failed to load agent bad: boom" in caplog.text


@pytest.mark.asyncio
async def test_lifespan_runs_coursepilot_llm_health_check_in_llm_mode(monkeypatch) -> None:
    from service import service

    @asynccontextmanager
    async def fake_initialize_database():
        yield type("Saver", (), {})()

    @asynccontextmanager
    async def fake_initialize_store():
        yield type("Store", (), {})()

    health_checks = 0

    def fake_health_check() -> None:
        nonlocal health_checks
        health_checks += 1

    monkeypatch.setattr(service.settings, "COURSEPILOT_GENERATION_MODE", "llm")
    monkeypatch.setattr(service, "check_coursepilot_llm_health", fake_health_check)
    monkeypatch.setattr(service, "initialize_database", fake_initialize_database)
    monkeypatch.setattr(service, "initialize_store", fake_initialize_store)
    monkeypatch.setattr(service, "get_all_agent_info", lambda: [])

    async with service.lifespan(FastAPI()):
        pass

    assert health_checks == 1
