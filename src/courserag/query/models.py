from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class IntentRoute(StrEnum):
    FACT = "fact"
    DEFINITION = "definition"
    COMPARISON = "comparison"
    PROCEDURE = "procedure"
    EXAMPLE_APPLICATION = "example_application"
    CROSS_SECTION = "cross_section"


class RetrievalStrategy(StrEnum):
    HYBRID = "hybrid_retrieval"
    METADATA_FILTERED = "metadata_filtered_retrieval"
    UNANSWERABLE_AUDIT = "unanswerable_audit"


class StepStatus(StrEnum):
    SUCCEEDED = "succeeded"
    SKIPPED_DISABLED = "skipped_disabled"
    FALLBACK_ORIGINAL = "rewrite_fallback_original"


class QueryStepTrace(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    step: str
    status: StepStatus
    input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_ms: int = Field(ge=0)
    warnings: tuple[str, ...] = ()


class LinkedKnowledgePoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_point_id: str
    name: str
    confidence: float = Field(ge=0, le=1)
    match_method: str
    hard_filter: bool = False


class ParsedFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_ids: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()
    section_terms: tuple[str, ...] = ()
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    knowledge_point_ids: tuple[str, ...] = ()
    source_tiers: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()
    source_fragments: tuple[str, ...] = ()


class QueryState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_query: str
    normalized_query: str
    current_query: str
    explicit_filters: ParsedFilters = Field(default_factory=ParsedFilters)
    linked_knowledge_points: tuple[LinkedKnowledgePoint, ...] = ()
    aliases: tuple[str, ...] = ()
    rewrites: tuple[str, ...] = ()
    intent_route: IntentRoute = IntentRoute.FACT
    intent_rule_id: str = "intent.fact.default.v2"
    intent_reason: str = "default fact route"
    minimum_source_count: int = Field(default=1, ge=1)
    retrieval_strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    required_terms: tuple[str, ...] = ()
    retry_reason: str | None = None
    traces: tuple[QueryStepTrace, ...] = ()
    warnings: tuple[str, ...] = ()


class QueryPipelineProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    normalize: bool = True
    filter_parser: bool = True
    kp_link: bool = True
    alias_expansion: bool = True
    intent_router: bool = True
    retrieval_strategy: bool = True
    multi_query: bool = False
    low_recall_retry: bool = True
    max_rewrites: int = Field(default=3, ge=0, le=3)
    kp_hard_filter_threshold: float = Field(default=0.90, ge=0, le=1)
