from __future__ import annotations

from collections.abc import Hashable, Sequence
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta
from courserag.contracts.retrieval import ContextPackage, SourceTier


class GenerationArtifactType(StrEnum):
    LESSON = "lesson"
    EXAM = "exam"
    PPT = "ppt"


class GenerationSemanticRole(StrEnum):
    FACT = "fact"
    DEFINITION = "definition"
    BOUNDARY = "boundary"
    PRINCIPLE = "principle"
    RELATION = "relation"
    PROCESS = "process"
    COMPARISON = "comparison"
    EXAMPLE = "example"
    COUNTEREXAMPLE = "counterexample"
    APPLICATION_CONTEXT = "application_context"


class GenerationMaterialType(StrEnum):
    FORMULA = "formula"
    TABLE = "table"
    NUMERIC = "numeric"
    CASE = "case"
    VISUAL_RELATIONSHIP = "visual_relationship"


class ContextAdequacyStatus(StrEnum):
    ADEQUATE = "adequate"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    UNRESOLVABLE = "unresolvable"


class KnowledgePointCoverageRequirement(ContractModel):
    knowledge_point_id: str = Field(min_length=1)
    minimum_semantic_units: int = Field(ge=1)


class GenerationSemanticRequirement(ContractModel):
    requirement_id: str = Field(min_length=1, max_length=160)
    minimum_count: int = Field(ge=1)
    roles: list[GenerationSemanticRole] = Field(default_factory=list)
    material_types: list[GenerationMaterialType] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    required: bool = True

    @model_validator(mode="after")
    def validate_requirement(self) -> GenerationSemanticRequirement:
        if not self.roles and not self.material_types:
            raise ValueError("semantic requirement needs a role or material type")
        _require_sorted_unique(self.roles, "roles")
        _require_sorted_unique(self.material_types, "material_types")
        _require_sorted_unique(self.knowledge_point_ids, "knowledge_point_ids")
        return self


class GenerationContextBoundary(ContractModel):
    required_index_version: str | None = Field(default=None, min_length=1)
    required_overlay_version: str | None = Field(default=None, min_length=1)
    allowed_source_tiers: list[SourceTier] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    document_version_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_boundary(self) -> GenerationContextBoundary:
        _require_sorted_unique(self.allowed_source_tiers, "allowed source tiers")
        _require_sorted_unique(self.document_ids, "document IDs")
        _require_sorted_unique(self.document_version_ids, "document version IDs")
        return self


class GenerationContextRequirements(ContractModel):
    contract_version: Literal["v1"] = "v1"
    artifact_type: GenerationArtifactType
    target_unit_count: int = Field(ge=1)
    knowledge_point_requirements: list[KnowledgePointCoverageRequirement] = Field(
        default_factory=list
    )
    semantic_requirements: list[GenerationSemanticRequirement] = Field(default_factory=list)
    minimum_distinct_sources: int = Field(ge=1)
    minimum_semantic_units: int = Field(ge=1)
    max_context_tokens: int = Field(default=4000, ge=1)
    max_context_items: int = Field(default=8, ge=1)
    supplement_round: int = Field(default=0, ge=0)
    max_supplement_rounds: int = Field(default=1, ge=0)
    boundary: GenerationContextBoundary = Field(default_factory=GenerationContextBoundary)

    @model_validator(mode="after")
    def validate_requirements(self) -> GenerationContextRequirements:
        if self.supplement_round > self.max_supplement_rounds:
            raise ValueError("supplement round exceeds configured maximum")
        kp_ids = [item.knowledge_point_id for item in self.knowledge_point_requirements]
        _require_sorted_unique(kp_ids, "knowledge point requirements")
        requirement_ids = [item.requirement_id for item in self.semantic_requirements]
        _require_sorted_unique(requirement_ids, "semantic requirement IDs")
        known_kps = set(kp_ids)
        if any(
            not set(requirement.knowledge_point_ids) <= known_kps
            for requirement in self.semantic_requirements
        ):
            raise ValueError("semantic requirement references an undeclared knowledge point")
        return self


class GenerationContextRequest(ContractModel):
    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    requirements: GenerationContextRequirements


class AdequacyCoverageResult(ContractModel):
    requirement_id: str = Field(min_length=1)
    required_count: int = Field(ge=1)
    available_count: int = Field(ge=0)
    satisfied: bool
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_result(self) -> AdequacyCoverageResult:
        _require_sorted_unique(self.evidence_ids, "coverage evidence IDs")
        if self.satisfied != (self.available_count >= self.required_count):
            raise ValueError("coverage satisfied flag is inconsistent with counts")
        return self


class SupplementRetrievalSuggestion(ContractModel):
    suggestion_id: str = Field(min_length=1)
    requirement_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    roles: list[GenerationSemanticRole] = Field(default_factory=list)
    material_types: list[GenerationMaterialType] = Field(default_factory=list)
    reason_code: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_suggestion(self) -> SupplementRetrievalSuggestion:
        _require_sorted_unique(self.requirement_ids, "suggestion requirement IDs")
        _require_sorted_unique(self.knowledge_point_ids, "suggestion knowledge point IDs")
        _require_sorted_unique(self.roles, "suggestion roles")
        _require_sorted_unique(self.material_types, "suggestion material types")
        return self


class ContextAdequacyReport(ContractModel):
    contract_version: Literal["v1"] = "v1"
    status: ContextAdequacyStatus
    reason_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    knowledge_point_results: list[AdequacyCoverageResult] = Field(default_factory=list)
    requirement_results: list[AdequacyCoverageResult] = Field(default_factory=list)
    semantic_role_counts: dict[GenerationSemanticRole, int] = Field(default_factory=dict)
    material_type_counts: dict[GenerationMaterialType, int] = Field(default_factory=dict)
    evidence_count: int = Field(ge=0)
    distinct_semantic_units: int = Field(ge=0)
    distinct_sources: int = Field(ge=0)
    complete_evidence_group_count: int = Field(ge=0)
    incomplete_evidence_group_count: int = Field(ge=0)
    selected_item_count: int = Field(ge=0)
    selected_evidence_count: int = Field(ge=0)
    token_count: int = Field(ge=0)
    token_budget: int = Field(ge=1)
    discarded_for_budget: int = Field(ge=0)
    discarded_for_item_limit: int = Field(ge=0)
    discarded_for_token_limit: int = Field(ge=0)
    parent_expansion_count: int = Field(ge=0)
    neighbor_expansion_count: int = Field(ge=0)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    missing_knowledge_point_ids: list[str] = Field(default_factory=list)
    supported_target_unit_count: int = Field(ge=0)
    supplement_allowed: bool
    supplement_suggestions: list[SupplementRetrievalSuggestion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_report(self) -> ContextAdequacyReport:
        _require_unique(self.reason_codes, "adequacy reason codes")
        _require_sorted_unique(self.warning_codes, "adequacy warning codes")
        _require_sorted_unique(self.missing_requirement_ids, "missing requirement IDs")
        _require_sorted_unique(self.missing_knowledge_point_ids, "missing knowledge point IDs")
        _require_sorted_unique(
            [item.requirement_id for item in self.knowledge_point_results],
            "knowledge point result IDs",
        )
        _require_sorted_unique(
            [item.requirement_id for item in self.requirement_results],
            "semantic result IDs",
        )
        _require_sorted_unique(
            [item.suggestion_id for item in self.supplement_suggestions],
            "supplement suggestion IDs",
        )
        if self.status is ContextAdequacyStatus.ADEQUATE and (
            self.missing_requirement_ids or self.missing_knowledge_point_ids
        ):
            raise ValueError("adequate report cannot contain missing requirements")
        return self


class GenerationContextResponse(ContractModel):
    meta: ResponseMeta
    context: ContextPackage
    adequacy: ContextAdequacyReport

    @model_validator(mode="after")
    def validate_response(self) -> GenerationContextResponse:
        if (
            self.context.meta.request_id != self.meta.request_id
            or self.context.meta.trace_id != self.meta.trace_id
        ):
            raise ValueError("generation context response metadata is inconsistent")
        return self


def _require_unique(values: Sequence[Hashable], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_sorted_unique(values: Sequence[Hashable], label: str) -> None:
    _require_unique(values, label)
    if list(values) != sorted(values, key=str):
        raise ValueError(f"{label} must be sorted")
