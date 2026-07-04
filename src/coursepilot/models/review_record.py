from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReviewRecord(Base):
    __tablename__ = "coursepilot_review_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(36), nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    write_back_status: Mapped[str] = mapped_column(String(32), nullable=False, default="not_written")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
