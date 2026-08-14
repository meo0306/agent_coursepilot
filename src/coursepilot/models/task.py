"""
保存生成任务的状态和中间结果
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class GenerationTask(Base):
    __tablename__ = "coursepilot_generation_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    workflow_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy")
    active_interrupt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    current_stage: Mapped[str | None] = mapped_column(String(100), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    template_snapshot_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("coursepilot_template_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    active_run_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("coursepilot_workflow_runs.id", ondelete="SET NULL", use_alter=True),
        nullable=True,
    )
    input_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    active_artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_params_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    intermediate_outputs_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    lesson_designs = relationship("LessonDesign", back_populates="task")
