from __future__ import annotations

from enum import StrEnum

from pydantic import Field, JsonValue

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta
from courserag.contracts.retrieval import RetrievalOptions, SearchFilters


class AnswerType(StrEnum):
    FACTOID = "factoid"
    LIST = "list"
    EXPLANATORY = "explanatory"
    COMPARISON = "comparison"
    PROCEDURE = "procedure"


class AnswerStatus(StrEnum):
    ANSWERED = "answered"
    ABSTAINED_INSUFFICIENT_EVIDENCE = "abstained_insufficient_evidence"
    ABSTAINED_OUT_OF_SCOPE = "abstained_out_of_scope"
    FAILED = "failed"


class AnsweringOptions(ContractModel):
    max_answer_tokens: int = Field(default=600, ge=1)
    require_citations: bool = True
    allow_abstention: bool = True
    citation_style: str = "evidence_id"
    answer_shape: AnswerType | None = None


class QARequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    retrieval: RetrievalOptions = Field(default_factory=RetrievalOptions)
    answering: AnsweringOptions = Field(default_factory=AnsweringOptions)


class AnswerClaim(ContractModel):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    validation_status: str = "valid"


class Citation(ContractModel):
    evidence_id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    section_path: list[str] = Field(default_factory=list)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class ModelReference(ContractModel):
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)


class QAResponse(ContractModel):
    meta: ResponseMeta
    question: str
    answer_status: AnswerStatus
    answer: str | None = None
    answer_type: AnswerType | None = None
    list_items: list[str] = Field(default_factory=list)
    claims: list[AnswerClaim] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    context_package_id: str | None = None
    retrieval_trace_id: str | None = None
    model: ModelReference | None = None
    qa_run_id: str | None = None
    used_evidence_ids: list[str] = Field(default_factory=list)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    validation_summary: dict[str, JsonValue] = Field(default_factory=dict)
