"""
定义 CoursePilot 专用 SQLAlchemy Base

"""

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

NAMING_CONVENTION = {
    # Stable constraint names make Alembic migrations easier to diff and roll
    # back. Without a naming convention, databases may auto-generate different
    # names on different machines.
    # 给数据库约束统一命名，例如 pk_coursepilot_courses。
    # 这样 Alembic 生成迁移时名字稳定，后续升级/回滚更可靠。
    "ix": "ix_%(column_0_label)s",  # 索引的缩写
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Base class for CoursePilot business tables."""

    # All CoursePilot ORM models inherit this Base instead of using any AST
    # memory/checkpointer metadata. That keeps business tables isolated and
    # lets Alembic target only CoursePilot tables.
    # CoursePilot 所有 ORM model 都继承这个 Base，和原 AST 的 LangGraph memory/checkpointer 表隔离。
    metadata = MetaData(
        naming_convention=NAMING_CONVENTION
    )  # Alembic 会读取这里注册过的表，然后知道哪些表需要迁移
