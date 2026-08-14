from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from coursepilot.models import GenerationTask
from coursepilot.schemas.task_schema import AsyncTaskAccepted, AsyncTaskRead

TERMINAL_TASK_STATUSES = frozenset({"completed", "needs_review", "failed"})


def utc_now() -> datetime:
    return datetime.now(UTC)


class AsyncTaskService:
    def __init__(self, session: Session):
        self.session = session

    def enqueue(
        self,
        *,
        course_id: str,
        task_type: str,
        input_params: dict[str, Any],
        workflow_type: str | None = None,
        workflow_mode: str = "legacy",
    ) -> AsyncTaskAccepted:
        task = GenerationTask(
            course_id=course_id,
            task_type=task_type,
            status="pending",
            workflow_type=workflow_type,
            workflow_mode=workflow_mode,
            input_params_json=jsonable_encoder(input_params),
        )
        self.session.add(task)
        self.session.flush()
        if workflow_mode == "recoverable":
            task.thread_id = f"coursepilot:{workflow_type}:{task.id}"
        self.session.commit()
        self.session.refresh(task)
        return AsyncTaskAccepted(
            task_id=task.id,
            status_url=f"/api/coursepilot/tasks/{task.id}",
        )

    def get(self, task_id: str) -> AsyncTaskRead | None:
        task = self.session.get(GenerationTask, task_id)
        if task is None:
            return None
        return AsyncTaskRead(
            task_id=task.id,
            course_id=task.course_id,
            task_type=task.task_type,
            status=task.status,
            result=task.result_json,
            error_message=task.error_message,
            attempt_count=task.attempt_count,
            created_at=task.created_at,
            updated_at=task.updated_at,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )


def prepare_execution_task(
    session: Session,
    *,
    task_id: str | None,
    course_id: str,
    task_type: str,
    input_params: dict[str, Any],
) -> GenerationTask:
    if task_id is None:
        task = GenerationTask(
            course_id=course_id,
            task_type=task_type,
            status="running",
            input_params_json=jsonable_encoder(input_params),
            attempt_count=1,
            started_at=utc_now(),
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        return task

    existing_task = session.get(GenerationTask, task_id)
    if existing_task is None:
        raise ValueError(f"Generation task not found: {task_id}")
    if existing_task.course_id != course_id or existing_task.task_type != task_type:
        raise ValueError("Generation task does not match the requested operation")
    existing_task.status = "running"
    existing_task.input_params_json = jsonable_encoder(input_params)
    existing_task.error_message = None
    existing_task.started_at = existing_task.started_at or utc_now()
    session.commit()
    return existing_task


def complete_execution_task(
    task: GenerationTask,
    result: Any,
    *,
    status: str = "completed",
    error_message: str | None = None,
) -> None:
    task.status = status
    task.result_json = jsonable_encoder(result)
    task.error_message = error_message
    task.completed_at = utc_now()
    task.locked_until = None
    task.worker_id = None


def fail_execution_task(task: GenerationTask, exc: BaseException) -> None:
    task.status = "failed"
    task.error_message = str(exc)
    task.completed_at = utc_now()
    task.locked_until = None
    task.worker_id = None
