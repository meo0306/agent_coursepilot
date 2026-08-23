from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.security import PrincipalRole, TrustedPrincipal, require_course_role
from core.settings import settings
from coursepilot.api.routes_p12 import principal_from_headers
from coursepilot.application.lesson_workflow_service import (
    LessonWorkflowError,
    LessonWorkflowService,
)
from coursepilot.db.session import get_session
from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.interrupts import ApprovalScope
from coursepilot.exporters.lesson_versioned_exporter import VersionedLessonDocxExporter
from coursepilot.integration import StaleCourseRAGContextError, assert_context_binding_current
from coursepilot.models import ArtifactRecord, ArtifactVersionRecord, GenerationTask
from coursepilot.ports.courserag import CourseRAGServicePort
from coursepilot.runtime.interrupts import InterruptError, InterruptService
from coursepilot.schemas.p14_schema import LessonExportRequest, LessonWritebackRequest

router = APIRouter(tags=["coursepilot-p14-lesson-effects"])


def _owned_version(
    task: GenerationTask, version_id: str, session: Session
) -> ArtifactVersionRecord:
    version = session.get(ArtifactVersionRecord, version_id)
    if version is None:
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    artifact = session.get(ArtifactRecord, version.artifact_id)
    if artifact is None or artifact.task_id != task.id or artifact.course_id != task.course_id:
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    return version


@router.post("/tasks/{task_id}/lesson/export", response_model=dict[str, object])
def export_lesson_version(
    task_id: str,
    payload: LessonExportRequest,
    response: Response,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    task = session.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        require_course_role(principal, task.course_id, PrincipalRole.EDITOR)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="EDITOR_ROLE_REQUIRED") from exc
    source = _owned_version(task, payload.artifact_version_id, session)
    if source.content_sha256 != canonical_sha256(payload.artifact.model_dump(mode="json")):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    _stale_preflight(task, source, session)
    operation_key = (
        idempotency_key
        or hashlib.sha256(
            f"export:{task_id}:{payload.artifact_version_id}:{payload.output_filename}".encode()
        ).hexdigest()
    )
    root = Path(settings.COURSEPILOT_STORAGE_DIR) / "coursepilot_exports" / task_id
    safe_name = Path(payload.output_filename).name or "lesson.docx"
    output_path = root / f"{operation_key[:16]}-{safe_name}"

    def effect() -> dict[str, object]:
        root.mkdir(parents=True, exist_ok=True)
        exported = VersionedLessonDocxExporter().export(payload.artifact, output_path)
        artifact = session.get(ArtifactRecord, source.artifact_id)
        if artifact is None:
            raise InterruptError("STALE_ARTIFACT_VERSION")
        latest = (
            session.scalar(
                select(ArtifactVersionRecord.version)
                .where(ArtifactVersionRecord.artifact_id == artifact.id)
                .order_by(ArtifactVersionRecord.version.desc())
            )
            or source.version
        )
        exported_version = ArtifactVersionRecord(
            artifact_id=artifact.id,
            version=int(latest) + 1,
            schema_version="coursepilot.lesson.export.v1",
            content_json=payload.artifact.model_dump(mode="json"),
            storage_kind="file",
            storage_uri=str(exported.relative_to(Path(settings.COURSEPILOT_STORAGE_DIR))),
            content_sha256=canonical_sha256(payload.artifact.model_dump(mode="json")),
            created_by=principal.principal_id,
            source_run_id=None,
        )
        session.add(exported_version)
        artifact.active_version = exported_version.version
        session.flush()
        return {
            "exported": True,
            "artifact_version_id": exported_version.id,
            "storage_uri": exported_version.storage_uri,
        }

    try:
        result = InterruptService(session).execute_side_effect(
            task_id=task_id,
            artifact_version_id=source.id,
            scope=ApprovalScope.EXPORT,
            operation_key=operation_key,
            fn=effect,
        )
        session.commit()
        return result
    except InterruptError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.code) from exc


@router.post("/tasks/{task_id}/lesson/writeback", response_model=dict[str, object])
def write_lesson_fragment(
    task_id: str,
    payload: LessonWritebackRequest,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    task = session.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        require_course_role(principal, task.course_id, PrincipalRole.OWNER)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="OWNER_ROLE_REQUIRED") from exc
    source = _owned_version(task, payload.artifact_version_id, session)
    if source.content_sha256 != canonical_sha256(payload.artifact.model_dump(mode="json")):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    _stale_preflight(task, source, session)
    operation_key = f"writeback:{payload.approval_record_id}:{payload.json_path}"

    def effect() -> dict[str, object]:
        try:
            result = LessonWorkflowService(_course_rag_service()).write_verified_path(
                artifact=payload.artifact,
                json_path=payload.json_path,
                evidence_ids=payload.evidence_ids,
                approved_by=principal.principal_id,
                task_id=task_id,
                approval_record_id=payload.approval_record_id,
            )
        except LessonWorkflowError as exc:
            raise InterruptError(str(exc)) from exc
        return {"written": True, "result": result}

    try:
        result = InterruptService(session).execute_side_effect(
            task_id=task_id,
            artifact_version_id=source.id,
            scope=ApprovalScope.VERIFIED_WRITEBACK,
            operation_key=operation_key,
            fn=effect,
        )
        session.commit()
        return result
    except InterruptError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.code) from exc


def _course_rag_service() -> CourseRAGServicePort:
    """Dependency seam kept local; deployment wires the existing CourseRAG adapter."""
    from coursepilot.services.courserag_runtime import get_courserag_service

    return get_courserag_service()


def _stale_preflight(task: GenerationTask, source: ArtifactVersionRecord, session: Session) -> None:
    try:
        assert_context_binding_current(
            session=session,
            source_version=source,
            course_id=task.course_id,
            service=_course_rag_service(),
        )
    except StaleCourseRAGContextError as exc:
        task.status = "needs_review"
        session.commit()
        raise HTTPException(status_code=409, detail=exc.code) from exc
