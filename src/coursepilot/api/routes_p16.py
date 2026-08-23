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
from coursepilot.exporters.pptx import PPTXVersionedExporter
from coursepilot.integration import StaleCourseRAGContextError, assert_context_binding_current
from coursepilot.models import ArtifactRecord, ArtifactVersionRecord, GenerationTask
from coursepilot.rendering.pptx import render_with_libreoffice
from coursepilot.runtime.interrupts import InterruptError, InterruptService
from coursepilot.schemas.p16_schema import PPTExportV2Request, PPTWritebackV2Request
from courserag.contracts.common import RequestContext
from courserag.contracts.verified_content import VerifiedContentType, VerifiedContentWriteRequest

router = APIRouter(tags=["coursepilot-p16-ppt-effects"])


def _source(task: GenerationTask, version_id: str, session: Session) -> ArtifactVersionRecord:
    version = session.get(ArtifactVersionRecord, version_id)
    artifact = session.get(ArtifactRecord, version.artifact_id) if version else None
    if (
        version is None
        or artifact is None
        or artifact.task_id != task.id
        or artifact.course_id != task.course_id
        or artifact.active_version != version.version
    ):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    return version


@router.post("/tasks/{task_id}/ppt/export", response_model=dict[str, object])
def export_ppt_v2(
    task_id: str,
    payload: PPTExportV2Request,
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
    source = _source(task, payload.artifact_version_id, session)
    if source.content_sha256 != canonical_sha256(payload.artifact.model_dump(mode="json")):
        raise HTTPException(status_code=409, detail="STALE_ARTIFACT_VERSION")
    _stale_preflight(task, source, session)
    key = (
        idempotency_key or hashlib.sha256(f"ppt-export:{task_id}:{source.id}".encode()).hexdigest()
    )
    root = Path(settings.COURSEPILOT_STORAGE_DIR) / "coursepilot_exports" / task_id / key[:16]

    def effect() -> dict[str, object]:
        path = PPTXVersionedExporter().export(payload.artifact, root / "presentation.pptx")
        report = render_with_libreoffice(
            path,
            root / "rendered",
            expected_slide_count=len(payload.artifact.slides),
        )
        if not report.passed:
            raise ValueError("PPT_RENDER_GATE_FAILED")
        return {
            "exported": True,
            "path": str(path),
            "render_report": report.model_dump(mode="json"),
        }

    try:
        result = InterruptService(session).execute_side_effect(
            task_id=task_id,
            artifact_version_id=source.id,
            scope=ApprovalScope.EXPORT,
            operation_key=key,
            fn=effect,
        )
        session.commit()
        return result
    except (InterruptError, ValueError) as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=getattr(exc, "code", str(exc))) from exc


@router.post("/tasks/{task_id}/ppt/writeback", response_model=dict[str, object])
def writeback_ppt_v2(
    task_id: str,
    payload: PPTWritebackV2Request,
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
    source = _source(task, payload.artifact_version_id, session)
    _stale_preflight(task, source, session)
    selected = next(
        (slide for slide in payload.artifact.slides if slide.slide_id == payload.slide_id), None
    )
    if selected is None or not set(payload.evidence_ids) <= {
        c.evidence_id for c in selected.citations
    }:
        raise HTTPException(status_code=409, detail="EVIDENCE_SCOPE_REQUIRED")
    index = next(
        i for i, slide in enumerate(payload.artifact.slides) if slide.slide_id == payload.slide_id
    )
    target_path = (
        f"$.slides[{index}]" if payload.component == "slide" else f"$.slides[{index}].speaker_notes"
    )

    def effect() -> dict[str, object]:
        result = _course_rag_service().write_verified_content(
            VerifiedContentWriteRequest(
                context=RequestContext(),
                course_id=task.course_id,
                content_type=VerifiedContentType.VERIFIED_LESSON_FRAGMENT,
                content=selected.model_dump(mode="json"),
                evidence_ids=payload.evidence_ids,
                approved_by=principal.principal_id,
                task_id=task_id,
                approval_record_id=payload.approval_record_id,
            )
        )
        return {
            "written": True,
            "slide_id": payload.slide_id,
            "result": result.model_dump(mode="json"),
        }

    try:
        result = InterruptService(session).execute_side_effect(
            task_id=task_id,
            artifact_version_id=source.id,
            scope=ApprovalScope.VERIFIED_WRITEBACK,
            operation_key=f"ppt-writeback:{payload.approval_record_id}:{payload.slide_id}:{payload.component}",
            fn=effect,
            approval_record_id=payload.approval_record_id,
            required_target_paths={target_path},
        )
        session.commit()
        return result
    except InterruptError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail=exc.code) from exc


def _course_rag_service():
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
