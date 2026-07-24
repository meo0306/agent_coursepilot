from __future__ import annotations

from pydantic import Field

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta
from courserag.contracts.retrieval import SourceTier


class GetEvidenceRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    evidence_id: str = Field(min_length=1)


class BatchGetEvidenceRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class EvidenceRecord(ContractModel):
    meta: ResponseMeta
    evidence_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    block_ids: list[str] = Field(default_factory=list)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    evidence_text: str
    source_tier: SourceTier
    content_hash: str = Field(min_length=1)


class EvidenceBatch(ContractModel):
    meta: ResponseMeta
    records: list[EvidenceRecord] = Field(default_factory=list)
    missing_ids: list[str] = Field(default_factory=list)
