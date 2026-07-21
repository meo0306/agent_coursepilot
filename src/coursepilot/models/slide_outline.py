from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class SlideOutline(Base):
    __tablename__ = "coursepilot_slide_outlines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    lesson_design_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_lesson_designs.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    outline_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    pptx_file_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("coursepilot_export_files.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
