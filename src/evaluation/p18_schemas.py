"""P18 formal CoursePilot evaluation dataset contracts.

These contracts are evaluation-only overlays.  They do not change product HTTP,
database, graph, or provider interfaces.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from evaluation.contracts import ReviewableRecord, Sha256, StrictModel

P18ArtifactType = Literal["lesson", "exam", "ppt"]
P18Split = Literal["dev", "test"]
P18DatasetVersion = Literal["p18-formal-r1", "p18-formal-r2"]


class P18SourceSnapshot(StrictModel):
    course_id: str = Field(min_length=1)
    knowledge_point_id: str = Field(min_length=1)
    knowledge_point_name: str = Field(min_length=1)
    knowledge_point_summary: str = Field(min_length=1)
    knowledge_point_record_sha256: Sha256
    concept_family_id: str = Field(min_length=1)
    section_ids: list[str] = Field(min_length=1)
    evidence_id: str = Field(min_length=1)
    evidence_text: str = Field(min_length=1)
    necessary_neighbors: list[str] = Field(default_factory=list)
    evidence_record_sha256: Sha256
    document_id: str = Field(min_length=1)
    document_version: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)


class P18TrackAContext(StrictModel):
    purpose: Literal["fixed_context_quality"] = "fixed_context_quality"
    evidence_ids: list[str] = Field(min_length=1)
    required_neighbor_texts: list[str] = Field(default_factory=list)
    evidence_group_complete: Literal[True] = True


class P18TrackBRequest(StrictModel):
    purpose: Literal["frozen_index_integration"] = "frozen_index_integration"
    course_id: str = Field(min_length=1)
    retrieval_intent: str = Field(min_length=1)
    required_evidence_ids_for_scoring: list[str] = Field(min_length=1)
    live_result_is_gold: Literal[False] = False
    course_rag_test_query_reused: Literal[False] = False


class P18TaskBase(ReviewableRecord):
    split: P18Split
    artifact_type: P18ArtifactType
    course_id: str = Field(min_length=1)
    task_family_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    task_prompt: str = Field(min_length=1)
    source_snapshots: list[P18SourceSnapshot] = Field(min_length=2)
    required_claims: list[str] = Field(min_length=2)
    forbidden_claims: list[str] = Field(min_length=1)
    track_a_context: P18TrackAContext
    track_b_request: P18TrackBRequest
    critical_defects: list[str] = Field(min_length=1)
    pilot_record_reused: Literal[False] = False

    @model_validator(mode="after")
    def validate_source_scope(self) -> P18TaskBase:
        if any(item.course_id != self.course_id for item in self.source_snapshots):
            raise ValueError("P18 task sources must belong to the task course")
        evidence_ids = [item.evidence_id for item in self.source_snapshots]
        if self.track_a_context.evidence_ids != evidence_ids:
            raise ValueError("Track A evidence order must match source snapshots")
        if self.track_b_request.course_id != self.course_id:
            raise ValueError("Track B request must preserve the task course")
        if self.track_b_request.required_evidence_ids_for_scoring != evidence_ids:
            raise ValueError("Track B scoring Evidence must match the fixed Gold sources")
        return self


class P18LessonTask(P18TaskBase):
    artifact_type: Literal["lesson"] = "lesson"
    total_sessions: int = Field(ge=1, le=12)
    session_duration_minutes: int = Field(ge=15, le=240)
    audience: str = Field(min_length=1)
    required_activity_types: list[str] = Field(min_length=1)
    required_interrupts: list[Literal["lesson_session_plan_review", "lesson_final_review"]]


class P18ExamTask(P18TaskBase):
    artifact_type: Literal["exam"] = "exam"
    question_count: int = Field(ge=1, le=100)
    total_score: int = Field(ge=1, le=200)
    question_type_counts: dict[str, int] = Field(min_length=2)
    difficulty_counts: dict[Literal["easy", "medium", "hard"], int]
    required_interrupts: list[Literal["exam_blueprint_review", "exam_global_review"]]

    @model_validator(mode="after")
    def validate_exam_counts(self) -> P18ExamTask:
        if sum(self.question_type_counts.values()) != self.question_count:
            raise ValueError("question type counts must equal question_count")
        if sum(self.difficulty_counts.values()) != self.question_count:
            raise ValueError("difficulty counts must equal question_count")
        return self


class P18PPTTask(P18TaskBase):
    artifact_type: Literal["ppt"] = "ppt"
    slide_count: int = Field(ge=4, le=60)
    required_slide_types: list[str] = Field(min_length=4)
    notes_required_for_content_slides: Literal[True] = True
    citations_required_for_fact_slides: Literal[True] = True
    editable_objects_required: Literal[True] = True
    required_interrupts: list[Literal["ppt_architecture_review", "ppt_final_review"]]


class P18LessonDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds1-p18.v1"] = "coursepilot.cp-ds1-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    cases: list[P18LessonTask] = Field(min_length=10, max_length=10)


class P18ExamDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds2-p18.v1"] = "coursepilot.cp-ds2-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    cases: list[P18ExamTask] = Field(min_length=10, max_length=10)


class P18PPTDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds3-p18.v1"] = "coursepilot.cp-ds3-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    cases: list[P18PPTTask] = Field(min_length=10, max_length=10)


class P18IssueGold(StrictModel):
    code: str = Field(min_length=1)
    severity: Literal["info", "warning", "error", "critical"]
    layer: Literal["L0", "L1", "L2", "L3", "L4"]
    json_path: str = Field(pattern=r"^\$")
    auto_repairable: bool
    rationale: str = Field(min_length=1)


class P18ValidationCase(ReviewableRecord):
    split: P18Split
    artifact_type: P18ArtifactType
    course_id: str
    source_task_id: str
    fixture_family_id: str
    clean_artifact: bool
    clean_fragment: dict[str, object]
    faulty_fragment: dict[str, object]
    injection_description: str
    gold_issues: list[P18IssueGold]

    @model_validator(mode="after")
    def validate_clean_case(self) -> P18ValidationCase:
        if self.clean_artifact and self.gold_issues:
            raise ValueError("clean validation cases cannot contain Gold issues")
        if not self.clean_artifact and not self.gold_issues:
            raise ValueError("faulted validation cases require Gold issues")
        return self


class P18CarriedRecord(StrictModel):
    record_id: str
    source_path: str
    approved_record_sha256: Sha256
    split: Literal["dev"] = "dev"
    final_metrics_eligible: Literal[True] = True
    requires_new_review: Literal[False] = False


class P18ValidationDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds4-p18.v1"] = "coursepilot.cp-ds4-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    carried_dev_records: list[P18CarriedRecord] = Field(min_length=30, max_length=30)
    new_cases: list[P18ValidationCase] = Field(min_length=60, max_length=60)


class P18RepairCase(ReviewableRecord):
    split: P18Split
    artifact_type: P18ArtifactType
    course_id: str
    source_validation_case_id: str
    issue_code: str
    artifact_before: dict[str, object]
    expected_after: dict[str, object]
    allowed_paths: list[str] = Field(min_length=1)
    forbidden_paths: list[str] = Field(min_length=1)
    preservation_assertions: list[str] = Field(min_length=1)
    max_repair_rounds: int = Field(default=2, ge=1, le=2)


class P18RepairDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds5-p18.v1"] = "coursepilot.cp-ds5-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    carried_dev_records: list[P18CarriedRecord] = Field(min_length=15, max_length=15)
    new_cases: list[P18RepairCase] = Field(min_length=45, max_length=45)


class P18RecoveryCase(ReviewableRecord):
    split: P18Split
    course_id: str
    workflow_type: P18ArtifactType
    source_task_id: str
    interrupt_type: Literal[
        "lesson_session_plan_review",
        "lesson_final_review",
        "exam_blueprint_review",
        "exam_global_review",
        "ppt_architecture_review",
        "ppt_final_review",
    ]
    decision: Literal["approve", "edit_resume", "replan", "reject"]
    initial_state: dict[str, str]
    fault_sequence: list[str] = Field(min_length=1)
    expected_state_transitions: list[str] = Field(min_length=2)
    expected_artifact_version_before: int = Field(ge=1)
    expected_artifact_version_after: int = Field(ge=1)
    expected_reused_nodes: list[str]
    expected_invalidated_nodes: list[str]
    expected_side_effects: dict[str, int]
    approval_scope_granted: list[str]
    approval_scope_forbidden: list[str]


class P18RecoveryDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds6-p18.v1"] = "coursepilot.cp-ds6-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    historical_regression_source_sha256: Sha256
    cases: list[P18RecoveryCase] = Field(min_length=24, max_length=24)


class P18TemplateRenderEvidence(StrictModel):
    renderer: Literal["libreoffice-headless"] = "libreoffice-headless"
    renderer_version: Literal["7.4.7.2"] = "7.4.7.2"
    page_count: int = Field(ge=1)
    png_sha256s: list[Sha256] = Field(min_length=1)
    repeat_render_equal: Literal[True] = True
    visually_inspected: Literal[True] = True
    visual_findings: list[str]


class P18TemplateCase(ReviewableRecord):
    split_role: Literal["dev_contract", "heldout_custom"]
    artifact_type: P18ArtifactType
    template_id: str
    custom_template: bool
    source_kind: Literal["project_builtin", "github_public", "p16_approved_velis"]
    source_path: str
    source_sha256: Sha256
    normalized_path: str
    normalized_sha256: Sha256
    license: str
    source_commit: str | None = None
    source_repository: str | None = None
    source_repository_path: str | None = None
    required_roles: list[str] = Field(min_length=1)
    security_findings: list[str]
    render_status: Literal["prior_phase_verified", "verified_current", "pending_environment"]
    verification_evidence_paths: list[str]
    render_evidence: P18TemplateRenderEvidence | None = None


class P18TemplateDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds7-p18.v1"] = "coursepilot.cp-ds7-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    cases: list[P18TemplateCase] = Field(min_length=11, max_length=11)


class P18FaultVariant(StrictModel):
    variant_id: str
    injection: str
    expected_error_class: str
    expected_user_status: str
    expected_side_effect_count: int = Field(ge=0)
    retry_rule: str
    resume_rule: str
    forbidden_effects: list[str] = Field(min_length=1)


class P18FaultCase(ReviewableRecord):
    split: Literal["dev", "blind"]
    category: Literal["provider", "courserag", "worker", "persistence", "security"]
    course_id: str | None
    scenario_family: str
    initial_state: dict[str, str | int | bool | None]
    injection_point: str
    variants: list[P18FaultVariant] = Field(min_length=1)
    expected_trace_assertions: list[str]
    source_kind: Literal["contract_fixture", "course_grounded_security_wrapper"]
    p17_record_reused: Literal[False] = False


class P18FaultDataset(StrictModel):
    schema_version: Literal["coursepilot.cp-ds8-p18.v1"] = "coursepilot.cp-ds8-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    blind_commitment_sha256: Sha256
    cases: list[P18FaultCase] = Field(min_length=30, max_length=30)


class P18JourneyStep(StrictModel):
    step_index: int = Field(ge=1)
    action: str
    state_before: str
    expected_state: str
    version_assertion: str
    expected_side_effect_count: int = Field(ge=0)
    assertions: list[str] = Field(min_length=1)


class P18JourneyCase(ReviewableRecord):
    split: Literal["test"] = "test"
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
    course_id: str
    source_task_id: str
    p17_signature_difference: list[str] = Field(min_length=2)
    steps: list[P18JourneyStep] = Field(min_length=3)
    expected_final_status: str
    expected_side_effects: dict[str, int]
    forbidden_side_effects: list[str] = Field(min_length=1)


class P18JourneyDataset(StrictModel):
    schema_version: Literal["coursepilot.sys-ds1-p18.v1"] = "coursepilot.sys-ds1-p18.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: P18DatasetVersion = "p18-formal-r1"
    cases: list[P18JourneyCase] = Field(min_length=8, max_length=8)


class P18BundleManifest(StrictModel):
    schema_version: Literal["coursepilot.p18-bundle-manifest.v1"] = (
        "coursepilot.p18-bundle-manifest.v1"
    )
    bundle_kind: Literal["business", "quality_recovery", "integration_export"]
    bundle_sha256: Sha256
    candidate_hashes: dict[str, Sha256] = Field(min_length=1)
    candidate_record_hashes: dict[str, Sha256] = Field(min_length=1)
    upstream_hashes: dict[str, Sha256] = Field(min_length=1)
    review_record_ids: list[str] = Field(min_length=1)
    review_rounds_required: Literal[1] = 1
    html_review_generated: Literal[False] = False
    test_locked: Literal[False] = False
    provider_calls: Literal[0] = 0


class P18ReviewDecision(StrictModel):
    record_id: str
    component: str
    decision: Literal["pending", "approve", "reject"] = "pending"
    notes: str = ""

    @model_validator(mode="after")
    def validate_reject_reason(self) -> P18ReviewDecision:
        if self.decision == "reject" and not self.notes.strip():
            raise ValueError("rejected P18 records require notes")
        return self


class P18ReviewTemplate(StrictModel):
    schema_version: Literal["coursepilot.p18-review-decisions.v1"] = (
        "coursepilot.p18-review-decisions.v1"
    )
    bundle_kind: Literal["business", "quality_recovery", "integration_export"]
    bundle_sha256: Sha256
    review_pass: Literal["single"] = "single"
    reviewer_id: str | None = None
    reviewed_at: datetime | None = None
    instructions: list[str] = Field(min_length=1)
    decisions: list[P18ReviewDecision] = Field(min_length=1)
    readable_records: dict[str, list[dict[str, object]]] = Field(default_factory=dict)


class P18FormalApproval(StrictModel):
    schema_version: Literal["coursepilot.p18-formal-approval.v1"] = (
        "coursepilot.p18-formal-approval.v1"
    )
    approval_scope: Literal["p18_formal_gold_without_cp_ds0_or_test_lock"] = (
        "p18_formal_gold_without_cp_ds0_or_test_lock"
    )
    reviewer_id: Literal["course_owner"] = "course_owner"
    reviewed_at: datetime
    bundle_sha256s: dict[str, Sha256] = Field(min_length=3, max_length=3)
    review_source_sha256s: dict[str, Sha256] = Field(min_length=3)
    candidate_dataset_sha256s: dict[str, Sha256] = Field(min_length=9, max_length=9)
    approved_dataset_sha256s: dict[str, Sha256] = Field(min_length=9, max_length=9)
    approved_record_sha256s: dict[str, Sha256] = Field(min_length=1)
    approved_record_count: int = Field(ge=1)
    component_split_manifest_sha256: Sha256
    cp_ds0_created: Literal[False] = False
    test_locked: Literal[False] = False
