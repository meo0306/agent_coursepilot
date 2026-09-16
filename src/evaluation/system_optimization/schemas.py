"""Strict schemas for the post-P18 development workbench.

All Adequacy labels and rubric bindings in candidate records are proposals for
human review.  They are not formal Gold until an explicit ApprovalRecord is
attached to every record and the dataset is stored under ``approved/``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from evaluation.contracts import RecordId, ReviewableRecord, ReviewStatus, Sha256, StrictModel


class ArtifactType(StrEnum):
    LESSON = "lesson"
    EXAM = "exam"
    PPT = "ppt"


class CapacityTier(StrEnum):
    THIN = "thin"
    MEDIUM = "medium"
    RICH = "rich"


class MaterialType(StrEnum):
    DEFINITION = "definition"
    COMPARISON = "comparison"
    PROCESS = "process"
    FORMULA = "formula"
    TABLE = "table"
    NUMERIC = "numeric"
    CASE = "case"


class TopicRelation(StrEnum):
    SINGLE = "single"
    ADJACENT = "adjacent"
    NON_ADJACENT = "non_adjacent"


class AdequacyStatus(StrEnum):
    ADEQUATE = "adequate"
    NEEDS_MORE_EVIDENCE = "needs_more_evidence"
    UNRESOLVABLE = "unresolvable"


class NextAction(StrEnum):
    GENERATE = "generate"
    SUPPLEMENT_RETRIEVAL = "supplement_retrieval"
    REDUCE_SCOPE = "reduce_scope"
    HUMAN_REVIEW = "human_review"


class TaskDemandCandidate(StrictModel):
    artifact_type: ArtifactType
    output_count: int = Field(ge=1, le=100)
    output_unit: Literal["sessions", "questions", "slides"]
    knowledge_point_ids: list[RecordId] = Field(min_length=1, max_length=6)
    required_material_types: list[MaterialType] = Field(min_length=1)
    topic_relation: TopicRelation
    audience: str = Field(min_length=1, max_length=200)
    difficulty_profile: dict[Literal["easy", "medium", "hard"], float]

    @model_validator(mode="after")
    def validate_artifact_quantity(self) -> TaskDemandCandidate:
        expected_units = {
            ArtifactType.LESSON: "sessions",
            ArtifactType.EXAM: "questions",
            ArtifactType.PPT: "slides",
        }
        if self.output_unit != expected_units[self.artifact_type]:
            raise ValueError("output unit must match artifact type")
        limits = {
            ArtifactType.LESSON: (1, 2),
            ArtifactType.EXAM: (2, 6),
            ArtifactType.PPT: (3, 7),
        }
        lower, upper = limits[self.artifact_type]
        if not lower <= self.output_count <= upper:
            raise ValueError("output count is outside the EP-00 Dev range")
        if abs(sum(self.difficulty_profile.values()) - 1.0) > 1e-9:
            raise ValueError("difficulty profile must sum to 1.0")
        kp_count = len(self.knowledge_point_ids)
        expected_kps = {
            TopicRelation.SINGLE: 1,
            TopicRelation.ADJACENT: 2,
            TopicRelation.NON_ADJACENT: 3,
        }
        if kp_count != expected_kps[self.topic_relation]:
            raise ValueError("knowledge point count must match topic relation")
        return self


class EvidenceItem(StrictModel):
    evidence_id: RecordId
    source_record_id: RecordId
    course_id: RecordId
    content_sha256: Sha256
    semantic_unit_type: str = Field(min_length=1, max_length=80)
    source_type: str = Field(min_length=1, max_length=80)
    excerpt: str = Field(min_length=1)
    material_types: list[MaterialType] = Field(min_length=1)
    dev_context_ids: list[RecordId] = Field(min_length=1)
    source_origin: Literal["courserag_approved_non_p18_dev"] = "courserag_approved_non_p18_dev"


class EvidenceGroup(StrictModel):
    group_id: RecordId
    knowledge_point_id: RecordId
    evidence_ids: list[RecordId]
    complete: bool
    missing_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_completion(self) -> EvidenceGroup:
        if self.complete and (not self.evidence_ids or self.missing_reasons):
            raise ValueError("complete Evidence groups require Evidence and no missing reasons")
        if not self.complete and not self.missing_reasons:
            raise ValueError("incomplete Evidence groups require a reason")
        return self


class EvidencePackageCandidate(StrictModel):
    capacity_tier: CapacityTier
    items: list[EvidenceItem] = Field(min_length=1)
    groups: list[EvidenceGroup] = Field(min_length=1)
    estimated_tokens: int = Field(ge=1)
    distinct_semantic_units: int = Field(ge=1)
    missing_knowledge_point_ids: list[RecordId] = Field(default_factory=list)
    missing_material_types: list[MaterialType] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_course_and_identity(self) -> EvidencePackageCandidate:
        evidence_ids = [item.evidence_id for item in self.items]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence package contains duplicate Evidence IDs")
        if len({item.course_id for item in self.items}) != 1:
            raise ValueError("Evidence package cannot cross course boundaries")
        known = set(evidence_ids)
        if any(not set(group.evidence_ids).issubset(known) for group in self.groups):
            raise ValueError("Evidence group references an unknown Evidence item")
        return self


class AdequacyCandidate(StrictModel):
    status: AdequacyStatus
    rationale: str = Field(min_length=1, max_length=4000)
    unmet_requirements: list[str] = Field(default_factory=list)
    allowed_actions: list[NextAction] = Field(min_length=1)
    human_approval_required: Literal[True] = True

    @model_validator(mode="after")
    def validate_actions(self) -> AdequacyCandidate:
        actions = set(self.allowed_actions)
        if self.status is AdequacyStatus.ADEQUATE:
            if self.unmet_requirements or actions != {NextAction.GENERATE}:
                raise ValueError("adequate candidates must only allow generation")
        elif NextAction.GENERATE in actions:
            raise ValueError("inadequate candidates cannot allow generation")
        return self


class RubricDimension(StrictModel):
    rubric_id: str = Field(pattern=r"^[LEP]-H(?:10|[1-9])$")
    label: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=500)


class ArtifactRubricProfile(StrictModel):
    artifact_type: ArtifactType
    rubric_version: Literal["coursepilot-human-rubric-frozen-v1"] = (
        "coursepilot-human-rubric-frozen-v1"
    )
    dimensions: list[RubricDimension]
    score_min: Literal[1] = 1
    score_max: Literal[5] = 5
    edit_burden_scale: dict[Literal["0", "1", "2", "3", "4"], str]

    @model_validator(mode="after")
    def validate_dimensions(self) -> ArtifactRubricProfile:
        expected = {ArtifactType.LESSON: 8, ArtifactType.EXAM: 10, ArtifactType.PPT: 10}
        prefixes = {ArtifactType.LESSON: "L-H", ArtifactType.EXAM: "E-H", ArtifactType.PPT: "P-H"}
        ids = [item.rubric_id for item in self.dimensions]
        if len(ids) != expected[self.artifact_type] or len(ids) != len(set(ids)):
            raise ValueError("rubric dimension set is incomplete or duplicated")
        if any(not item.startswith(prefixes[self.artifact_type]) for item in ids):
            raise ValueError("rubric dimension prefix does not match artifact type")
        return self


class SystemOptimizationDevCase(ReviewableRecord):
    split: Literal["dev"] = "dev"
    artifact_type: ArtifactType
    course_id: RecordId
    title: str = Field(min_length=1, max_length=300)
    task_demand: TaskDemandCandidate
    evidence_package: EvidencePackageCandidate
    candidate_adequacy: AdequacyCandidate
    rubric_profile: ArtifactRubricProfile
    coverage_tags: list[str] = Field(min_length=1)
    p18_case_reused: Literal[False] = False
    formal_gold_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_case_alignment(self) -> SystemOptimizationDevCase:
        if self.task_demand.artifact_type is not self.artifact_type:
            raise ValueError("Task Demand artifact type differs from the Dev Case")
        if self.rubric_profile.artifact_type is not self.artifact_type:
            raise ValueError("rubric artifact type differs from the Dev Case")
        if any(item.course_id != self.course_id for item in self.evidence_package.items):
            raise ValueError("Dev Case Evidence must remain in the task course")
        if self.record_id.casefold().startswith("p18"):
            raise ValueError("P18 records are forbidden in the optimization Dev dataset")
        if self.review_status is ReviewStatus.APPROVED and self.formal_gold_eligible:
            raise ValueError("approved Dev data is still not formal Test Gold")
        return self


class DevCaseDataset(StrictModel):
    schema_version: Literal["system-optimization.dev-cases.v1"] = "system-optimization.dev-cases.v1"
    dataset_id: Literal["system-optimization-dev"] = "system-optimization-dev"
    dataset_version: Literal["v1"] = "v1"
    records: list[SystemOptimizationDevCase] = Field(min_length=27, max_length=27)

    @model_validator(mode="after")
    def validate_coverage(self) -> DevCaseDataset:
        for artifact in ArtifactType:
            records = [item for item in self.records if item.artifact_type is artifact]
            if len(records) != 9:
                raise ValueError(f"{artifact.value} requires exactly nine Dev Cases")
            tiers = [item.evidence_package.capacity_tier for item in records]
            if any(tiers.count(tier) != 3 for tier in CapacityTier):
                raise ValueError(f"{artifact.value} requires three Cases per capacity tier")
            covered = {
                material
                for item in records
                for material in item.task_demand.required_material_types
            }
            if covered != set(MaterialType):
                raise ValueError(f"{artifact.value} does not cover every material type")
        if len({item.record_id for item in self.records}) != 27:
            raise ValueError("Dev Case IDs must be unique")
        return self


class FailureExpectation(StrictModel):
    error_class: str = Field(min_length=1, max_length=120)
    user_status: str = Field(min_length=1, max_length=120)
    retry_allowed: bool
    resume_allowed: bool
    maximum_side_effects: int = Field(ge=0, le=1)


class FailureReplayCase(ReviewableRecord):
    split: Literal["dev"] = "dev"
    category: Literal[
        "schema",
        "timeout",
        "missing_batch",
        "incomplete_group",
        "index_missing",
    ]
    artifact_type: ArtifactType | None = None
    injection_point: str = Field(min_length=1, max_length=300)
    fixture: dict[str, str | int | bool | None]
    expectation: FailureExpectation
    p18_case_reused: Literal[False] = False

    @model_validator(mode="after")
    def validate_non_p18(self) -> FailureReplayCase:
        if self.record_id.casefold().startswith("p18"):
            raise ValueError("P18 failures cannot be copied into the new Dev dataset")
        return self


class FailureReplayDataset(StrictModel):
    schema_version: Literal["system-optimization.failure-replays.v1"] = (
        "system-optimization.failure-replays.v1"
    )
    dataset_id: Literal["system-optimization-dev"] = "system-optimization-dev"
    dataset_version: Literal["v1"] = "v1"
    records: list[FailureReplayCase] = Field(min_length=7, max_length=7)

    @model_validator(mode="after")
    def validate_failure_coverage(self) -> FailureReplayDataset:
        categories = {item.category for item in self.records}
        expected = {"schema", "timeout", "missing_batch", "incomplete_group", "index_missing"}
        schema_artifacts = {
            item.artifact_type for item in self.records if item.category == "schema"
        }
        if categories != expected or schema_artifacts != set(ArtifactType):
            raise ValueError("failure replays do not cover the approved EP-00 matrix")
        return self


class CaseApprovalDecision(StrictModel):
    record_id: RecordId
    decision: Literal["pending", "approve", "reject", "request_changes"] = "pending"
    reviewer_id: RecordId | None = None
    reviewed_at: datetime | None = None
    adequacy_decision: AdequacyStatus | None = None
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_completed_decision(self) -> CaseApprovalDecision:
        completed = self.decision != "pending"
        if completed and (self.reviewer_id is None or self.reviewed_at is None):
            raise ValueError("completed Case reviews require reviewer and time")
        if self.decision == "approve" and self.adequacy_decision is None:
            raise ValueError("approved Cases require an explicit Adequacy decision")
        if self.decision in {"reject", "request_changes"} and not self.notes.strip():
            raise ValueError("rejected or returned Cases require notes")
        return self


class CaseApprovalBatch(StrictModel):
    schema_version: Literal["system-optimization.case-review-decisions.v1"]
    dataset_status: Literal["candidate"]
    decisions: list[CaseApprovalDecision] = Field(min_length=27, max_length=27)

    @model_validator(mode="after")
    def validate_unique_records(self) -> CaseApprovalBatch:
        record_ids = [item.record_id for item in self.decisions]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Case approval decisions contain duplicate record IDs")
        return self


class ArtifactReviewDecision(StrictModel):
    blind_artifact_id: RecordId
    artifact_type: ArtifactType
    repeat_group_id: RecordId | None = None
    artifact_status: Literal["pending", "accepted", "minor_edit", "major_edit", "reject"] = (
        "pending"
    )
    rubric_scores: dict[str, int | None]
    edit_burden: int | None = Field(default=None, ge=0, le=4)
    critical_defect: bool | None = None
    reviewer_id: RecordId | None = None
    reviewed_at: datetime | None = None
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_review_completion(self) -> ArtifactReviewDecision:
        if self.artifact_status == "pending":
            return self
        required = (self.edit_burden, self.critical_defect, self.reviewer_id, self.reviewed_at)
        if any(value is None for value in required):
            raise ValueError("completed Artifact reviews require all review metadata")
        if any(value is None for value in self.rubric_scores.values()):
            raise ValueError("completed Artifact reviews require every rubric score")
        if self.artifact_status in {"major_edit", "reject"} and not self.notes.strip():
            raise ValueError("major edits and rejects require notes")
        return self
