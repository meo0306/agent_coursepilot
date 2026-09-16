from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.http_schema import API_PREFIX
from courserag.api.principal import trusted_principal
from courserag.api.retrieval_qa import _api_error, _bind_context, _request_context
from courserag.contracts import (
    BuildJob,
    BuildProgress,
    BuildStatus,
    DeleteDocumentRequest,
    DeleteDocumentResult,
    DocumentDescriptor,
    DocumentPage,
    DocumentStatus,
    DocumentSummary,
    RegisterDocumentRequest,
    RegisterDocumentResponse,
    ResponseMeta,
    StartBuildRequest,
)
from courserag.persistence.models import (
    BuildJobRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    SourceDocumentRecord,
)
from courserag.security import PrincipalRole, TrustedPrincipal, require_course_role

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Documents"])


def _kb(session: Session, course_id: str) -> KnowledgeBaseRecord:
    value = session.scalar(
        select(KnowledgeBaseRecord).where(KnowledgeBaseRecord.course_id == course_id)
    )
    if value is None:
        raise ValueError("Knowledge base not found")
    return value


@router.post("/knowledge-bases/{course_id}/documents", response_model=RegisterDocumentResponse)
def register_document(
    course_id: str,
    payload: RegisterDocumentRequest,
    headers: Annotated[object, Depends(_request_context)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    session: Annotated[Session, Depends(get_session)],
) -> RegisterDocumentResponse:
    _bind_context(payload, headers)  # type: ignore[arg-type]
    try:
        require_course_role(principal, course_id, PrincipalRole.EDITOR)
        if payload.course_id != course_id:
            raise ValueError("Path course differs from payload")
        kb = _kb(session, course_id)
        source = SourceDocumentRecord(
            knowledge_base_id=kb.id,
            filename=payload.file.filename,
            document_type=payload.document_type,
            legacy_document_id=payload.file.filename,
            status="registered",
            source_tier="primary_source",
        )
        session.add(source)
        session.flush()
        version = DocumentVersionRecord(
            source_document_id=source.id,
            version_number=1,
            content_sha256=payload.file.sha256,
            object_uri=payload.file.object_uri,
            mime_type=payload.file.mime_type,
            size_bytes=payload.file.size_bytes,
            status="registered",
        )
        session.add(version)
        session.flush()
        source.current_version_id = version.id
        session.commit()
        return RegisterDocumentResponse(
            meta=ResponseMeta.from_context(payload.context),
            document=DocumentDescriptor(
                document_id=source.id,
                document_version=version.id,
                status=DocumentStatus.REGISTERED,
                content_hash=version.content_sha256,
            ),
        )
    except Exception as exc:
        session.rollback()
        raise _api_error(payload.context, exc) from exc


@router.post("/documents/{document_id}/builds", response_model=BuildJob, status_code=202)
def start_build(
    document_id: str,
    payload: StartBuildRequest,
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    session: Annotated[Session, Depends(get_session)],
) -> BuildJob:
    try:
        require_course_role(principal, payload.course_id, PrincipalRole.EDITOR)
        kb = _kb(session, payload.course_id)
        source = session.get(SourceDocumentRecord, document_id)
        if source is None or source.knowledge_base_id != kb.id:
            raise ValueError("Document not found")
        request_hash = hashlib.sha256(
            payload.model_dump_json(exclude={"context"}).encode()
        ).hexdigest()
        existing = session.scalar(
            select(BuildJobRecord).where(
                BuildJobRecord.knowledge_base_id == kb.id,
                BuildJobRecord.request_hash == request_hash,
            )
        )
        if existing is None:
            existing = BuildJobRecord(
                knowledge_base_id=kb.id,
                request_hash=request_hash,
                build_mode=payload.build_mode.value,
                force_rebuild=payload.force_rebuild,
                status="queued",
            )
            session.add(existing)
            session.commit()
            session.refresh(existing)
        now = existing.updated_at or existing.created_at or datetime.now(UTC)
        return BuildJob(
            meta=ResponseMeta.from_context(payload.context),
            job_id=existing.id,
            course_id=payload.course_id,
            status=BuildStatus(existing.status),
            progress=BuildProgress(
                completed_units=100 if existing.status == "succeeded" else 0,
                total_units=100,
                percent=100 if existing.status == "succeeded" else 0,
            ),
            document_versions={source.id: source.current_version_id or ""},
            created_at=existing.created_at,
            updated_at=now,
        )
    except Exception as exc:
        session.rollback()
        raise _api_error(payload.context, exc) from exc


@router.get("/builds/{job_id}", response_model=BuildJob)
def get_build(job_id: str, session: Annotated[Session, Depends(get_session)]) -> BuildJob:
    job = session.get(BuildJobRecord, job_id)
    context = _request_context()
    if job is None:
        raise _api_error(context, ValueError("Build job not found"))
    knowledge_base = session.get(KnowledgeBaseRecord, job.knowledge_base_id)
    if knowledge_base is None:
        raise _api_error(context, ValueError("Knowledge base not found"))
    return BuildJob(
        meta=ResponseMeta.from_context(context),
        job_id=job.id,
        course_id=knowledge_base.course_id,
        status=BuildStatus(job.status),
        progress=BuildProgress(completed_units=0, total_units=100, percent=0),
        created_at=job.created_at,
        updated_at=job.updated_at or job.created_at,
    )


@router.get("/knowledge-bases/{course_id}/documents", response_model=DocumentPage)
def list_documents(
    course_id: str, session: Annotated[Session, Depends(get_session)]
) -> DocumentPage:
    context = _request_context()
    kb = _kb(session, course_id)
    rows = list(
        session.scalars(
            select(SourceDocumentRecord)
            .where(SourceDocumentRecord.knowledge_base_id == kb.id)
            .order_by(SourceDocumentRecord.id)
        )
    )
    return DocumentPage(
        meta=ResponseMeta.from_context(context),
        documents=[
            DocumentSummary(
                document_id=row.id,
                course_id=course_id,
                filename=row.filename,
                document_type=row.document_type,
                status=DocumentStatus(row.status),
                document_version=row.current_version_id or "unversioned",
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row in rows
        ],
    )


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResult)
def delete_document(
    document_id: str,
    payload: DeleteDocumentRequest,
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    session: Annotated[Session, Depends(get_session)],
) -> DeleteDocumentResult:
    try:
        require_course_role(principal, payload.course_id, PrincipalRole.EDITOR)
        source = session.get(SourceDocumentRecord, document_id)
        if source is None or source.knowledge_base_id != _kb(session, payload.course_id).id:
            raise ValueError("Document not found")
        source.status = "deleted"
        session.commit()
        return DeleteDocumentResult(
            meta=ResponseMeta.from_context(payload.context), document_id=document_id, deleted=True
        )
    except Exception as exc:
        session.rollback()
        raise _api_error(payload.context, exc) from exc
