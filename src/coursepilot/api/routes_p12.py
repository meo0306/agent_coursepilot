from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.security import PrincipalRole, TrustedPrincipal, require_course_role
from core.settings import settings
from coursepilot.api.idempotency import execute_idempotent
from coursepilot.db.session import get_session
from coursepilot.domain import HumanDecision
from coursepilot.domain.common import canonical_sha256
from coursepilot.models import (
    ApprovalRecord,
    ArtifactVersionRecord,
    GenerationTask,
    InterruptRecord,
    ResumeCommandRecord,
)
from coursepilot.runtime.interrupts import InterruptError, InterruptService
from coursepilot.schemas.p12_schema import (
    InterruptDecisionRequest,
    InterruptRead,
    RecoverableTaskCreate,
    ResumeCommandRead,
    ScopeApprovalRequest,
)
from coursepilot.schemas.task_schema import AsyncTaskAccepted
from coursepilot.services.async_task_service import AsyncTaskService, utc_now

router = APIRouter(tags=["coursepilot-recoverable-workflows"])


def principal_from_headers(
    principal_id: Annotated[str | None, Header(alias="X-CoursePilot-Principal-ID")] = None,
    principal_course_id: Annotated[str | None, Header(alias="X-CoursePilot-Course-ID")] = None,
    roles: Annotated[str | None, Header(alias="X-CoursePilot-Roles")] = None,
) -> TrustedPrincipal:
    try:
        return TrustedPrincipal.from_gateway_headers(
            principal_id=principal_id, course_id=principal_course_id, roles=roles
        )
    except (PermissionError, ValueError) as exc:
        raise HTTPException(status_code=403, detail="TRUSTED_IDENTITY_REQUIRED") from exc


def _require_task(task_id: str, session: Session, principal: TrustedPrincipal) -> GenerationTask:
    task = session.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        require_course_role(principal, task.course_id, PrincipalRole.READER)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="COURSE_SCOPE_MISMATCH") from exc
    return task


@router.post("/tasks/recoverable", response_model=AsyncTaskAccepted, status_code=202)
def create_recoverable_task(
    payload: RecoverableTaskCreate,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> AsyncTaskAccepted:
    if not settings.COURSEPILOT_RECOVERABLE_WORKFLOWS_ENABLED:
        raise HTTPException(status_code=503, detail="RECOVERABLE_RUNTIME_UNAVAILABLE")
    try:
        require_course_role(principal, principal.course_id, PrincipalRole.EDITOR)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="EDITOR_ROLE_REQUIRED") from exc
    return execute_idempotent(
        session=session,
        response=response,
        operation="workflow.recoverable.create",
        idempotency_key=idempotency_key,
        request_payload=payload.model_dump(mode="json"),
        fn=lambda: AsyncTaskService(session).enqueue(
            course_id=principal.course_id,
            task_type=payload.task_type,
            workflow_type=payload.workflow_type,
            workflow_mode="recoverable",
            input_params=payload.input_params,
        ),
        response_status=202,
        resource_type="async_task",
        resource_id_field="task_id",
    )


@router.get("/tasks/{task_id}/interrupts", response_model=list[InterruptRead])
def list_interrupts(
    task_id: str,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> list[InterruptRecord]:
    task = _require_task(task_id, session, principal)
    return list(
        session.scalars(
            select(InterruptRecord)
            .where(InterruptRecord.task_id == task.id)
            .order_by(InterruptRecord.created_at)
        )
    )


@router.get("/tasks/{task_id}/interrupts/{interrupt_id}", response_model=InterruptRead)
def get_interrupt(
    task_id: str,
    interrupt_id: str,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> InterruptRecord:
    _require_task(task_id, session, principal)
    record = InterruptService(session).get(interrupt_id)
    if record is None or record.task_id != task_id:
        raise HTTPException(status_code=404, detail="Interrupt not found")
    session.commit()
    return record


@router.post(
    "/tasks/{task_id}/interrupts/{interrupt_id}/decisions", response_model=ResumeCommandRead
)
def decide_interrupt(
    task_id: str,
    interrupt_id: str,
    payload: InterruptDecisionRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> ResumeCommandRecord:
    task = _require_task(task_id, session, principal)
    try:
        require_course_role(principal, task.course_id, PrincipalRole.EDITOR)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="EDITOR_ROLE_REQUIRED") from exc
    record = InterruptService(session).get(interrupt_id)
    if record is None or record.task_id != task_id:
        raise HTTPException(status_code=404, detail="Interrupt not found")
    decision = HumanDecision(
        decision_id=payload.decision_id,
        task_id=task_id,
        checkpoint_id=payload.checkpoint_id,
        action=payload.action,
        feedback=payload.feedback,
        target_paths=payload.target_paths,
        actor_id=principal.principal_id,
        change_mode=payload.change_mode,
        approval_scopes=payload.approval_scopes,
        patch=payload.patch,
        idempotency_key=idempotency_key or payload.decision_id,
    )
    try:
        command = InterruptService(session).decide(record=record, decision=decision)
        session.commit()
        return command
    except InterruptError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.code) from exc


@router.post(
    "/tasks/{task_id}/resume-commands/{command_id}/resume",
    response_model=ResumeCommandRead,
)
def resume_command(
    task_id: str,
    command_id: str,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> ResumeCommandRecord:
    task = _require_task(task_id, session, principal)
    try:
        require_course_role(principal, task.course_id, PrincipalRole.EDITOR)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="EDITOR_ROLE_REQUIRED") from exc
    command = session.get(ResumeCommandRecord, command_id)
    if command is None or command.task_id != task_id:
        raise HTTPException(status_code=404, detail="Resume command not found")
    if command.status == "pending":
        task.status = "running"
        task.worker_id = None
        task.locked_until = utc_now() - timedelta(seconds=1)
        session.commit()
    return command


@router.get("/tasks/{task_id}/resume-commands/{command_id}", response_model=ResumeCommandRead)
def get_resume_command(
    task_id: str,
    command_id: str,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> ResumeCommandRecord:
    _require_task(task_id, session, principal)
    command = session.get(ResumeCommandRecord, command_id)
    if command is None or command.task_id != task_id:
        raise HTTPException(status_code=404, detail="Resume command not found")
    return command


@router.post("/tasks/{task_id}/interrupts/{interrupt_id}/reopen", response_model=InterruptRead)
def reopen_interrupt(
    task_id: str,
    interrupt_id: str,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> InterruptRecord:
    task = _require_task(task_id, session, principal)
    try:
        require_course_role(principal, task.course_id, PrincipalRole.OWNER)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="OWNER_ROLE_REQUIRED") from exc
    record = InterruptService(session).get(interrupt_id)
    if record is None or record.task_id != task_id:
        raise HTTPException(status_code=404, detail="Interrupt not found")
    try:
        reopened = InterruptService(session).reopen(record, actor_id=principal.principal_id)
        session.commit()
        return reopened
    except InterruptError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.code) from exc


@router.post("/tasks/{task_id}/approvals", response_model=dict[str, str])
def create_scope_approval(
    task_id: str,
    payload: ScopeApprovalRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> dict[str, str]:
    task = _require_task(task_id, session, principal)
    minimum = (
        PrincipalRole.OWNER if payload.scope.value == "verified_writeback" else PrincipalRole.EDITOR
    )
    try:
        require_course_role(principal, task.course_id, minimum)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="APPROVAL_ROLE_REQUIRED") from exc
    existing = session.scalar(
        select(ApprovalRecord).where(
            ApprovalRecord.task_id == task_id,
            ApprovalRecord.artifact_version_id == payload.artifact_version_id,
            ApprovalRecord.scope == payload.scope.value,
            ApprovalRecord.idempotency_key == (idempotency_key or payload.operation_key),
        )
    )
    if existing is not None:
        return {"approval_id": existing.id, "scope": str(existing.scope)}
    if session.get(ArtifactVersionRecord, payload.artifact_version_id) is None:
        raise HTTPException(status_code=409, detail="STALE_INTERRUPT")
    record = ApprovalRecord(
        task_id=task_id,
        artifact_version_id=payload.artifact_version_id,
        decision="approved" if payload.approved else "rejected",
        reviewer_id=principal.principal_id,
        notes=None,
        decision_sha256=canonical_sha256(
            {
                "task_id": task_id,
                "artifact_version_id": payload.artifact_version_id,
                "scope": payload.scope.value,
                "operation_key": payload.operation_key,
            }
        ),
        interrupt_id=None,
        checkpoint_id=None,
        decision_id=None,
        scope=payload.scope.value,
        action="approve" if payload.approved else "reject",
        target_paths_json=list(payload.target_paths),
        idempotency_key=idempotency_key or payload.operation_key,
        request_sha256=None,
        expires_at=None,
        superseded_by_id=None,
    )
    session.add(record)
    session.commit()
    return {"approval_id": record.id, "scope": str(record.scope)}
