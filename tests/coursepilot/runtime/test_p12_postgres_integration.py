"""Real PostgreSQL checks for the P12 recovery contract.

The suite is opt-in because the normal unit-test environment intentionally has
no database dependency.  ``run_p12_postgres_gate.ps1`` starts an isolated
Compose project and sets ``COURSEPILOT_P12_POSTGRES_GATE=1``.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from coursepilot.db.session import CoursePilotSessionLocal, get_coursepilot_engine
from coursepilot.domain import ApprovalScope, ChangeMode, DecisionAction, HumanDecision
from coursepilot.domain.common import canonical_sha256
from coursepilot.models import (
    ApprovalRecord,
    ArtifactVersionRecord,
    Course,
    GenerationTask,
    InterruptRecord,
    ResumeCommandRecord,
)
from coursepilot.runtime import InterruptError, InterruptService
from coursepilot.services.task_worker import CoursePilotTaskWorker

pytestmark = pytest.mark.skipif(
    os.getenv("COURSEPILOT_P12_POSTGRES_GATE") != "1",
    reason="P12 PostgreSQL gate is opt-in",
)


@pytest.fixture(autouse=True)
def _cancel_leftover_queued_tasks() -> None:
    """Keep reruns deterministic without touching completed audit facts."""
    with _session() as session:
        session.execute(
            update(GenerationTask)
            .where(GenerationTask.status.in_(["pending", "running"]))
            .values(status="cancelled", worker_id=None, locked_until=None)
        )
        session.commit()


def _session() -> Session:
    return CoursePilotSessionLocal(bind=get_coursepilot_engine())


def _create_task(workflow_type: str, *, title: str = "original") -> tuple[str, str]:
    course_id = str(uuid4())
    task_id = str(uuid4())
    with _session() as session:
        session.add(Course(id=course_id, course_name=f"P12 {workflow_type} {task_id}"))
        session.add(
            GenerationTask(
                id=task_id,
                course_id=course_id,
                task_type=f"{workflow_type}_recoverable",
                workflow_type=workflow_type,
                workflow_mode="recoverable",
                status="pending",
                thread_id=f"coursepilot:{workflow_type}:{task_id}",
                input_params_json={"plan": {"title": title}},
            )
        )
        session.commit()
    return task_id, course_id


def _worker() -> CoursePilotTaskWorker:
    return CoursePilotTaskWorker(poll_seconds=0.01, lease_seconds=30)


def _interrupt(task_id: str) -> InterruptRecord:
    with _session() as session:
        record = session.scalar(
            select(InterruptRecord)
            .where(InterruptRecord.task_id == task_id)
            .where(InterruptRecord.status == "pending")
            .order_by(InterruptRecord.created_at.desc())
        )
        assert record is not None
        return record


def _approve(task_id: str, record: InterruptRecord, *, decision_id: str) -> str:
    decision = HumanDecision(
        decision_id=decision_id,
        task_id=task_id,
        checkpoint_id=record.checkpoint_id,
        action=DecisionAction.APPROVE,
        actor_id="course-owner",
        idempotency_key=decision_id,
    )
    with _session() as session:
        current = session.get(InterruptRecord, record.id)
        assert current is not None
        command = InterruptService(session).decide(record=current, decision=decision)
        session.commit()
        return command.id


@pytest.mark.parametrize(
    ("workflow_type", "expected_interrupts"),
    [
        ("lesson", ["lesson_session_plan_review", "lesson_final_review"]),
        ("exam", ["exam_blueprint_review", "exam_global_review"]),
        ("ppt", ["ppt_architecture_review", "ppt_final_review"]),
    ],
)
def test_six_interrupts_resume_across_worker_restarts(
    workflow_type: str, expected_interrupts: list[str]
) -> None:
    task_id, _ = _create_task(workflow_type)
    worker = _worker()

    assert worker.run_once() is True
    first = _interrupt(task_id)
    assert first.interrupt_type == expected_interrupts[0]
    first_command = _approve(task_id, first, decision_id=f"decision-{uuid4()}")

    # A new worker instance represents a service restart.  The same stable
    # thread and pending command must continue at the next interrupt.
    assert _worker().run_once() is True
    second = _interrupt(task_id)
    assert second.interrupt_type == expected_interrupts[1]
    assert second.id != first.id

    _approve(task_id, second, decision_id=f"decision-{uuid4()}")
    assert _worker().run_once() is True
    with _session() as session:
        task = session.get(GenerationTask, task_id)
        assert task is not None
        assert task.status == "completed"
        assert task.active_interrupt_id is None
        command = session.get(ResumeCommandRecord, first_command)
        assert command is not None and command.status == "succeeded"


def test_edit_resume_creates_new_version_and_duplicate_decision_is_idempotent() -> None:
    task_id, _ = _create_task("lesson")
    assert _worker().run_once() is True
    first = _interrupt(task_id)
    decision_id = f"edit-{uuid4()}"
    decision = HumanDecision(
        decision_id=decision_id,
        task_id=task_id,
        checkpoint_id=first.checkpoint_id,
        action=DecisionAction.REQUEST_CHANGES,
        actor_id="course-owner",
        change_mode=ChangeMode.EDIT_RESUME,
        target_paths=["$.plan.title"],
        patch={"$.plan.title": "owner-edited"},
        idempotency_key=decision_id,
    )
    with _session() as session:
        current = session.get(InterruptRecord, first.id)
        assert current is not None
        command = InterruptService(session).decide(record=current, decision=decision)
        session.commit()
        command_id = command.id
        duplicate = InterruptService(session).decide(record=current, decision=decision)
        assert duplicate.id == command_id

    assert _worker().run_once() is True
    with _session() as session:
        versions = list(
            session.scalars(
                select(ArtifactVersionRecord)
                .join(
                    GenerationTask,
                    GenerationTask.active_artifact_version == ArtifactVersionRecord.version,
                )
                .where(GenerationTask.id == task_id)
            )
        )
        task = session.get(GenerationTask, task_id)
        assert task is not None
        artifact_versions = list(
            session.scalars(
                select(ArtifactVersionRecord).where(
                    ArtifactVersionRecord.artifact_id
                    == session.scalar(
                        select(ArtifactVersionRecord.artifact_id).where(
                            ArtifactVersionRecord.id == first.artifact_version_id
                        )
                    )
                )
            )
        )
        assert len(versions) >= 1
        assert len(artifact_versions) == 2
        assert task.active_artifact_version == 2
        assert artifact_versions[-1].content_json["plan"]["title"] == "owner-edited"


def test_stale_version_expiry_reopen_and_scope_side_effect_idempotency() -> None:
    task_id, _ = _create_task("ppt")
    assert _worker().run_once() is True
    first = _interrupt(task_id)
    with _session() as session:
        record = session.get(InterruptRecord, first.id)
        assert record is not None
        record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        assert InterruptService(session).get(record.id) is not None
        assert record.status == "expired"
        reopened = InterruptService(session).reopen(record, actor_id="owner")
        session.commit()
        assert reopened.status == "pending"

        version = session.get(ArtifactVersionRecord, reopened.artifact_version_id)
        assert version is not None
        session.add(
            ApprovalRecord(
                task_id=task_id,
                artifact_version_id=version.id,
                decision="approved",
                reviewer_id="owner",
                decision_sha256=canonical_sha256(
                    {"task_id": task_id, "scope": ApprovalScope.EXPORT.value}
                ),
                scope=ApprovalScope.EXPORT.value,
                action="approve",
                target_paths_json=[],
                idempotency_key=f"export-{task_id}",
            )
        )
        session.flush()
        calls: list[str] = []
        service = InterruptService(session)

        def export_result(label: str, export_id: str) -> dict[str, str]:
            calls.append(label)
            return {"export_id": export_id}

        result = service.execute_side_effect(
            task_id=task_id,
            artifact_version_id=version.id,
            scope=ApprovalScope.EXPORT,
            operation_key="export-once",
            fn=lambda: export_result("called", "export-1"),
        )
        replay = service.execute_side_effect(
            task_id=task_id,
            artifact_version_id=version.id,
            scope=ApprovalScope.EXPORT,
            operation_key="export-once",
            fn=lambda: export_result("called-again", "export-2"),
        )
        assert result == replay == {"export_id": "export-1"}
        assert calls == ["called"]
        session.commit()

        task = session.get(GenerationTask, task_id)
        assert task is not None
        task.active_artifact_version = version.version + 1
        session.commit()
        with pytest.raises(InterruptError, match="STALE_ARTIFACT_VERSION"):
            InterruptService(session).decide(
                record=reopened,
                decision=HumanDecision(
                    decision_id=f"stale-{uuid4()}",
                    task_id=task_id,
                    checkpoint_id=reopened.checkpoint_id,
                    action=DecisionAction.APPROVE,
                    actor_id="owner",
                    idempotency_key=f"stale-{uuid4()}",
                ),
            )


def test_checkpoint_schema_isolated_and_migration_tables_exist() -> None:
    with _session() as session:
        schema = session.scalar(
            text(
                "SELECT schema_name FROM information_schema.schemata "
                "WHERE schema_name = 'coursepilot_checkpoints'"
            )
        )
        assert schema == "coursepilot_checkpoints"
        tables = set(
            session.scalars(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'coursepilot_checkpoints'"
                )
            )
        )
        assert {
            "checkpoint_migrations",
            "checkpoints",
            "checkpoint_blobs",
            "checkpoint_writes",
        } <= tables
