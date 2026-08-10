from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import coursepilot.models  # noqa: F401
import courserag.persistence.models  # noqa: F401
from coursepilot.db.base import Base
from courserag.persistence.base import CourseRAGBase


@pytest.fixture
def p03_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    CourseRAGBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session
