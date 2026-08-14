from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from coursepilot.domain.common import DomainModel, UTCDateTime


class WorkflowType(StrEnum):
    LESSON = "lesson"
    EXAM = "exam"
    PPT = "ppt"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.QUEUED: frozenset({TaskStatus.RUNNING, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING: frozenset(
        {
            TaskStatus.WAITING_HUMAN,
            TaskStatus.NEEDS_REVIEW,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.WAITING_HUMAN: frozenset(
        {
            TaskStatus.RUNNING,
            TaskStatus.NEEDS_REVIEW,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED,
        }
    ),
    TaskStatus.NEEDS_REVIEW: frozenset(
        {TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}
    ),
    TaskStatus.FAILED: frozenset({TaskStatus.QUEUED}),
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


def require_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target not in ALLOWED_TASK_TRANSITIONS[current]:
        raise ValueError(f"illegal task transition: {current.value} -> {target.value}")


class BusinessTask(DomainModel):
    task_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    workflow_type: WorkflowType
    status: TaskStatus
    current_stage: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    template_snapshot_id: str | None = None
    input_version: int = Field(default=1, ge=1)
    active_artifact_version: int | None = Field(default=None, ge=1)
    active_run_id: str | None = None
    created_at: UTCDateTime
    updated_at: UTCDateTime

    @model_validator(mode="after")
    def validate_thread_identity(self) -> BusinessTask:
        expected = f"coursepilot:{self.workflow_type.value}:{self.task_id}"
        if self.thread_id != expected:
            raise ValueError("thread_id does not match stable CoursePilot identity")
        return self
