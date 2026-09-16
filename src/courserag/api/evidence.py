from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from coursepilot.db.session import get_session
from courserag.api.http_schema import API_PREFIX
from courserag.api.retrieval_qa import _api_error, _request_context
from courserag.contracts import (
    BatchGetEvidenceRequest,
    EvidenceBatch,
    EvidenceRecord,
    RequestContext,
    ResponseMeta,
    SourceTier,
)
from courserag.persistence.models import (
    DocumentVersionRecord,
    ParsedDocumentRecord,
    SourceDocumentRecord,
)
from courserag.persistence.models import (
    EvidenceRecord as EvidenceRecordModel,
)
from courserag.persistence.repositories import CourseRAGRepository

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Evidence"])


def _to_contract(
    record: EvidenceRecordModel, context: RequestContext, session: Session
) -> EvidenceRecord:
    evidence = record
    version_row = session.scalar(
        select(DocumentVersionRecord)
        .join(
            ParsedDocumentRecord,
            ParsedDocumentRecord.document_version_id == DocumentVersionRecord.id,
        )
        .where(ParsedDocumentRecord.id == evidence.parsed_document_id)
    )
    source = (
        session.get(SourceDocumentRecord, version_row.source_document_id)
        if version_row is not None
        else None
    )
    source_tier = (
        SourceTier(source.source_tier)
        if source and source.source_tier in SourceTier._value2member_map_
        else SourceTier.PRIMARY_SOURCE
    )
    return EvidenceRecord(
        meta=ResponseMeta.from_context(context),
        evidence_id=evidence.id,
        document_id=evidence.parsed_document_id,
        document_version=version_row.id if version_row is not None else "unknown",
        section_path=[],
        block_ids=[evidence.block_id] if evidence.block_id else [],
        char_start=evidence.char_start or 0,
        char_end=evidence.char_end or len(evidence.text),
        evidence_text=evidence.text,
        source_tier=source_tier,
        content_hash=evidence.content_sha256,
    )


@router.get("/evidence/{evidence_id}", response_model=EvidenceRecord)
def get_evidence(
    evidence_id: str, session: Annotated[Session, Depends(get_session)]
) -> EvidenceRecord:
    context = _request_context()
    record = CourseRAGRepository(session).get_evidence(evidence_id)
    if record is None:
        raise _api_error(context, ValueError("Evidence not found"))
    return _to_contract(record, context, session)


@router.post("/evidence/batch", response_model=EvidenceBatch)
def batch_evidence(
    payload: BatchGetEvidenceRequest, session: Annotated[Session, Depends(get_session)]
) -> EvidenceBatch:
    records = []
    missing = []
    repository = CourseRAGRepository(session)
    for evidence_id in payload.evidence_ids:
        record = repository.get_evidence(evidence_id)
        if record is None:
            missing.append(evidence_id)
        else:
            records.append(_to_contract(record, payload.context, session))
    return EvidenceBatch(
        meta=ResponseMeta.from_context(payload.context), records=records, missing_ids=missing
    )
