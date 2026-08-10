"""
告诉 Alembic 如何找到 `src/coursepilot` 和 SQLAlchemy metadata
"""

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# 把 src 加到 sys.path，确保 alembic 命令能 import src/coursepilot
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    # Alembic runs from the repository root, not through pytest. Adding src here
    # lets migration commands import coursepilot.* modules consistently.
    sys.path.insert(0, str(SRC))

# Importing coursepilot.models registers every ORM model on Base.metadata. The
# migration environment then knows which CoursePilot tables exist in code.
import coursepilot.models  # noqa: E402,F401
import courserag.persistence.models  # noqa: E402,F401
from coursepilot.db.base import Base  # noqa: E402
from coursepilot.db.session import _build_postgres_url  # noqa: E402
from courserag.persistence.base import CourseRAGBase  # noqa: E402

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = [Base.metadata, CourseRAGBase.metadata]


def run_migrations_offline() -> None:
    # Offline mode emits SQL text without opening a database connection.
    url = _build_postgres_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Online mode connects to Postgres and applies migrations directly.
    config.set_main_option(
        "sqlalchemy.url", _build_postgres_url()
    )  # 迁移命令会复用 `session.py` 里的数据库 URL 生成逻辑，避免 Alembic 和应用代码各写一套数据库配置。
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
