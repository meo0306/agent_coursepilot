from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, JsonValue, model_validator

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
    document_version_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    index_version: str | None = None
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


class QueryProcessingOptions(ContractModel):
    enabled: bool = False
    profile_version: str | None = None
    disabled_steps: list[str] = Field(default_factory=list)


class SearchRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    filters: SearchFilters = Field(default_factory=SearchFilters)
    retrieval: RetrievalOptions = Field(default_factory=RetrievalOptions)
    query_processing: QueryProcessingOptions = Field(default_factory=QueryProcessingOptions)


class ScoreBreakdown(ContractModel):
    dense: float | None = None
    sparse: float | None = None
    fusion: float | None = None
    rerank: float | None = None


class RankBreakdown(ContractModel):
    dense: int | None = Field(default=None, ge=1)
    sparse: int | None = Field(default=None, ge=1)
    fusion: int | None = Field(default=None, ge=1)
    rerank: int | None = Field(default=None, ge=1)


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
    ranks: RankBreakdown = Field(default_factory=RankBreakdown)
    evidence_ids: list[str] = Field(default_factory=list)
    source_tier: SourceTier


class QueryTrace(ContractModel):
    original: str
    normalized: str
    rewrites: list[str] = Field(default_factory=list)
    step_trace: list[dict[str, JsonValue]] = Field(default_factory=list)
    parsed_filters: dict[str, JsonValue] = Field(default_factory=dict)
    linked_knowledge_points: list[dict[str, JsonValue]] = Field(default_factory=list)
    intent_route: str | None = None
    intent_rule_id: str | None = None
    intent_reason: str | None = None
    minimum_source_count: int = Field(default=1, ge=1)
    retrieval_strategy: str | None = None
    retry_reason: str | None = None


class RetrievalTrace(ContractModel):
    retrieval_config_version: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    candidate_count: int = Field(ge=0)
    returned_count: int = Field(ge=0)
    run_id: str | None = None
    provider: str | None = None
    model: str | None = None
    manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    stage_latency_ms: dict[str, int] = Field(default_factory=dict)
    fallback_applied: bool = False
    warnings: list[str] = Field(default_factory=list)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    debug_trace: dict[str, JsonValue] = Field(default_factory=dict)


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


class ContextEvidenceSegment(ContractModel):
    evidence_id: str = Field(min_length=1)
    text: str
    ordinal: int = Field(ge=0)
    search_hit_rank: int | None = Field(default=None, ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ContextItem(ContractModel):
    context_item_id: str = Field(min_length=1)
    text: str
    document_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_segments: list[ContextEvidenceSegment] = Field(default_factory=list)
    token_count: int = Field(ge=0)
    truncated: bool = False
    expansion_source: str = "retrieval"
    search_hit_rank: int | None = Field(default=None, ge=1)
    evidence_ordinal: int | None = Field(default=None, ge=0)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")


class EvidenceSummary(ContractModel):
    evidence_id: str | None = None
    document_id: str | None = None
    document_version_id: str | None = None
    section_id: str | None = None
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    page_bboxes: list[dict[str, JsonValue]] = Field(default_factory=list)
    source_spans: list[dict[str, JsonValue]] = Field(default_factory=list)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    source_mode: str | None = None
    warning_codes: list[str] = Field(default_factory=list)


class PackingReport(ContractModel):
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    selected_evidence_count: int = Field(default=0, ge=0)
    deduplicated_count: int = Field(ge=0)
    discarded_for_budget: int = Field(ge=0)
    discarded_for_item_limit: int = Field(default=0, ge=0)
    discarded_for_token_limit: int = Field(default=0, ge=0)
    oversized_evidence_count: int = Field(default=0, ge=0)
    parent_expansion_count: int = Field(default=0, ge=0)
    neighbor_expansion_count: int = Field(default=0, ge=0)
    core_selected_count: int = Field(default=0, ge=0)
    expansion_selected_count: int = Field(default=0, ge=0)
    selected_by_hit_rank: dict[str, int] = Field(default_factory=dict)
    token_budget: int | None = Field(default=None, ge=1)
    token_count: int = Field(default=0, ge=0)
    tokenizer_id: str | None = None
    tokenizer_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    warnings: list[str] = Field(default_factory=list)


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
    context_package_id: str | None = None
    result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
