"""
保存教学设计草稿 JSON
保存RAG 检索到的上下文和 validator 报告
"""
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class LessonDesign(Base):
    __tablename__ = "coursepilot_lesson_designs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"), nullable=False
    )
    chapter: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    total_sessions: Mapped[int] = mapped_column(Integer, nullable=False)
    content_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    validation_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    task = relationship("GenerationTask", back_populates="lesson_designs")

