from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg import Connection, connect
from psycopg.rows import dict_row
from psycopg.sql import SQL, Identifier
from psycopg_pool import ConnectionPool

from core.settings import settings
from coursepilot.runtime.checkpoint import checkpoint_connection_string


def _prepare_checkpoint_schema(connection_string: str) -> str:
    schema = settings.COURSEPILOT_CHECKPOINT_SCHEMA
    with connect(connection_string, autocommit=True) as connection:
        connection.execute(SQL("CREATE SCHEMA IF NOT EXISTS {} ").format(Identifier(schema)))
    return schema


@contextmanager
def get_sync_recoverable_checkpointer() -> Iterator[PostgresSaver]:
    if not settings.COURSEPILOT_RECOVERABLE_WORKFLOWS_ENABLED:
        raise RuntimeError("RECOVERABLE_RUNTIME_UNAVAILABLE")
    connection_string = checkpoint_connection_string()
    schema = _prepare_checkpoint_schema(connection_string)
    with ConnectionPool[Connection[dict[str, Any]]](
        connection_string,
        min_size=1,
        max_size=2,
        kwargs={
            "autocommit": True,
            "row_factory": dict_row,
            "options": f"-csearch_path={schema}",
        },
    ) as pool:
        saver = PostgresSaver(pool)
        saver.setup()
        yield saver
