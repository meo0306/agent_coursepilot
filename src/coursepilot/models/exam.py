from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExamBlueprint(Base):
    __tablename__ = "coursepilot_exam_blueprints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    chapter_range: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    blueprint_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    questions = relationship(
        "Question", back_populates="exam_blueprint", cascade="all, delete-orphan"
    )
