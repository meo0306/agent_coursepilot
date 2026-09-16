from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.http_schema import API_PREFIX
from courserag.api.principal import trusted_principal
from courserag.api.retrieval_qa import _api_error
from courserag.contracts import (
    ContextBindingValidationRequest,
    ContextBindingValidationResponse,
    ResponseMeta,
)
from courserag.persistence.models import (
    DocumentVersionRecord,
    EvidenceRecord,
    KnowledgeBaseRecord,
    ParsedDocumentRecord,
    SourceDocumentRecord,
)
from courserag.security import PrincipalRole, TrustedPrincipal, require_course_role

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Context Binding"])


@router.post("/context-bindings/validate", response_model=ContextBindingValidationResponse)
@router.post(
    "/knowledge-bases/{course_id}/context-bindings/validate",
    response_model=ContextBindingValidationResponse,
)
def validate_binding(
    payload: ContextBindingValidationRequest,
    session: Annotated[Session, Depends(get_session)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    course_id: str | None = None,
) -> ContextBindingValidationResponse:
    if course_id is not None and payload.course_id != course_id:
        raise _api_error(payload.context, ValueError("Path course differs from payload"))
    try:
        require_course_role(principal, payload.course_id, PrincipalRole.READER)
    except PermissionError as exc:
        raise _api_error(payload.context, exc) from exc
    kb = (
        session.query(KnowledgeBaseRecord)
        .filter(KnowledgeBaseRecord.course_id == payload.course_id)
        .one_or_none()
    )
    if kb is None:
        raise _api_error(payload.context, ValueError("Knowledge base not found"))
    status = "compatible"
    changed: list[str] = []
    reason: str | None = None
    if kb.active_index_version_id != payload.index_version:
        status, reason = "stale_primary_index", "Primary index version changed"
    elif kb.active_verified_index_version_id != payload.verified_overlay_version:
        status, reason = "stale_verified_overlay", "Verified overlay version changed"
    else:
        evidence_rows = session.execute(
            select(
                EvidenceRecord.id,
                EvidenceRecord.content_sha256,
                SourceDocumentRecord.knowledge_base_id,
            )
            .join(
                ParsedDocumentRecord,
                ParsedDocumentRecord.id == EvidenceRecord.parsed_document_id,
            )
            .join(
                DocumentVersionRecord,
                DocumentVersionRecord.id == ParsedDocumentRecord.document_version_id,
            )
            .join(
                SourceDocumentRecord,
                SourceDocumentRecord.id == DocumentVersionRecord.source_document_id,
            )
            .where(EvidenceRecord.id.in_(payload.evidence_versions))
        ).all()
        evidence_by_id = {row.id: row for row in evidence_rows}
        for evidence_id, expected_hash in payload.evidence_versions.items():
            row = evidence_by_id.get(evidence_id)
            if row is None:
                changed.append(evidence_id)
            elif row.knowledge_base_id != kb.id:
                status, reason = "cross_course_evidence", "Evidence belongs to another course"
                changed.append(evidence_id)
            elif row.content_sha256 != expected_hash:
                changed.append(evidence_id)
        if changed and status == "compatible":
            status, reason = "changed_evidence", "Evidence content hash changed or is missing"
    return ContextBindingValidationResponse(
        meta=ResponseMeta.from_context(payload.context),
        status=status,
        stale=status != "compatible",
        changed_evidence_ids=changed,
        reason=reason,
    )
