from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier
from psycopg_pool import AsyncConnectionPool

from core.settings import settings


def checkpoint_connection_string() -> str:
    value = settings.COURSEPILOT_CHECKPOINT_DATABASE_URL
    if value:
        return value
    from memory.postgres import get_postgres_connection_string

    return get_postgres_connection_string()


def recoverable_config(*, workflow_type: str, task_id: str, course_id: str) -> RunnableConfig:
    thread_id = f"coursepilot:{workflow_type}:{task_id}"
    return RunnableConfig(
        configurable={
            "thread_id": thread_id,
            "checkpoint_ns": workflow_type,
            "course_id": course_id,
        },
        metadata={
            "coursepilot_thread_id": thread_id,
            "course_id": course_id,
            "workflow_mode": "recoverable",
        },
        tags=["coursepilot", "recoverable", f"thread:{thread_id}"],
    )


@asynccontextmanager
async def get_recoverable_checkpointer() -> AsyncIterator[AsyncPostgresSaver]:
    if not settings.COURSEPILOT_RECOVERABLE_WORKFLOWS_ENABLED:
        raise RuntimeError("RECOVERABLE_RUNTIME_UNAVAILABLE")
    connection_string = checkpoint_connection_string()
    async with await AsyncConnection.connect(connection_string, autocommit=True) as connection:
        await connection.execute(
            SQL("CREATE SCHEMA IF NOT EXISTS {} ").format(
                Identifier(settings.COURSEPILOT_CHECKPOINT_SCHEMA)
            )
        )
    async with AsyncConnectionPool[AsyncConnection[dict[str, Any]]](
        connection_string,
        min_size=1,
        max_size=2,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "options": f"-csearch_path={settings.COURSEPILOT_CHECKPOINT_SCHEMA}",
        },
        check=AsyncConnectionPool.check_connection,
    ) as pool:
        saver = AsyncPostgresSaver(pool)
        await saver.setup()
        yield saver
