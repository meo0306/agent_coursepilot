from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class CourseRAGBase(DeclarativeBase):
    """Declarative base owned by CourseRAG persistence.

    CourseRAG shares the current PostgreSQL engine with CoursePilot until P19,
    but it keeps independent metadata and never imports CoursePilot ORM models.
    """

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid4())
