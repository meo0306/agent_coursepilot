from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class IdempotencyRecord(Base):
    __tablename__ = "coursepilot_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "operation",
            "idempotency_key",
            name="uq_coursepilot_idempotency_operation_key",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    operation: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="in_progress")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    resource_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )
