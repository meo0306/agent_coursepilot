from __future__ import annotations

from collections.abc import Hashable, Sequence
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from coursepilot.domain.common import DomainModel
from coursepilot.domain.task import WorkflowType

Difficulty = Literal["easy", "medium", "hard"]


class ArtifactTargetUnit(StrEnum):
    SESSIONS = "sessions"
    QUESTIONS = "questions"
    SLIDES = "slides"


class SemanticUnitRole(StrEnum):
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


class MaterialType(StrEnum):
    FORMULA = "formula"
    TABLE = "table"
    NUMERIC = "numeric"
    CASE = "case"
    VISUAL_RELATIONSHIP = "visual_relationship"


class SemanticUnitRequirement(DomainModel):
    requirement_id: str = Field(min_length=1, max_length=160)
    minimum_count: int = Field(ge=1)
    roles: list[SemanticUnitRole] = Field(default_factory=list)
    material_types: list[MaterialType] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    required: bool = True

    @model_validator(mode="after")
    def validate_requirement(self) -> SemanticUnitRequirement:
        if not self.roles and not self.material_types:
            raise ValueError("semantic requirement needs a role or material type")
        _require_sorted_unique(self.roles, "roles")
        _require_sorted_unique(self.material_types, "material_types")
        _require_sorted_unique(self.knowledge_point_ids, "knowledge_point_ids")
        return self


class DemandBuildContext(DomainModel):
    """CoursePilot-only inputs that are not part of the current HTTP request schemas."""

    knowledge_point_ids: list[str] = Field(default_factory=list)
    additional_requirements: list[SemanticUnitRequirement] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_context(self) -> DemandBuildContext:
        _require_sorted_unique(self.knowledge_point_ids, "knowledge_point_ids")
        _require_unique(
            [item.requirement_id for item in self.additional_requirements],
            "additional requirement IDs",
        )
        return self


class PPTLessonDemandContext(DomainModel):
    lesson_id: str = Field(min_length=1)
    chapter_scope: str = Field(min_length=1)
    total_sessions: int = Field(ge=1)
    knowledge_point_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_context(self) -> PPTLessonDemandContext:
        _require_sorted_unique(self.knowledge_point_ids, "knowledge_point_ids")
        return self


class ArtifactDemand(DomainModel):
    course_id: str = Field(min_length=1)
    artifact_type: WorkflowType
    scope_label: str = Field(min_length=1, max_length=1000)
    source_artifact_id: str | None = None
    target_unit: ArtifactTargetUnit
    target_unit_count: int = Field(ge=1)
    minimum_viable_unit_count: int = Field(ge=1)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    minimum_units_per_knowledge_point: int = Field(default=0, ge=0)
    minimum_distinct_sources: int = Field(ge=1)
    minimum_semantic_units: int = Field(ge=1)
    semantic_requirements: list[SemanticUnitRequirement] = Field(min_length=1)
    audience: str | None = Field(default=None, max_length=500)
    difficulty_profile: dict[Difficulty, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_demand(self) -> ArtifactDemand:
        expected_units = {
            WorkflowType.LESSON: ArtifactTargetUnit.SESSIONS,
            WorkflowType.EXAM: ArtifactTargetUnit.QUESTIONS,
            WorkflowType.PPT: ArtifactTargetUnit.SLIDES,
        }
        if self.target_unit is not expected_units[self.artifact_type]:
            raise ValueError("target unit must match artifact type")
        if self.minimum_viable_unit_count > self.target_unit_count:
            raise ValueError("minimum viable unit count exceeds target")
        if self.artifact_type is WorkflowType.PPT and self.source_artifact_id is None:
            raise ValueError("PPT demand requires a source lesson artifact")
        if self.artifact_type is not WorkflowType.PPT and self.source_artifact_id is not None:
            raise ValueError("only PPT demand may reference a source artifact")

        _require_sorted_unique(self.knowledge_point_ids, "knowledge_point_ids")
        _require_unique(
            [item.requirement_id for item in self.semantic_requirements],
            "semantic requirement IDs",
        )
        _require_sorted_unique(self.warnings, "warnings")
        known_kps = set(self.knowledge_point_ids)
        if any(
            not set(requirement.knowledge_point_ids) <= known_kps
            for requirement in self.semantic_requirements
        ):
            raise ValueError("semantic requirement references a knowledge point outside demand")
        if known_kps and self.minimum_units_per_knowledge_point < 1:
            raise ValueError("knowledge point demand requires minimum coverage")
        if not known_kps and self.minimum_units_per_knowledge_point != 0:
            raise ValueError("knowledge point minimum must be zero when no IDs are known")

        if self.artifact_type is WorkflowType.EXAM:
            if set(self.difficulty_profile) != {"easy", "medium", "hard"}:
                raise ValueError("exam difficulty profile requires easy, medium and hard")
            if any(value < 0 for value in self.difficulty_profile.values()):
                raise ValueError("difficulty weights cannot be negative")
            if abs(sum(self.difficulty_profile.values()) - 1.0) > 1e-9:
                raise ValueError("difficulty profile must sum to 1.0")
        elif self.difficulty_profile:
            raise ValueError("difficulty profile is only valid for exam demand")
        return self


class AdequacyStatus(StrEnum):
    ADEQUATE = "adequate"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    UNRESOLVABLE = "unresolvable"


class AdequacySnapshot(DomainModel):
    """Minimal CoursePilot consumer view; EP-02 owns the eventual public report."""

    status: AdequacyStatus
    knowledge_point_unit_counts: dict[str, int] = Field(default_factory=dict)
    requirement_unit_counts: dict[str, int] = Field(default_factory=dict)
    distinct_sources: int = Field(ge=0)
    distinct_semantic_units: int = Field(ge=0)
    supplement_allowed: bool = False
    supported_target_unit_count: int | None = Field(default=None, ge=0)
    low_character_count_warning: bool = False

    @model_validator(mode="after")
    def validate_counts(self) -> AdequacySnapshot:
        for label, counts in (
            ("knowledge point", self.knowledge_point_unit_counts),
            ("requirement", self.requirement_unit_counts),
        ):
            if any(not key for key in counts):
                raise ValueError(f"{label} count keys cannot be empty")
            if any(value < 0 for value in counts.values()):
                raise ValueError(f"{label} counts cannot be negative")
        return self


class FeasibilityStatus(StrEnum):
    FEASIBLE = "feasible"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    SCOPE_REDUCTION_REQUIRED = "scope_reduction_required"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class FeasibilityAction(StrEnum):
    PROCEED_GENERATION = "proceed_generation"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    OFFER_SCOPE_REDUCTION = "offer_scope_reduction"
    REQUEST_HUMAN_REVIEW = "request_human_review"


class FeasibilityReasonCode(StrEnum):
    KNOWLEDGE_POINT_COVERAGE_MISSING = "knowledge_point_coverage_missing"
    SEMANTIC_REQUIREMENT_MISSING = "semantic_requirement_missing"
    DISTINCT_SOURCE_CAPACITY_INSUFFICIENT = "distinct_source_capacity_insufficient"
    SEMANTIC_UNIT_CAPACITY_INSUFFICIENT = "semantic_unit_capacity_insufficient"
    ADEQUACY_NEEDS_MORE_EVIDENCE = "adequacy_needs_more_evidence"
    ADEQUACY_UNRESOLVABLE = "adequacy_unresolvable"
    ADEQUACY_CONTRACT_INCONSISTENT = "adequacy_contract_inconsistent"
    SCOPE_CAN_BE_REDUCED = "scope_can_be_reduced"
    MINIMUM_VIABLE_SCOPE_UNSUPPORTED = "minimum_viable_scope_unsupported"
    LOW_CHARACTER_COUNT_WARNING = "low_character_count_warning"


class FeasibilityDecision(DomainModel):
    status: FeasibilityStatus
    action: FeasibilityAction
    reason_codes: list[FeasibilityReasonCode] = Field(default_factory=list)
    missing_requirement_ids: list[str] = Field(default_factory=list)
    missing_knowledge_point_ids: list[str] = Field(default_factory=list)
    suggested_target_unit_count: int | None = Field(default=None, ge=1)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_decision(self) -> FeasibilityDecision:
        expected_actions = {
            FeasibilityStatus.FEASIBLE: FeasibilityAction.PROCEED_GENERATION,
            FeasibilityStatus.NEEDS_MORE_EVIDENCE: FeasibilityAction.REQUEST_MORE_EVIDENCE,
            FeasibilityStatus.SCOPE_REDUCTION_REQUIRED: (FeasibilityAction.OFFER_SCOPE_REDUCTION),
            FeasibilityStatus.NEEDS_HUMAN_REVIEW: FeasibilityAction.REQUEST_HUMAN_REVIEW,
        }
        if self.action is not expected_actions[self.status]:
            raise ValueError("feasibility status and action are inconsistent")
        _require_unique(self.reason_codes, "reason codes")
        _require_sorted_unique(self.missing_requirement_ids, "missing requirement IDs")
        _require_sorted_unique(self.missing_knowledge_point_ids, "missing knowledge point IDs")
        _require_sorted_unique(self.warnings, "warnings")
        if self.status is FeasibilityStatus.FEASIBLE and (
            self.missing_requirement_ids or self.missing_knowledge_point_ids
        ):
            raise ValueError("feasible decision cannot contain missing requirements")
        if self.status is FeasibilityStatus.SCOPE_REDUCTION_REQUIRED:
            if self.suggested_target_unit_count is None:
                raise ValueError("scope reduction requires a suggested target")
        elif self.suggested_target_unit_count is not None:
            raise ValueError("only scope reduction may suggest a target")
        return self

    @property
    def generation_allowed(self) -> bool:
        return (
            self.status is FeasibilityStatus.FEASIBLE
            and self.action is FeasibilityAction.PROCEED_GENERATION
        )


def _require_unique(values: Sequence[Hashable], label: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"{label} must be unique")


def _require_sorted_unique(values: Sequence[Hashable], label: str) -> None:
    _require_unique(values, label)
    if list(values) != sorted(values, key=str):
        raise ValueError(f"{label} must be sorted")
