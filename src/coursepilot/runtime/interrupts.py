from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from langgraph.types import Command
from sqlalchemy import select
from sqlalchemy.orm import Session

from coursepilot.domain import (
    ApprovalScope,
    ChangeMode,
    DecisionAction,
    HumanDecision,
    InterruptType,
)
from coursepilot.domain.common import canonical_sha256
from coursepilot.models import (
    ApprovalRecord,
    ArtifactRecord,
    ArtifactVersionRecord,
    GenerationTask,
    InterruptRecord,
    ResumeCommandRecord,
    SideEffectRunRecord,
)


def _edit_path(root: object, path: str, value: object, allowed: list[str]) -> None:
    """Apply one explicitly approved JSONPath edit, including array indexes."""
    if path not in allowed or not path.startswith("$."):
        raise InterruptError("INVALID_EDIT_PATH")
    parts: list[str | int] = []
    remainder = path[2:]
    for token in remainder.replace("]", "").replace("[", ".").split("."):
        if token:
            parts.append(int(token) if token.isdigit() else token)
    if not parts:
        raise InterruptError("INVALID_EDIT_PATH")
    target: object = root
    for part in parts[:-1]:
        try:
            target = target[part]  # type: ignore[index]
        except (KeyError, IndexError, TypeError):
            raise InterruptError("INVALID_EDIT_PATH") from None
    leaf = parts[-1]
    try:
        if isinstance(target, dict):
            if leaf not in target:
                raise InterruptError("INVALID_EDIT_PATH")
            target[leaf] = value
        elif isinstance(target, list) and isinstance(leaf, int) and leaf < len(target):
            target[leaf] = value
        else:
            raise InterruptError("INVALID_EDIT_PATH")
    except (KeyError, IndexError, TypeError):
        raise InterruptError("INVALID_EDIT_PATH") from None


class InterruptError(ValueError):
    def __init__(self, code: str, message: str | None = None):
        super().__init__(message or code)
        self.code = code


def expire_interrupt(record: InterruptRecord, *, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if record.status == "pending" and record.expires_at <= current:
        record.status = "expired"
        return True
    return False


class InterruptService:
    def __init__(self, session: Session, *, ttl_seconds: int = 604800):
        self.session = session
        self.ttl_seconds = ttl_seconds

    def create(
        self,
        *,
        task: GenerationTask,
        interrupt_type: InterruptType,
        checkpoint_id: str,
        artifact_version_id: str,
        payload: dict[str, Any],
        context_identity: dict[str, Any] | None = None,
    ) -> InterruptRecord:
        active = self.session.scalar(
            select(InterruptRecord).where(
                InterruptRecord.task_id == task.id,
                InterruptRecord.status.in_(["pending", "resuming"]),
            )
        )
        if active is not None:
            return active
        now = datetime.now(UTC)
        record = InterruptRecord(
            task_id=task.id,
            interrupt_type=interrupt_type.value,
            status="pending",
            checkpoint_id=checkpoint_id,
            thread_id=task.thread_id or f"coursepilot:{task.workflow_type}:{task.id}",
            artifact_version_id=artifact_version_id,
            payload_json=payload,
            context_identity_json=context_identity or {},
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        self.session.add(record)
        self.session.flush()
        task.active_interrupt_id = record.id
        task.status = "waiting_human"
        task.current_stage = interrupt_type.value
        task.worker_id = None
        task.locked_until = None
        return record

    def get(self, interrupt_id: str) -> InterruptRecord | None:
        record = self.session.get(InterruptRecord, interrupt_id)
        if record is not None:
            expire_interrupt(record)
        return record

    def decide(self, *, record: InterruptRecord, decision: HumanDecision) -> ResumeCommandRecord:
        if record.task_id != decision.task_id or record.checkpoint_id != decision.checkpoint_id:
            raise InterruptError("STALE_INTERRUPT")
        if expire_interrupt(record):
            raise InterruptError("INTERRUPT_EXPIRED")
        if record.status != "pending":
            existing = self.session.scalar(
                select(ResumeCommandRecord).where(
                    ResumeCommandRecord.decision_id == decision.decision_id
                )
            )
            if existing is not None:
                if canonical_sha256(existing.command_json) != canonical_sha256(
                    decision.model_dump(mode="json")
                ):
                    raise InterruptError("IDEMPOTENCY_CONFLICT")
                return existing
            raise InterruptError("DECISION_CONFLICT")
        task = self.session.get(GenerationTask, record.task_id)
        if task is None or task.status == "cancelled":
            raise InterruptError("TASK_CANCELLED")
        version = self.session.get(ArtifactVersionRecord, record.artifact_version_id)
        artifact = self.session.get(ArtifactRecord, version.artifact_id) if version else None
        if (
            version is None
            or artifact is None
            or artifact.active_version != version.version
            or (
                task.active_artifact_version is not None
                and task.active_artifact_version != version.version
            )
        ):
            raise InterruptError("STALE_ARTIFACT_VERSION")
        if decision.action in {DecisionAction.REJECT, DecisionAction.CANCEL}:
            record.status = "cancelled"
            task.status = "cancelled"
            task.worker_id = None
            task.locked_until = None
        else:
            record.status = "resuming"
            task.status = "running"
            task.worker_id = None
            task.locked_until = datetime.now(UTC) - timedelta(seconds=1)
        if decision.change_mode == ChangeMode.EDIT_RESUME:
            if not decision.patch:
                raise InterruptError("INVALID_EDIT_PATH")
            content = dict(version.content_json or {})
            for path, value in decision.patch.items():
                _edit_path(content, path, value, decision.target_paths)
            edited = ArtifactVersionRecord(
                artifact_id=version.artifact_id,
                version=int(version.version) + 1,
                schema_version=version.schema_version,
                content_json=content,
                storage_kind=version.storage_kind,
                storage_uri=version.storage_uri,
                content_sha256=canonical_sha256(content),
                created_by=decision.actor_id,
                source_run_id=version.source_run_id,
            )
            self.session.add(edited)
            task.active_artifact_version = edited.version
            artifact.active_version = edited.version
            self.session.flush()
            record.artifact_version_id = edited.id
        approval = ApprovalRecord(
            task_id=record.task_id,
            artifact_version_id=record.artifact_version_id,
            decision=decision.action.value,
            reviewer_id=decision.actor_id,
            notes=decision.feedback,
            decision_sha256=canonical_sha256(decision.model_dump(mode="json")),
            interrupt_id=record.id,
            checkpoint_id=record.checkpoint_id,
            decision_id=decision.decision_id,
            scope=ApprovalScope.CONTINUE_GENERATION.value,
            action=decision.action.value,
            target_paths_json=decision.target_paths,
            idempotency_key=decision.idempotency_key,
            request_sha256=canonical_sha256(decision.model_dump(mode="json")),
            expires_at=record.expires_at,
        )
        self.session.add(approval)
        command = ResumeCommandRecord(
            task_id=record.task_id,
            interrupt_id=record.id,
            decision_id=decision.decision_id,
            thread_id=record.thread_id,
            command_json=decision.model_dump(mode="json"),
            status=(
                "cancelled"
                if decision.action in {DecisionAction.REJECT, DecisionAction.CANCEL}
                else "pending"
            ),
            result_json=(
                {"task_status": task.status}
                if decision.action in {DecisionAction.REJECT, DecisionAction.CANCEL}
                else None
            ),
            completed_at=(
                datetime.now(UTC)
                if decision.action in {DecisionAction.REJECT, DecisionAction.CANCEL}
                else None
            ),
        )
        self.session.add(command)
        self.session.flush()
        return command

    def reopen(self, record: InterruptRecord, *, actor_id: str) -> InterruptRecord:
        if record.status != "expired":
            raise InterruptError("DECISION_CONFLICT")
        task = self.session.get(GenerationTask, record.task_id)
        if task is None or task.status == "cancelled":
            raise InterruptError("TASK_CANCELLED")
        now = datetime.now(UTC)
        new_record = InterruptRecord(
            task_id=record.task_id,
            interrupt_type=record.interrupt_type,
            status="pending",
            checkpoint_id=record.checkpoint_id,
            thread_id=record.thread_id,
            artifact_version_id=record.artifact_version_id,
            payload_json={**record.payload_json, "reopened_by": actor_id},
            context_identity_json=dict(record.context_identity_json),
            created_at=now,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
        )
        self.session.add(new_record)
        self.session.flush()
        record.superseded_by_id = new_record.id
        task.active_interrupt_id = new_record.id
        task.status = "waiting_human"
        task.worker_id = None
        task.locked_until = None
        return new_record

    def execute_side_effect(
        self,
        *,
        task_id: str,
        artifact_version_id: str,
        scope: ApprovalScope,
        operation_key: str,
        fn: Any,
        approval_record_id: str | None = None,
        required_target_paths: set[str] | None = None,
    ) -> dict[str, Any]:
        task = self.session.get(GenerationTask, task_id)
        # The side-effect boundary must observe the database's current active
        # version, not a possibly stale identity-map copy left by an earlier
        # request in this long-lived session.
        if task is not None:
            self.session.refresh(task)
        if task is not None and task.active_artifact_version is not None:
            version = self.session.get(ArtifactVersionRecord, artifact_version_id)
            if version is None or version.version != task.active_artifact_version:
                raise InterruptError("STALE_ARTIFACT_VERSION")
        existing = self.session.scalar(
            select(SideEffectRunRecord).where(
                SideEffectRunRecord.task_id == task_id,
                SideEffectRunRecord.artifact_version_id == artifact_version_id,
                SideEffectRunRecord.scope == scope.value,
                SideEffectRunRecord.operation_key == operation_key,
            )
        )
        if existing is not None and existing.status == "succeeded":
            return dict(existing.result_json or {})
        if existing is not None and existing.status == "running":
            raise InterruptError("SIDE_EFFECT_IN_PROGRESS")
        if existing is None:
            if approval_record_id is not None:
                approval = self.session.get(ApprovalRecord, approval_record_id)
            else:
                approval = self.session.scalar(
                    select(ApprovalRecord).where(
                        ApprovalRecord.task_id == task_id,
                        ApprovalRecord.artifact_version_id == artifact_version_id,
                        ApprovalRecord.scope == scope.value,
                        ApprovalRecord.decision == "approved",
                    )
                )
            if (
                approval is None
                or approval.task_id != task_id
                or approval.artifact_version_id != artifact_version_id
                or approval.scope != scope.value
                or approval.decision != "approved"
            ):
                raise InterruptError("APPROVAL_SCOPE_REQUIRED")
            if required_target_paths and not required_target_paths.issubset(
                set(approval.target_paths_json or [])
            ):
                raise InterruptError("APPROVAL_TARGET_SCOPE_REQUIRED")
        if existing is None:
            existing = SideEffectRunRecord(
                task_id=task_id,
                artifact_version_id=artifact_version_id,
                scope=scope.value,
                operation_key=operation_key,
                status="running",
            )
            self.session.add(existing)
            self.session.flush()
        try:
            result = fn()
            existing.status = "succeeded"
            existing.result_json = result
            existing.completed_at = datetime.now(UTC)
            return dict(result)
        except Exception:
            existing.status = "failed"
            raise

    def resume_command(self, command: ResumeCommandRecord) -> dict[str, Any]:
        """Resume one pending command against the immutable LangGraph thread."""
        from coursepilot.runtime.checkpoint_sync import get_sync_recoverable_checkpointer
        from coursepilot.runtime.recoverable_graph import (
            build_recoverable_graph,
            recoverable_graph_config,
        )

        if command.status in {"succeeded", "cancelled"}:
            return dict(command.result_json or {})
        if command.status == "running":
            raise InterruptError("RESUME_IN_PROGRESS")
        task = self.session.get(GenerationTask, command.task_id)
        if task is None or task.status == "cancelled":
            command.status = "failed"
            command.error_category = "TASK_CANCELLED"
            raise InterruptError("TASK_CANCELLED")
        command.status = "running"
        command.started_at = datetime.now(UTC)
        self.session.flush()
        with get_sync_recoverable_checkpointer() as saver:
            graph = build_recoverable_graph(str(task.workflow_type), checkpointer=saver)
            result = graph.invoke(
                Command(resume=command.command_json),
                config=recoverable_graph_config(str(task.workflow_type), task.id, task.course_id),
            )
        interrupts = result.get("__interrupt__", []) if isinstance(result, dict) else []
        previous = self.session.get(InterruptRecord, command.interrupt_id)
        if previous is not None:
            previous.status = "resumed"
            previous.resumed_at = datetime.now(UTC)
            # The next interrupt is created in the same SQLAlchemy session.  An
            # explicit flush prevents the active-record query in ``create``
            # from observing the old ``resuming`` state on PostgreSQL.
            self.session.flush()
        if interrupts:
            item = interrupts[0]
            value = dict(item.value)
            interrupt_type = InterruptType(value.pop("interrupt_type"))
            if previous is None:
                raise InterruptError("STALE_INTERRUPT")
            version = self.session.get(ArtifactVersionRecord, previous.artifact_version_id)
            if version is None:
                raise InterruptError("STALE_INTERRUPT")
            self.create(
                task=task,
                interrupt_type=interrupt_type,
                checkpoint_id=item.id,
                artifact_version_id=version.id,
                payload=value,
            )
        else:
            task.status = "completed"
            task.active_interrupt_id = None
            task.worker_id = None
            task.locked_until = None
            task.completed_at = datetime.now(UTC)
        command.status = "succeeded"
        command.result_json = {"interrupted": bool(interrupts), "task_status": task.status}
        command.completed_at = datetime.now(UTC)
        self.session.commit()
        return dict(command.result_json)
