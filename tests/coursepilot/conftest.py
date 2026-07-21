from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from core import settings
from coursepilot.db.base import Base
from coursepilot.db.session import get_session
from coursepilot.services.task_worker import CoursePilotTaskWorker
from service import app


@pytest.fixture(autouse=True)
def deterministic_coursepilot_runtime(monkeypatch) -> None:
    monkeypatch.setattr(settings, "COURSEPILOT_GENERATION_MODE", "deterministic")
    monkeypatch.setattr(settings, "COURSEPILOT_EMBEDDING_PROVIDER", "hashing")
    monkeypatch.setattr(settings, "COURSEPILOT_ASYNC_WORKER_ENABLED", False)


@pytest.fixture
def coursepilot_client(tmp_path, monkeypatch) -> Generator[TestClient, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(settings, "COURSEPILOT_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "COURSEPILOT_CHROMA_DIR", str(tmp_path / "chroma"))

    def override_get_session() -> Generator[Session, None, None]:
        with session_local() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.state.coursepilot_test_task_worker = CoursePilotTaskWorker(
        session_factory=session_local,
        poll_seconds=0,
        lease_seconds=30,
    )
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.state.coursepilot_test_task_worker = None
        Base.metadata.drop_all(engine)
        engine.dispose()
