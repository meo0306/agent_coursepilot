from __future__ import annotations

from collections.abc import Iterable
from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from evaluation.contracts import (
    HumanReviewMetadata,
    ReviewableRecord,
    Sha256,
    StrictModel,
)


class DatasetEnvelope(StrictModel):
    schema_version: str
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)


class P11FoundationInputBinding(StrictModel):
    frozen_document_hashes: dict[str, Sha256]
    b0_interface_snapshot_sha256: Sha256
    p10_frozen_manifest_sha256: Sha256
    p10_contract_sha256: Sha256
    logical_template_ids: list[str] = Field(min_length=9, max_length=9)
    model_profile_ids: list[str] = Field(min_length=6, max_length=6)
    binding_status: Literal["pending_p11_output", "resolved"]
    template_registry_sha256: Sha256 | None = None
    prompt_manifest_sha256: Sha256 | None = None
    model_capability_manifest_sha256: Sha256 | None = None
    state_schema_sha256: Sha256 | None = None
    artifact_schema_sha256: Sha256 | None = None
    migration_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_binding_status(self) -> P11FoundationInputBinding:
        runtime_hashes = (
            self.template_registry_sha256,
            self.prompt_manifest_sha256,
            self.model_capability_manifest_sha256,
            self.state_schema_sha256,
            self.artifact_schema_sha256,
            self.migration_sha256,
        )
        if self.binding_status == "pending_p11_output" and any(runtime_hashes):
            raise ValueError("pending P11 bindings cannot contain future runtime hashes")
        if self.binding_status == "resolved" and any(value is None for value in runtime_hashes):
            raise ValueError("resolved P11 bindings require every runtime hash")
        return self


class CPManifestRecord(ReviewableRecord):
    graph_version: str
    courserag_fixture_version: str
    template_registry_version: str
    validator_version: str
    repair_policy_version: str
    exporter_version: str
    rubric_version: str
    p11_foundation_input: P11FoundationInputBinding | None = None


class CPDS0ManifestDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds0.v1"] = "coursepilot.cp-ds0.v1"
    records: list[CPManifestRecord] = Field(default_factory=list)


class LessonTaskCase(ReviewableRecord):
    course_id: str
    template_id: str
    chapter_range: str
    total_sessions: int = Field(ge=1, le=12)
    session_duration: int = Field(ge=15, le=240)
    audience: str
    required_knowledge_point_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_activity_types: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_interrupts: list[str] = Field(default_factory=list)


class CPDS1LessonDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds1.v1"] = "coursepilot.cp-ds1.v1"
    cases: list[LessonTaskCase] = Field(default_factory=list)


class ExamTaskCase(ReviewableRecord):
    template_id: str
    chapter_range: str
    question_counts: dict[str, int]
    score_per_question: dict[str, int]
    difficulty_distribution: dict[str, float]
    required_total_score: int = Field(ge=1)
    required_knowledge_point_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_interrupts: list[str] = Field(default_factory=list)


class CPDS2ExamDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds2.v1"] = "coursepilot.cp-ds2.v1"
    cases: list[ExamTaskCase] = Field(default_factory=list)


class PPTTaskCase(ReviewableRecord):
    template_id: str
    lesson_artifact_id: str
    slide_count: int = Field(ge=3, le=80)
    include_references: bool
    include_speaker_notes: bool
    required_slide_types: list[str] = Field(default_factory=list)
    required_knowledge_point_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    max_bullets_per_slide: int = Field(default=6, ge=1, le=20)
    required_interrupts: list[str] = Field(default_factory=list)


class CPDS3PPTDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds3.v1"] = "coursepilot.cp-ds3.v1"
    cases: list[PPTTaskCase] = Field(default_factory=list)


class IssueScope(StrictModel):
    artifact_type: Literal["lesson", "exam", "ppt"]
    item_id: str | None = None
    json_path: str = Field(pattern=r"^\$")


class ValidationIssue(StrictModel):
    code: str = Field(min_length=1, max_length=160)
    severity: Literal["info", "warning", "error", "critical"]
    scope: IssueScope
    allowed_parent_paths: list[str] = Field(default_factory=list)
    auto_repairable: bool


class ValidationFaultCase(ReviewableRecord):
    artifact_type: Literal["lesson", "exam", "ppt"]
    artifact_fixture_id: str
    injection_ids: list[str] = Field(default_factory=list)
    gold_issues: list[ValidationIssue] = Field(default_factory=list)
    clean_artifact: bool = False


class CPDS4ValidationDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds4.v1"] = "coursepilot.cp-ds4.v1"
    cases: list[ValidationFaultCase] = Field(default_factory=list)


class RepairCase(ReviewableRecord):
    artifact_type: Literal["lesson", "exam", "ppt"]
    artifact_before_id: str
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(default_factory=list)
    expected_resolved_issue_codes: list[str] = Field(default_factory=list)
    original_correct_paths: list[str] = Field(default_factory=list)
    max_repair_rounds: int = Field(default=2, ge=1, le=10)


class CPDS5RepairDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds5.v1"] = "coursepilot.cp-ds5.v1"
    cases: list[RepairCase] = Field(default_factory=list)


class RecoveryExpectation(StrictModel):
    interrupt_reached: bool
    resume_succeeds: bool
    completed_nodes_reused: int = Field(ge=0)
    completed_nodes_before_resume: int = Field(ge=0)
    edited_fields_preserved: int = Field(ge=0)
    edited_fields_total: int = Field(ge=0)
    duplicate_side_effects: int = Field(ge=0)
    replayed_side_effect_attempts: int = Field(ge=0)
    approval_scope_correct: bool
    stale_version_detected: bool | None = None

    @model_validator(mode="after")
    def validate_duplicate_denominator(self) -> RecoveryExpectation:
        if self.duplicate_side_effects > self.replayed_side_effect_attempts:
            raise ValueError("duplicate_side_effects cannot exceed replayed_side_effect_attempts")
        return self


class InterruptRecoveryCase(ReviewableRecord):
    interrupt_type: Literal[
        "lesson_session_plan_review",
        "lesson_final_review",
        "exam_blueprint_review",
        "exam_global_review",
        "ppt_architecture_review",
        "ppt_final_review",
    ]
    decision: Literal["approve", "edit_resume", "replan", "reject"]
    fault: str | None = None
    expectation: RecoveryExpectation


class CPDS6RecoveryDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds6.v1"] = "coursepilot.cp-ds6.v1"
    cases: list[InterruptRecoveryCase] = Field(default_factory=list)


class P12InterruptRecoveryCase(ReviewableRecord):
    """Deterministic P12 Pilot contract; it contains no future runtime identities."""

    interrupt_type: Literal[
        "lesson_session_plan_review",
        "lesson_final_review",
        "exam_blueprint_review",
        "exam_global_review",
        "ppt_architecture_review",
        "ppt_final_review",
    ]
    workflow_type: Literal["lesson", "exam", "ppt"]
    scenario_type: Literal["approve", "edit_resume", "replan", "reject"]
    fixture_id: str = Field(pattern=r"^p12-structure-[a-z0-9-]+$")
    task_ref: str = Field(pattern=r"^task:p12:[a-z0-9-]+$")
    thread_ref: str = Field(pattern=r"^thread:p12:[a-z0-9-]+$")
    checkpoint_ref: str = Field(pattern=r"^checkpoint:p12:[a-z0-9-]+$")
    artifact_ref: str = Field(pattern=r"^artifact:p12:[a-z0-9-]+$")
    initial_state: dict[str, str] = Field(min_length=4)
    fault_sequence: list[str] = Field(min_length=1)
    human_decision: Literal["approve", "edit_resume", "replan", "reject"]
    editable_paths: list[str] = Field(default_factory=list)
    edit_patch: dict[str, str] = Field(default_factory=dict)
    expected_state_transitions: list[str] = Field(min_length=2)
    expected_artifact_version_before: int = Field(ge=1)
    expected_artifact_version_after: int = Field(ge=1)
    expected_reused_nodes: list[str] = Field(default_factory=list)
    expected_invalidated_nodes: list[str] = Field(default_factory=list)
    approval_scope_granted: list[str] = Field(default_factory=list)
    approval_scope_forbidden: list[str] = Field(default_factory=list)
    expected_side_effects: dict[str, int] = Field(min_length=4)
    expected_error_class: str | None = None
    stale_version_detected: bool
    resume_after_cancel_forbidden: bool = True

    @model_validator(mode="after")
    def validate_p12_case(self) -> P12InterruptRecoveryCase:
        if self.human_decision != self.scenario_type:
            raise ValueError("P12 human decision must match scenario type")
        if self.expected_artifact_version_after < self.expected_artifact_version_before:
            raise ValueError("P12 artifact version cannot move backwards")
        if self.scenario_type == "edit_resume":
            if not self.editable_paths or not self.edit_patch:
                raise ValueError("edit_resume requires editable paths and a patch")
            if self.expected_artifact_version_after != self.expected_artifact_version_before + 1:
                raise ValueError("edit_resume must create exactly one new artifact version")
        else:
            if self.editable_paths or self.edit_patch:
                raise ValueError("only edit_resume may contain an edit patch")
        if self.scenario_type == "replan" and not self.stale_version_detected:
            raise ValueError("replan must detect a stale version")
        if self.scenario_type == "reject" and not any(
            transition.endswith("->cancelled") for transition in self.expected_state_transitions
        ):
            raise ValueError("reject must terminate in cancelled state")
        if self.expected_side_effects.get("duplicate_decision_records", 0) != 0:
            raise ValueError("duplicate decision records must remain zero")
        if self.scenario_type == "reject" and not self.resume_after_cancel_forbidden:
            raise ValueError("cancelled P12 tasks must reject resume")
        return self


class CPDS6P12PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds6-p12.v1"] = "coursepilot.cp-ds6-p12.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: Literal["p12-pilot-r1"] = "p12-pilot-r1"
    approval_scope: Literal["cp_ds6_pilot_input_only"] = "cp_ds6_pilot_input_only"
    cases: list[P12InterruptRecoveryCase] = Field(min_length=24, max_length=24)

    @model_validator(mode="after")
    def validate_distribution(self) -> CPDS6P12PilotDataset:
        interrupt_counts = {
            item: 0
            for item in (
                "lesson_session_plan_review",
                "lesson_final_review",
                "exam_blueprint_review",
                "exam_global_review",
                "ppt_architecture_review",
                "ppt_final_review",
            )
        }
        scenario_counts = {item: 0 for item in ("approve", "edit_resume", "replan", "reject")}
        for case in self.cases:
            interrupt_counts[case.interrupt_type] += 1
            scenario_counts[case.scenario_type] += 1
        if set(interrupt_counts.values()) != {4} or set(scenario_counts.values()) != {6}:
            raise ValueError("P12 Pilot requires 4 cases per interrupt and 6 per scenario")
        return self


class TemplateExportCase(ReviewableRecord):
    artifact_type: Literal["lesson", "exam", "ppt"]
    template_id: str
    template_version: str
    custom_template: bool
    required_placeholders: list[str] = Field(default_factory=list)
    required_layouts: list[str] = Field(default_factory=list)
    expected_file_roles: list[str] = Field(default_factory=list)
    render_required: bool = True


class CPDS7ExportDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds7.v1"] = "coursepilot.cp-ds7.v1"
    cases: list[TemplateExportCase] = Field(default_factory=list)


class FaultSecurityCase(ReviewableRecord):
    category: Literal["provider", "courserag", "worker", "persistence", "security"]
    fault_code: str
    expected_error_class: str
    expected_graceful_failure: bool
    unauthorized_action_expected: bool = False
    cross_course_leakage_expected: bool = False
    secret_leakage_expected: bool = False
    duplicate_side_effect_expected: bool = False


class CPDS8FaultSecurityDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds8.v1"] = "coursepilot.cp-ds8.v1"
    cases: list[FaultSecurityCase] = Field(default_factory=list)


class SystemJourneyCase(ReviewableRecord):
    journey_type: Literal[
        "lesson",
        "exam",
        "ppt",
        "writeback_loop",
        "fault_recovery",
        "insufficient_evidence",
        "malicious_material",
        "version_change",
    ]
    required_steps: list[str] = Field(min_length=1)
    expected_final_status: str
    expected_side_effects: list[str] = Field(default_factory=list)
    forbidden_side_effects: list[str] = Field(default_factory=list)


class SYSDS1JourneyDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.sys-ds1.v1"] = "coursepilot.sys-ds1.v1"
    cases: list[SystemJourneyCase] = Field(default_factory=list)


CoursePilotDataset = Annotated[
    CPDS0ManifestDataset
    | CPDS1LessonDataset
    | CPDS2ExamDataset
    | CPDS3PPTDataset
    | CPDS4ValidationDataset
    | CPDS5RepairDataset
    | CPDS6RecoveryDataset
    | CPDS7ExportDataset
    | CPDS8FaultSecurityDataset
    | SYSDS1JourneyDataset,
    Field(discriminator="schema_version"),
]


class LessonHumanReview(StrictModel):
    review_type: Literal["lesson"] = "lesson"
    metadata: HumanReviewMetadata
    artifact_id: str
    rubric_scores: dict[
        Literal["L-H1", "L-H2", "L-H3", "L-H4", "L-H5", "L-H6", "L-H7", "L-H8"],
        Annotated[int, Field(ge=1, le=5)],
    ] = Field(min_length=8, max_length=8)
    edit_burden: int = Field(ge=0, le=4)
    critical_defect: bool
    artifact_status: Literal["accepted", "minor_edit", "major_edit", "reject"]

    @model_validator(mode="after")
    def validate_complete_rubric(self) -> LessonHumanReview:
        _require_complete_rubric(self.rubric_scores.keys(), _LESSON_RUBRIC_KEYS)
        return self


class ExamQuestionHumanReview(StrictModel):
    review_type: Literal["exam_question"] = "exam_question"
    metadata: HumanReviewMetadata
    artifact_id: str
    question_id: str
    question_status: Literal["accepted", "minor_edit", "major_edit", "reject"]
    rubric_scores: dict[
        Literal[
            "E-H1",
            "E-H2",
            "E-H3",
            "E-H4",
            "E-H5",
            "E-H6",
            "E-H7",
            "E-H8",
            "E-H9",
            "E-H10",
        ],
        Annotated[int, Field(ge=1, le=5)],
    ] = Field(min_length=10, max_length=10)
    edit_burden: int = Field(ge=0, le=4)
    critical_defect: bool

    @model_validator(mode="after")
    def validate_complete_rubric(self) -> ExamQuestionHumanReview:
        _require_complete_rubric(self.rubric_scores.keys(), _EXAM_RUBRIC_KEYS)
        return self


class PPTSlideHumanReview(StrictModel):
    review_type: Literal["ppt_slide"] = "ppt_slide"
    metadata: HumanReviewMetadata
    artifact_id: str
    slide_id: str
    slide_status: Literal["accepted", "minor_edit", "major_edit", "reject"]
    critical_defect: bool
    rubric_scores: dict[
        Literal[
            "P-H1",
            "P-H2",
            "P-H3",
            "P-H4",
            "P-H5",
            "P-H6",
            "P-H7",
            "P-H8",
            "P-H9",
            "P-H10",
        ],
        Annotated[int, Field(ge=1, le=5)],
    ] = Field(min_length=10, max_length=10)
    edit_burden: int = Field(ge=0, le=4)

    @model_validator(mode="after")
    def validate_complete_rubric(self) -> PPTSlideHumanReview:
        _require_complete_rubric(self.rubric_scores.keys(), _PPT_RUBRIC_KEYS)
        return self


HumanScoreRecord = Annotated[
    LessonHumanReview | ExamQuestionHumanReview | PPTSlideHumanReview,
    Field(discriminator="review_type"),
]


class HumanScoreJsonlRecord(RootModel[HumanScoreRecord]):
    """One CoursePilot human-score JSONL record."""


class HumanScoreDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.human-scores.v1"] = "coursepilot.human-scores.v1"
    records: list[HumanScoreRecord] = Field(default_factory=list)


_LESSON_RUBRIC_KEYS = frozenset(f"L-H{index}" for index in range(1, 9))
_EXAM_RUBRIC_KEYS = frozenset(f"E-H{index}" for index in range(1, 11))
_PPT_RUBRIC_KEYS = frozenset(f"P-H{index}" for index in range(1, 11))


def _require_complete_rubric(
    keys: Iterable[str],
    expected: frozenset[str],
) -> None:
    actual = set(keys)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected)
        raise ValueError(
            f"rubric_scores must contain every frozen dimension; "
            f"missing={missing}, unexpected={unexpected}"
        )
