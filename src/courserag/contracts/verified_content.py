from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, JsonValue

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta
from courserag.contracts.retrieval import SourceTier


class VerifiedContentType(StrEnum):
    VERIFIED_QUESTION = "verified_question"
    VERIFIED_ANSWER_EXPLANATION = "verified_answer_explanation"
    VERIFIED_LESSON_FRAGMENT = "verified_lesson_fragment"


class VerifiedContentStatus(StrEnum):
    INDEXED = "indexed"
    REVOKED = "revoked"


class VerifiedContentWriteRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    content_type: VerifiedContentType
    content: dict[str, JsonValue]
    evidence_ids: list[str] = Field(min_length=1)
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
