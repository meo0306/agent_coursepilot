from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import timedelta
from time import monotonic
from uuid import uuid4

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.db.session import CoursePilotSessionLocal, get_coursepilot_engine
from coursepilot.domain import InterruptType
from coursepilot.models import GenerationTask, ResumeCommandRecord
from coursepilot.runtime import InterruptService, get_sync_recoverable_checkpointer
from coursepilot.runtime.recoverable_graph import build_recoverable_graph, recoverable_graph_config
from coursepilot.schemas.exam_schema import ExamGenerationParams
from coursepilot.schemas.lesson_schema import LessonGenerationParams
from coursepilot.schemas.ppt_schema import PPTGenerationParams
from coursepilot.services.async_task_service import fail_execution_task, utc_now

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


def default_session_factory() -> Session:
    return CoursePilotSessionLocal(bind=get_coursepilot_engine())


class CoursePilotTaskWorker:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = default_session_factory,
        poll_seconds: float | None = None,
        lease_seconds: int | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.poll_seconds = (
            settings.COURSEPILOT_ASYNC_WORKER_POLL_SECONDS if poll_seconds is None else poll_seconds
        )
        self.lease_seconds = (
            settings.COURSEPILOT_ASYNC_TASK_LEASE_SECONDS
            if lease_seconds is None
            else lease_seconds
        )
        self.worker_id = f"worker-{uuid4().hex[:16]}"
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="coursepilot-task-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        self._stop_event.set()
        if self._thread is None:
            return
        self._thread.join(
            timeout=(
                settings.COURSEPILOT_ASYNC_WORKER_SHUTDOWN_TIMEOUT_SECONDS
                if timeout is None
                else timeout
            )
        )

    def run_once(self) -> bool:
        task_id = self._claim_next_task()
        if task_id is None:
            return False

        heartbeat = _TaskLeaseHeartbeat(
            session_factory=self.session_factory,
            task_id=task_id,
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        heartbeat.start()
        try:
            self._execute(task_id)
        finally:
            heartbeat.stop()
        return True

    def run_until_idle(self, *, max_tasks: int = 100) -> int:
        completed = 0
        while completed < max_tasks and self.run_once():
            completed += 1
        return completed

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                claimed = self.run_once()
            except Exception:
                logger.exception("CoursePilot async task worker iteration failed")
                claimed = False
            if not claimed:
                self._stop_event.wait(self.poll_seconds)

    def _claim_next_task(self) -> str | None:
        now = utc_now()
        with self.session_factory() as session:
            statement = (
                select(GenerationTask)
                .where(
                    or_(
                        GenerationTask.status == "pending",
                        and_(
                            GenerationTask.status == "running",
                            GenerationTask.locked_until.is_not(None),
                            GenerationTask.locked_until < now,
                        ),
                    )
                )
                .order_by(GenerationTask.created_at, GenerationTask.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            task = session.scalar(statement)
            if task is None:
                return None
            task.status = "running"
            task.worker_id = self.worker_id
            task.locked_until = now + timedelta(seconds=self.lease_seconds)
            task.started_at = task.started_at or now
            task.completed_at = None
            task.error_message = None
            task.attempt_count += 1
            session.commit()
            return task.id

    def _execute(self, task_id: str) -> None:
        with self.session_factory() as session:
            task = session.get(GenerationTask, task_id)
            if task is None or task.worker_id != self.worker_id or task.status != "running":
                return
            try:
                self._dispatch(session, task)
            except BaseException as exc:
                session.rollback()
                task = session.get(GenerationTask, task_id)
                if task is None:
                    raise
                fail_execution_task(task, exc)
                session.commit()
                logger.exception(
                    "CoursePilot async task failed: task_id=%s task_type=%s",
                    task.id,
                    task.task_type,
                )

    def _dispatch(self, session: Session, task: GenerationTask) -> None:
        if task.workflow_mode == "recoverable":
            self._dispatch_recoverable(session, task)
            return
        payload = dict(task.input_params_json or {})
        if task.task_type == "build_kb":
            from coursepilot.services.kb_service import KnowledgeBaseService

            build_result = KnowledgeBaseService(session).build_document(
                str(payload["document_id"]),
                task_id=task.id,
            )
            if build_result is None:
                raise ValueError("Document not found while executing build-kb task")
            return
        if task.task_type == "courserag_build":
            from coursepilot.adapters.courserag_build_bridge import (
                CourseRAGBuildCompatibilityBridge,
            )

            CourseRAGBuildCompatibilityBridge(session).resume_task(task)
            return
        if task.task_type == "lesson_design":
            from coursepilot.services.lesson_service import LessonService

            LessonService(session).generate_lesson(
                task.course_id,
                LessonGenerationParams.model_validate(payload["params"]),
                task_id=task.id,
            )
            return
        if task.task_type == "exam_blueprint":
            from coursepilot.services.exam_service import ExamService

            ExamService(session).create_blueprint(
                task.course_id,
                ExamGenerationParams.model_validate(payload["params"]),
                task_id=task.id,
            )
            return
        if task.task_type == "exam_questions":
            from coursepilot.services.exam_service import ExamService

            question_result = ExamService(session).generate_questions(
                str(payload["blueprint_id"]),
                task_id=task.id,
            )
            if question_result is None:
                raise ValueError("Exam blueprint not found while executing question task")
            return
        if task.task_type == "ppt_outline":
            from coursepilot.services.ppt_service import PPTService

            ppt_result = PPTService(session).generate_outline(
                str(payload["lesson_id"]),
                PPTGenerationParams.model_validate(payload["params"]),
                task_id=task.id,
            )
            if ppt_result is None:
                raise ValueError("Lesson not found while executing PPT task")
            return
        raise ValueError(f"Unsupported async task type: {task.task_type}")

    def _dispatch_recoverable(self, session: Session, task: GenerationTask) -> None:
        if task.workflow_type not in {"lesson", "exam", "ppt"}:
            raise ValueError("Unsupported recoverable workflow type")
        from coursepilot.domain.common import canonical_sha256
        from coursepilot.models import ArtifactRecord, ArtifactVersionRecord

        pending_command = session.scalar(
            select(ResumeCommandRecord)
            .where(
                ResumeCommandRecord.task_id == task.id,
                ResumeCommandRecord.status == "pending",
            )
            .order_by(ResumeCommandRecord.created_at)
        )
        if pending_command is not None:
            InterruptService(session).resume_command(pending_command)
            return

        artifact = session.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.task_id == task.id,
                ArtifactRecord.artifact_type == f"{task.workflow_type}_draft",
            )
        )
        if artifact is None:
            artifact = ArtifactRecord(
                task_id=task.id,
                course_id=task.course_id,
                artifact_type=f"{task.workflow_type}_draft",
                active_version=1,
            )
            session.add(artifact)
            session.flush()
            content = dict(task.input_params_json or {})
            session.add(
                ArtifactVersionRecord(
                    artifact_id=artifact.id,
                    version=1,
                    schema_version="p12-recoverable-v1",
                    content_json=content,
                    storage_kind="postgres",
                    content_sha256=canonical_sha256(content),
                    created_by="recoverable-runtime",
                )
            )
            session.flush()
            task.active_artifact_version = 1
        config = recoverable_graph_config(task.workflow_type, task.id, task.course_id)
        input_params = dict(task.input_params_json or {})
        if (
            task.workflow_type == "lesson"
            and isinstance(input_params.get("knowledge_points"), dict)
            and isinstance(input_params.get("context_ref"), dict)
        ):
            state = {
                "task_id": task.id,
                "course_id": task.course_id,
                "request": dict(input_params.get("request", input_params)),
                "template_snapshot_id": str(
                    input_params.get("template_snapshot_id", "lesson_standard_university_v1")
                ),
                "knowledge_points": input_params["knowledge_points"],
                "context_ref": input_params["context_ref"],
            }
        else:
            state = {
                "interrupt_payload": {
                    "task_id": task.id,
                    "artifact_id": artifact.id,
                    "artifact_version": task.active_artifact_version,
                }
            }
        with get_sync_recoverable_checkpointer() as saver:
            graph = build_recoverable_graph(task.workflow_type, checkpointer=saver)
            result = graph.invoke(state, config=config)
        interrupts = result.get("__interrupt__", []) if isinstance(result, dict) else []
        if interrupts:
            item = interrupts[0]
            value = dict(item.value)
            interrupt_type = InterruptType(value.pop("interrupt_type"))
            artifact_version = session.scalar(
                select(ArtifactVersionRecord).where(
                    ArtifactVersionRecord.artifact_id == artifact.id,
                    ArtifactVersionRecord.version == task.active_artifact_version,
                )
            )
            if artifact_version is None:
                raise ValueError("Recoverable artifact version missing")
            InterruptService(session).create(
                task=task,
                interrupt_type=interrupt_type,
                checkpoint_id=item.id,
                artifact_version_id=artifact_version.id,
                payload=value,
            )
            session.commit()
            return
        task.status = "completed"
        task.completed_at = utc_now()


class _TaskLeaseHeartbeat:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        task_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self.session_factory = session_factory
        self.task_id = task_id
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run,
            name=f"coursepilot-task-heartbeat-{self.task_id[:8]}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def _run(self) -> None:
        interval = max(1.0, self.lease_seconds / 3)
        next_heartbeat = monotonic() + interval
        while not self._stop_event.wait(max(0.0, next_heartbeat - monotonic())):
            try:
                with self.session_factory() as session:
                    session.execute(
                        update(GenerationTask)
                        .where(
                            GenerationTask.id == self.task_id,
                            GenerationTask.worker_id == self.worker_id,
                            GenerationTask.status == "running",
                        )
                        .values(locked_until=utc_now() + timedelta(seconds=self.lease_seconds))
                    )
                    session.commit()
            except Exception:
                logger.exception("Failed to renew async task lease: %s", self.task_id)
            next_heartbeat = monotonic() + interval
