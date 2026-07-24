from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta


class RetrievalMode(StrEnum):
    DENSE = "dense"
    SPARSE = "sparse"
    HYBRID = "hybrid"


class SourceTier(StrEnum):
    PRIMARY_SOURCE = "primary_source"
    TEACHER_VERIFIED = "teacher_verified"
    EXTERNAL_REFERENCE = "external_reference"
    GENERATED_DRAFT = "generated_draft"


class PageRange(ContractModel):
    start: int = Field(ge=1)
    end: int = Field(ge=1)


class SearchFilters(ContractModel):
    document_ids: list[str] = Field(default_factory=list)
    document_types: list[str] = Field(default_factory=list)
    section_paths: list[list[str]] = Field(default_factory=list)
    page_range: PageRange | None = None
    source_tiers: list[SourceTier] = Field(default_factory=list)


class RetrievalOptions(ContractModel):
    mode: RetrievalMode = RetrievalMode.DENSE
    candidate_k: int = Field(default=30, ge=1)
    rerank_top_n: int = Field(default=8, ge=1)
    return_top_n: int = Field(default=5, ge=1)
    enable_query_rewrite: bool = False
    enable_parent_expansion: bool = False


class SearchRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    retrieval: RetrievalOptions = Field(default_factory=RetrievalOptions)


class ScoreBreakdown(ContractModel):
    dense: float | None = None
    sparse: float | None = None
    fusion: float | None = None
    rerank: float | None = None


class SearchHit(ContractModel):
    rank: int = Field(ge=1)
    chunk_id: str = Field(min_length=1)
    parent_chunk_id: str | None = None
    document_id: str | None = None
    document_version: str = Field(min_length=1)
    document_type: str | None = None
    title: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    text: str
    scores: ScoreBreakdown
    evidence_ids: list[str] = Field(default_factory=list)
    source_tier: SourceTier


class QueryTrace(ContractModel):
    original: str
    normalized: str
    rewrites: list[str] = Field(default_factory=list)


class RetrievalTrace(ContractModel):
    retrieval_config_version: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)


class SearchResponse(ContractModel):
    meta: ResponseMeta
    query: QueryTrace
    hits: list[SearchHit] = Field(default_factory=list)
    retrieval: RetrievalTrace


class ContextPackingOptions(ContractModel):
    max_tokens: int = Field(default=4000, ge=1)
    max_items: int = Field(default=8, ge=1)
    deduplicate: bool = True
    include_neighbor_sections: bool = True
    preserve_evidence_boundaries: bool = True


class ContextRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    search_request: SearchRequest | None = None
    packing: ContextPackingOptions = Field(default_factory=ContextPackingOptions)

    @model_validator(mode="before")
    @classmethod
    def _inherit_outer_search_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        context = RequestContext.model_validate(data.get("context") or {})
        data["context"] = context
        nested = data.get("search_request")
        if isinstance(nested, dict):
            nested_data = dict(nested)
            nested_data.setdefault("course_id", data.get("course_id"))
            nested_data.setdefault("query", data.get("query"))
            if not nested_data.get("context"):
                nested_data["context"] = context
            data["search_request"] = nested_data
        return data

    @model_validator(mode="after")
    def _require_consistent_search_request(self) -> ContextRequest:
        nested = self.search_request
        if nested is None:
            return self
        if nested.course_id != self.course_id:
            raise ValueError("search_request.course_id must match ContextRequest.course_id")
        if nested.query != self.query:
            raise ValueError("search_request.query must match ContextRequest.query")
        if nested.context != self.context:
            raise ValueError("search_request.context must match ContextRequest.context")
        return self


class ContextItem(ContractModel):
    context_item_id: str = Field(min_length=1)
    text: str
    document_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    token_count: int = Field(ge=0)
    truncated: bool = False


class EvidenceSummary(ContractModel):
    document_id: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)


class PackingReport(ContractModel):
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    deduplicated_count: int = Field(ge=0)
    discarded_for_budget: int = Field(ge=0)


class ContextPackage(ContractModel):
    meta: ResponseMeta
    query: str
    purpose: str
    items: list[ContextItem] = Field(default_factory=list)
    token_count: int = Field(ge=0)
    evidence_map: dict[str, EvidenceSummary] = Field(default_factory=dict)
    retrieval_trace_id: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    packing_report: PackingReport
