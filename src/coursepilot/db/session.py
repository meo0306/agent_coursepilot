"""
创建 CoursePilot 业务数据库连接和 FastAPI session dependency

"""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.settings import settings


def _build_postgres_url() -> str:
    # Prefer a CoursePilot-specific URL when it is configured. This keeps the
    # business database independent from the original AST memory/checkpointer
    # settings while still allowing both systems to share Postgres in local dev.
    # 如果在 `.env` 里显式配置了 `COURSEPILOT_DATABASE_URL`，CoursePilot 就优先使用这个 URL。
    if settings.COURSEPILOT_DATABASE_URL:
        return settings.COURSEPILOT_DATABASE_URL

    # Fall back to the existing POSTGRES_* settings from Agent Service Toolkit.
    # We validate every required piece up front so a missing value fails with a
    # readable message instead of a lower-level SQLAlchemy connection error.
    required = {
        "POSTGRES_USER": settings.POSTGRES_USER,
        "POSTGRES_PASSWORD": settings.POSTGRES_PASSWORD,
        "POSTGRES_HOST": settings.POSTGRES_HOST,
        "POSTGRES_PORT": settings.POSTGRES_PORT,
        "POSTGRES_DB": settings.POSTGRES_DB,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError(
            "Missing CoursePilot PostgreSQL configuration: "
            f"{', '.join(missing)}. Set COURSEPILOT_DATABASE_URL or POSTGRES_* values."
        )
    postgres_password = settings.POSTGRES_PASSWORD
    if postgres_password is None:
        raise ValueError("Missing CoursePilot PostgreSQL configuration: POSTGRES_PASSWORD.")
    password = postgres_password.get_secret_value()
    return (
        f"postgresql+psycopg://{settings.POSTGRES_USER}:{password}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


@lru_cache  # 在进程中只创建一次
def get_coursepilot_engine() -> Engine:
    # Creating an Engine is relatively expensive and should be done once per
    # process. pool_pre_ping avoids reusing stale database connections.
    return create_engine(
        _build_postgres_url(), pool_pre_ping=True
    )  # `pool_pre_ping=True` 会检查连接是否可用，减少数据库空闲断连导致的问题。


CoursePilotSessionLocal = sessionmaker(
    # CoursePilot service methods manage transaction boundaries explicitly.
    # autocommit=False and autoflush=False keep database writes predictable.
    #
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_session() -> Generator[Session, None, None]:
    # 给 FastAPI 路由用的 dependency。每次请求拿到一个数据库 session，请求结束后自动关闭。
    # 不用在每个接口里手动创建和关闭数据库连接，FastAPI 自动按请求生命周期管理
    # FastAPI dependencies can yield a session and reliably close it after the
    # request. The bind is resolved lazily so tests can monkeypatch settings.
    with CoursePilotSessionLocal(bind=get_coursepilot_engine()) as session:
        yield session
