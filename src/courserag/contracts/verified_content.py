from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta, UTCDateTime
from courserag.contracts.retrieval import SourceTier


class VerifiedContentType(StrEnum):
    VERIFIED_QUESTION = "verified_question"
    VERIFIED_ANSWER_EXPLANATION = "verified_answer_explanation"
    VERIFIED_LESSON_FRAGMENT = "verified_lesson_fragment"


class VerifiedContentStatus(StrEnum):
    PENDING_ENRICHMENT = "pending_enrichment"
    ENRICHED = "enriched"
    ACTIVE = "active"
    INDEXED = "indexed"
    REVOKED = "revoked"
    LEGACY_INCOMPLETE = "legacy_incomplete"


class VerifiedContentWriteRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    content_type: VerifiedContentType
    content: dict[str, JsonValue]
    evidence_ids: list[str] = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    source_tier: Literal[SourceTier.TEACHER_VERIFIED] = SourceTier.TEACHER_VERIFIED
    approved_by: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    approval_record_id: str = Field(min_length=1)


class VerifiedContentWriteResult(ContractModel):
    meta: ResponseMeta
    verified_content_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    status: VerifiedContentStatus
    index_version: str = Field(min_length=1)
    created: bool
    overlay_index_version: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    enrichment_status: VerifiedContentStatus | None = None


class RevokeVerifiedContentRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    verified_content_id: str = Field(min_length=1)
    revoked_by: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class RevokeVerifiedContentResult(ContractModel):
    meta: ResponseMeta
    verified_content_id: str = Field(min_length=1)
    status: VerifiedContentStatus
    revoked: bool
    overlay_index_version: str | None = None


class EnrichmentTriggerReason(StrEnum):
    MANUAL = "manual"
    RECORD_COUNT = "record_count"
    TOKEN_COUNT = "token_count"
    AGE = "age"


class StartEnrichmentBatchRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    actor_id: str = Field(min_length=1)
    manual: bool = False


class EnrichmentBatchResult(ContractModel):
    meta: ResponseMeta
    batch_id: str | None = None
    created: bool
    trigger_reason: EnrichmentTriggerReason | None = None
    item_count: int = Field(default=0, ge=0)
    status: str | None = None
    completed_at: UTCDateTime | None = None
    overlay_index_version: str | None = None
