from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from core.security import PrincipalRole, TrustedPrincipal, require_course_role
from core.settings import settings
from coursepilot.api.routes_p12 import principal_from_headers
from coursepilot.db.session import get_session
from coursepilot.domain.common import canonical_sha256
from coursepilot.domain.interrupts import ApprovalScope
from coursepilot.exporters.exam_versioned_exporter import ExamVersionedExporter
from coursepilot.integration import StaleCourseRAGContextError, assert_context_binding_current
from coursepilot.models import ArtifactRecord, ArtifactVersionRecord, GenerationTask
from coursepilot.ports.courserag import CourseRAGServicePort
from coursepilot.runtime.interrupts import InterruptError, InterruptService
from coursepilot.schemas.p15_schema import ExamExportV2Request, ExamWritebackV2Request
from courserag.contracts.common import RequestContext
from courserag.contracts.verified_content import VerifiedContentType, VerifiedContentWriteRequest

router = APIRouter(tags=["coursepilot-p15-exam-effects"])


def _version(task: GenerationTask, version_id: str, session: Session) -> ArtifactVersionRecord:
    version = session.get(ArtifactVersionRecord, version_id)
    artifact = session.get(ArtifactRecord, version.artifact_id) if version else None
    if (
        version is None
        or artifact is None
        or artifact.task_id != task.id
        or artifact.course_id != task.course_id
    ):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    if artifact.active_version != version.version:
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    return version


@router.post("/tasks/{task_id}/exam/export", response_model=dict[str, object])
def export_exam_v2(
    task_id: str,
    payload: ExamExportV2Request,
    principal: TrustedPrincipal = Depends(principal_from_headers),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> dict[str, object]:
    task = session.get(GenerationTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    try:
        require_course_role(principal, task.course_id, PrincipalRole.EDITOR)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail="EDITOR_ROLE_REQUIRED") from exc
    source = _version(task, payload.artifact_version_id, session)
    if source.content_sha256 != canonical_sha256(payload.artifact.model_dump(mode="json")):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    _stale_preflight(task, source, session)
    operation_key = (
        idempotency_key or hashlib.sha256(f"exam-export:{task_id}:{source.id}".encode()).hexdigest()
    )
    root = (
        Path(settings.COURSEPILOT_STORAGE_DIR)
        / "coursepilot_exports"
        / task_id
        / operation_key[:16]
    )

    def effect() -> dict[str, object]:
        paths = ExamVersionedExporter().export(payload.artifact, root)
        return {"exported": True, "files": {role: str(path) for role, path in paths.items()}}

    try:
        result = InterruptService(session).execute_side_effect(
            task_id=task_id,
            artifact_version_id=source.id,
            scope=ApprovalScope.EXPORT,
            operation_key=operation_key,
            fn=effect,
            # Export approval is intentionally a scope-level approval.
        )
        session.commit()
        return result
    except (InterruptError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=getattr(exc, "code", str(exc))) from exc


@router.post("/tasks/{task_id}/exam/writeback", response_model=dict[str, object])
def writeback_exam_question(
    task_id: str,
    payload: ExamWritebackV2Request,
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
    source = _version(task, payload.artifact_version_id, session)
    if source.content_sha256 != canonical_sha256(payload.artifact.model_dump(mode="json")):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    _stale_preflight(task, source, session)
    selected_index = next(
        (
            index
            for index, q in enumerate(payload.artifact.questions)
            if q.question_id == payload.question_id
        ),
        None,
    )
    selected = payload.artifact.questions[selected_index] if selected_index is not None else None
    if selected is None or not set(payload.evidence_ids) <= set(selected.evidence_ids):
        raise HTTPException(status_code=409, detail="EVIDENCE_SCOPE_REQUIRED")
    operation_key = (
        f"exam-writeback:{payload.approval_record_id}:{payload.question_id}:{payload.component}"
    )
    question_path = f"$.questions[{selected_index}]"
    target_paths = {
        question_path if payload.component == "question" else f"{question_path}.explanation"
    }

    def effect() -> dict[str, object]:
        content = {
            "question_id": selected.question_id,
            "question_number": selected.question_number,
            "stem": selected.stem,
            "options": selected.options,
            "answer": selected.answer,
            "explanation": selected.explanation,
            "knowledge_point_ids": selected.knowledge_point_ids,
            "evidence_ids": selected.evidence_ids,
        }
        if payload.component == "explanation":
            content = {
                "question_id": selected.question_id,
                "answer": selected.answer,
                "explanation": selected.explanation,
                "knowledge_point_ids": selected.knowledge_point_ids,
                "evidence_ids": selected.evidence_ids,
            }
            content_type = VerifiedContentType.VERIFIED_ANSWER_EXPLANATION
        else:
            content_type = VerifiedContentType.VERIFIED_QUESTION
        result = _course_rag_service().write_verified_content(
            VerifiedContentWriteRequest(
                context=RequestContext(),
                course_id=task.course_id,
                content_type=content_type,
                content=content,
                evidence_ids=payload.evidence_ids,
                knowledge_point_ids=selected.knowledge_point_ids,
                approved_by=principal.principal_id,
                task_id=task_id,
                approval_record_id=payload.approval_record_id,
            )
        )
        return {
            "written": True,
            "question_id": payload.question_id,
            "component": payload.component,
            "result": result.model_dump(mode="json"),
        }

    try:
        result = InterruptService(session).execute_side_effect(
            task_id=task_id,
            artifact_version_id=source.id,
            scope=ApprovalScope.VERIFIED_WRITEBACK,
            operation_key=operation_key,
            fn=effect,
            approval_record_id=payload.approval_record_id,
            required_target_paths=target_paths,
        )
        session.commit()
        return result
    except InterruptError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.code) from exc


def _course_rag_service() -> CourseRAGServicePort:
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
