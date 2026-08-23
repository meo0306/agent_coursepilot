from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, RootModel, model_validator

from evaluation.contracts import (
    ApprovalRecord,
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


class P14EvidenceFixture(StrictModel):
    evidence_id: str = Field(min_length=1)
    record_sha256: Sha256
    course_id: str = Field(min_length=1)
    gold_text: str = Field(min_length=1)
    necessary_neighbors: list[str] = Field(default_factory=list)
    source_document_id: str = Field(min_length=1)
    source_document_version: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content_sha256: Sha256


class P14KnowledgePointFixture(StrictModel):
    gold_kp_id: str = Field(min_length=1)
    record_sha256: Sha256
    course_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    importance: Literal["core", "supporting"]
    section_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class P14ContextFixture(StrictModel):
    context_package_id: str = Field(min_length=1)
    purpose: Literal["lesson_generation"]
    course_id: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    content_hash: Sha256
    trace_id: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    evidence_records: list[P14EvidenceFixture] = Field(min_length=1)
    citation_map: dict[str, list[str]] = Field(min_length=1)
    token_count: int = Field(ge=0)
    retrieval_trace_summary: dict[str, str | int | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_citations(self) -> P14ContextFixture:
        available = {item.evidence_id for item in self.evidence_records}
        if set(self.evidence_ids) != available:
            raise ValueError("Context fixture evidence_ids must match evidence_records")
        if any(set(ids) - available for ids in self.citation_map.values()):
            raise ValueError("Context fixture citation_map contains unknown Evidence")
        return self


class P14ReviewScenario(StrictModel):
    plan_action: Literal["approve", "edit", "replan"]
    field_edits: dict[str, str] = Field(default_factory=dict)
    replan_instruction: str | None = None
    final_export_approved: bool = True
    writeback_scope: Literal["none", "verified_lesson_fragment"] = "none"

    @model_validator(mode="after")
    def validate_action(self) -> P14ReviewScenario:
        if self.plan_action == "edit" and not self.field_edits:
            raise ValueError("edit review scenarios require field_edits")
        if self.plan_action == "replan" and not self.replan_instruction:
            raise ValueError("replan review scenarios require replan_instruction")
        if self.writeback_scope == "verified_lesson_fragment" and not self.final_export_approved:
            raise ValueError("verified fragment writeback requires export approval")
        return self


class P14LessonTaskCase(ReviewableRecord):
    case_role: Literal["gold_pilot"] = "gold_pilot"
    course_id: str = Field(min_length=1)
    template_id: Literal[
        "lesson_standard_university_v1",
        "lesson_seminar_v1",
        "lesson_lab_practice_v1",
    ]
    chapter_range: str = Field(min_length=1)
    teaching_focus: str = Field(min_length=1)
    total_sessions: int = Field(ge=1, le=12)
    session_duration: int = Field(ge=15, le=240)
    audience: str = Field(min_length=1)
    required_knowledge_point_ids: list[str] = Field(min_length=1)
    optional_knowledge_point_ids: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(min_length=1)
    required_activity_types: list[str] = Field(min_length=1)
    forbidden_claims: list[str] = Field(default_factory=list)
    required_interrupts: list[str] = Field(min_length=2)
    context_fixture_id: str = Field(min_length=1)
    knowledge_point_snapshot: list[P14KnowledgePointFixture] = Field(min_length=1)
    review_scenario: P14ReviewScenario
    rubric_version: Literal["coursepilot.lesson-rubric.v1"] = "coursepilot.lesson-rubric.v1"
    source_provenance: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_required_links(self) -> P14LessonTaskCase:
        snapshot_ids = {item.gold_kp_id for item in self.knowledge_point_snapshot}
        if set(self.required_knowledge_point_ids) - snapshot_ids:
            raise ValueError("required Knowledge Points must be present in the snapshot")
        if set(self.optional_knowledge_point_ids) & set(self.required_knowledge_point_ids):
            raise ValueError("optional and required Knowledge Points must be disjoint")
        if "lesson_session_plan_review" not in self.required_interrupts:
            raise ValueError("P14 Pilot requires Session Plan Review")
        if "lesson_final_review" not in self.required_interrupts:
            raise ValueError("P14 Pilot requires Final Review")
        return self


class P14InsufficientEvidenceCase(StrictModel):
    record_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    required_knowledge_point_ids: list[str] = Field(min_length=1)
    context_fixture_id: str = Field(min_length=1)
    omitted_required_evidence_ids: list[str] = Field(min_length=1)
    expected_failure: Literal["context_insufficient_evidence"] = "context_insufficient_evidence"
    provider_calls_allowed: Literal[0] = 0
    side_effects_allowed: Literal[0] = 0


class P14FixtureBundle(StrictModel):
    schema_version: Literal["coursepilot.cp-ds1-p14-fixtures.v1"] = (
        "coursepilot.cp-ds1-p14-fixtures.v1"
    )
    context_fixtures: list[P14ContextFixture] = Field(min_length=4)
    negative_case: P14InsufficientEvidenceCase


class CPDS1P14PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds1-p14-pilot.v1"] = "coursepilot.cp-ds1-p14-pilot.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: Literal["p14-pilot-r1"] = "p14-pilot-r1"
    approval_scope: Literal["cp_ds1_p14_pilot_input_only"] = "cp_ds1_p14_pilot_input_only"
    cases: list[P14LessonTaskCase] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_pilot_distribution(self) -> CPDS1P14PilotDataset:
        if {case.template_id for case in self.cases} != {
            "lesson_standard_university_v1",
            "lesson_seminar_v1",
            "lesson_lab_practice_v1",
        }:
            raise ValueError("P14 Pilot must cover all three built-in Lesson templates")
        if len({case.course_id for case in self.cases}) != 2:
            raise ValueError("P14 Pilot must use both approved CourseRAG courses")
        return self


class P14ReviewDecision(StrictModel):
    record_id: str = Field(min_length=1)
    decision: Literal["pass", "return"]
    notes: str = ""

    @model_validator(mode="after")
    def validate_return_reason(self) -> P14ReviewDecision:
        if self.decision == "return" and not self.notes.strip():
            raise ValueError("returned P14 records require a reason")
        return self


class P14ReviewDecisions(StrictModel):
    schema_version: Literal["coursepilot.p14-review-decisions.v1"] = (
        "coursepilot.p14-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    expected_record_ids: list[str] = Field(min_length=3, max_length=3)
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    attestation_source: Literal["html_export", "conversation_exact_bundle_approval"]
    decisions: list[P14ReviewDecision] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_complete_review(self) -> P14ReviewDecisions:
        decision_ids = [item.record_id for item in self.decisions]
        if decision_ids != self.expected_record_ids:
            raise ValueError("P14 review decisions must match the expected record order")
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("P14 review decision IDs must be unique")
        return self


class P14BundleApproval(StrictModel):
    schema_version: Literal["coursepilot.p14-cp-ds1-bundle-approval.v1"] = (
        "coursepilot.p14-cp-ds1-bundle-approval.v1"
    )
    bundle_sha256: Sha256
    candidate_hashes: dict[str, Sha256]
    candidate_record_sha256: dict[str, Sha256]
    approved_record_sha256: dict[str, Sha256]
    approved_dataset_sha256: Sha256
    first_review_sha256: Sha256
    second_review_sha256: Sha256
    record_count: int = Field(ge=3, le=3)
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    review_id: str = Field(min_length=1)
    scope: Literal["cp_ds1_p14_pilot_input_only"] = "cp_ds1_p14_pilot_input_only"
    external_provider_calls: Literal[0] = 0
    final_coursepilot_gold_promoted: Literal[False] = False


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


class P15EvidenceFixture(StrictModel):
    evidence_id: str = Field(min_length=1)
    record_sha256: Sha256
    course_id: str = Field(min_length=1)
    gold_text: str = Field(min_length=1)
    necessary_neighbors: list[str] = Field(default_factory=list)
    source_document_id: str = Field(min_length=1)
    source_document_version: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_type: Literal["native_text", "ocr_derived"]
    semantic_unit_type: str = Field(min_length=1)
    content_sha256: Sha256


class P15KnowledgePointFixture(StrictModel):
    gold_kp_id: str = Field(min_length=1)
    record_sha256: Sha256
    course_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    section_ids: list[str] = Field(min_length=1)


class P15AssessmentTarget(ReviewableRecord):
    target_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    knowledge_point: P15KnowledgePointFixture
    primary_evidence: P15EvidenceFixture
    supporting_evidence: list[P15EvidenceFixture] = Field(default_factory=list)
    allowed_question_types: list[
        Literal["single_choice", "multiple_choice", "judgement", "short_answer"]
    ] = Field(min_length=1)
    content_role: Literal[
        "definition",
        "principle",
        "procedure",
        "comparison",
        "application",
        "formula",
        "table",
        "example",
    ]
    difficulty_range: list[Literal["easy", "medium", "hard"]] = Field(min_length=1)
    required_claims: list[str] = Field(min_length=1)
    optional_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    hard_negative_evidence_ids: list[str] = Field(default_factory=list)
    hard_negative_evidence: list[P15EvidenceFixture] = Field(default_factory=list)
    risk_flags: list[Literal["formula", "table", "ocr", "hard_negative"]] = Field(
        default_factory=list
    )
    source_provenance: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> P15AssessmentTarget:
        evidence = [self.primary_evidence, *self.supporting_evidence]
        if any(item.course_id != self.course_id for item in evidence):
            raise ValueError("Assessment Target Evidence must remain in the same course")
        if self.knowledge_point.course_id != self.course_id:
            raise ValueError("Assessment Target Knowledge Point must remain in the same course")
        if any(item.course_id != self.course_id for item in self.hard_negative_evidence):
            raise ValueError("Hard Negative Evidence must remain in the same course")
        if [
            item.evidence_id for item in self.hard_negative_evidence
        ] != self.hard_negative_evidence_ids:
            raise ValueError("Hard Negative IDs and readable snapshots must match")
        if "formula" in self.risk_flags and self.content_role != "formula":
            raise ValueError("formula risk requires formula content role")
        if "table" in self.risk_flags and self.content_role != "table":
            raise ValueError("table risk requires table content role")
        if "ocr" in self.risk_flags and self.primary_evidence.source_type != "ocr_derived":
            raise ValueError("ocr risk requires an OCR-derived primary Evidence")
        return self


class P15QuestionBatchPlan(StrictModel):
    batch_id: str = Field(min_length=1)
    question_type: Literal["single_choice", "multiple_choice", "judgement", "short_answer"]
    question_count: int = Field(ge=1)
    target_ids: list[str] = Field(min_length=1)


class P15BlueprintGold(StrictModel):
    case_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    template_id: Literal[
        "exam_chapter_assignment_v1",
        "exam_unit_quiz_v1",
        "exam_midterm_final_v1",
    ]
    chapter_range: str = Field(min_length=1)
    question_counts: dict[
        Literal["single_choice", "multiple_choice", "judgement", "short_answer"], int
    ]
    score_per_question: dict[
        Literal["single_choice", "multiple_choice", "judgement", "short_answer"], int
    ]
    difficulty_distribution: dict[Literal["easy", "medium", "hard"], float]
    difficulty_counts: dict[Literal["easy", "medium", "hard"], int]
    required_total_score: int = Field(ge=1)
    required_knowledge_point_ids: list[str] = Field(min_length=1)
    required_evidence_ids: list[str] = Field(min_length=1)
    target_ids: list[str] = Field(min_length=1)
    batch_plan: list[P15QuestionBatchPlan] = Field(min_length=1)
    context_package_id: str = Field(min_length=1)
    max_concurrency: int = Field(ge=1, le=8)
    blueprint_review_action: Literal["approve", "edit_resume", "replan"]
    global_review_action: Literal["approve", "edit_resume", "replan"]
    source_provenance: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_blueprint_math(self) -> P15BlueprintGold:
        if sum(self.question_counts.values()) != sum(self.difficulty_counts.values()):
            raise ValueError("question and difficulty counts must have the same total")
        score = sum(
            self.question_counts[key] * self.score_per_question[key] for key in self.question_counts
        )
        if score != self.required_total_score:
            raise ValueError("required_total_score must equal question count times score")
        if abs(sum(self.difficulty_distribution.values()) - 1.0) > 1e-6:
            raise ValueError("difficulty_distribution must sum to one")
        if sum(batch.question_count for batch in self.batch_plan) != sum(
            self.question_counts.values()
        ):
            raise ValueError("batch plan must cover every planned question")
        return self


class P15ExamPilotCase(ReviewableRecord):
    case_role: Literal["gold_pilot"] = "gold_pilot"
    blueprint: P15BlueprintGold
    track_b_query_id: str = Field(min_length=1)
    target_ids: list[str] = Field(min_length=1)
    required_interrupts: list[Literal["exam_blueprint_review", "exam_global_review"]] = Field(
        min_length=2, max_length=2
    )

    @model_validator(mode="after")
    def validate_case_links(self) -> P15ExamPilotCase:
        if self.blueprint.case_id != self.record_id:
            raise ValueError("P15 case and Blueprint IDs must match")
        if self.target_ids != self.blueprint.target_ids:
            raise ValueError("P15 case target IDs must match Blueprint target IDs")
        if set(self.required_interrupts) != {"exam_blueprint_review", "exam_global_review"}:
            raise ValueError("P15 Pilot requires Blueprint and Global Review interrupts")
        return self


class P15ContextFixture(StrictModel):
    context_package_id: str = Field(min_length=1)
    purpose: Literal["exam_generation"]
    case_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    evidence_records: list[P15EvidenceFixture] = Field(min_length=1)
    target_ids: list[str] = Field(min_length=1)
    content_hash: Sha256
    token_count: int = Field(ge=0)


class P15InsufficientEvidenceCase(StrictModel):
    record_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    required_target_ids: list[str] = Field(min_length=1)
    omitted_required_evidence_ids: list[str] = Field(min_length=1)
    context_package_id: str = Field(min_length=1)
    expected_failure: Literal["context_insufficient_evidence"] = "context_insufficient_evidence"
    provider_calls_allowed: Literal[0] = 0
    side_effects_allowed: Literal[0] = 0


class P15ConstraintConflictCase(StrictModel):
    record_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    question_counts: dict[str, int]
    score_per_question: dict[str, int]
    required_total_score: int = Field(ge=1)
    computed_total_score: int = Field(ge=1)
    expected_failure: Literal["blueprint_constraint_conflict"] = "blueprint_constraint_conflict"
    provider_calls_allowed: Literal[0] = 0
    side_effects_allowed: Literal[0] = 0


class P15FixtureBundle(StrictModel):
    schema_version: Literal["coursepilot.cp-ds2-p15-fixtures.v1"] = (
        "coursepilot.cp-ds2-p15-fixtures.v1"
    )
    context_fixtures: list[P15ContextFixture] = Field(min_length=3)
    insufficient_evidence_case: P15InsufficientEvidenceCase
    constraint_conflict_case: P15ConstraintConflictCase


class CPDS2P15PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds2-p15-pilot.v1"] = "coursepilot.cp-ds2-p15-pilot.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: Literal["p15-pilot-r1"] = "p15-pilot-r1"
    approval_scope: Literal["cp_ds2_p15_pilot_input_only"] = "cp_ds2_p15_pilot_input_only"
    cases: list[P15ExamPilotCase] = Field(min_length=3, max_length=3)
    targets: list[P15AssessmentTarget] = Field(min_length=26, max_length=26)

    @model_validator(mode="after")
    def validate_pilot(self) -> CPDS2P15PilotDataset:
        if {item.blueprint.template_id for item in self.cases} != {
            "exam_chapter_assignment_v1",
            "exam_unit_quiz_v1",
            "exam_midterm_final_v1",
        }:
            raise ValueError("P15 Pilot must cover all three built-in Exam templates")
        target_ids = {item.target_id for item in self.targets}
        linked = {target_id for case in self.cases for target_id in case.target_ids}
        if target_ids != linked:
            raise ValueError("P15 targets must be linked exactly once by the Pilot cases")
        return self


class P15ReviewDecision(StrictModel):
    record_id: str = Field(min_length=1)
    decision: Literal["pass", "return"]
    notes: str = ""

    @model_validator(mode="after")
    def validate_return_reason(self) -> P15ReviewDecision:
        if self.decision == "return" and not self.notes.strip():
            raise ValueError("returned P15 records require a reason")
        return self


class P15ReviewDecisions(StrictModel):
    schema_version: Literal["coursepilot.p15-review-decisions.v1"] = (
        "coursepilot.p15-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    expected_record_ids: list[str] = Field(min_length=1, max_length=64)
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    attestation_source: Literal["html_export", "conversation_exact_bundle_approval"]
    decisions: list[P15ReviewDecision] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_complete_review(self) -> P15ReviewDecisions:
        decision_ids = [item.record_id for item in self.decisions]
        if decision_ids != self.expected_record_ids:
            raise ValueError("P15 review decisions must match expected record order")
        if len(set(decision_ids)) != len(decision_ids):
            raise ValueError("P15 review decision IDs must be unique")
        return self


class P15BundleApproval(StrictModel):
    schema_version: Literal["coursepilot.p15-cp-ds2-bundle-approval.v1"] = (
        "coursepilot.p15-cp-ds2-bundle-approval.v1"
    )
    bundle_sha256: Sha256
    candidate_hashes: dict[str, Sha256]
    candidate_record_sha256: dict[str, Sha256]
    approved_record_sha256: dict[str, Sha256]
    approved_dataset_sha256: Sha256
    first_review_sha256: Sha256
    second_review_sha256: Sha256
    record_count: int = Field(ge=29, le=29)
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    review_id: str = Field(min_length=1)
    scope: Literal["cp_ds2_p15_pilot_input_only"] = "cp_ds2_p15_pilot_input_only"
    external_provider_calls: Literal[0] = 0
    final_coursepilot_gold_promoted: Literal[False] = False


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


class P16EvidenceSnapshot(StrictModel):
    evidence_id: str = Field(min_length=1)
    record_sha256: Sha256
    course_id: str = Field(min_length=1)
    gold_text: str = Field(min_length=1)
    necessary_neighbors: list[str] = Field(default_factory=list)
    source_document_id: str = Field(min_length=1)
    source_document_version: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    source_type: Literal["native_text", "ocr_derived"]
    content_sha256: Sha256


class P16KnowledgePointSnapshot(StrictModel):
    gold_kp_id: str = Field(min_length=1)
    record_sha256: Sha256
    course_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    importance: Literal["core", "supporting"]
    evidence_ids: list[str] = Field(min_length=1)


class P16SlideTargetGold(StrictModel):
    slide_id: str = Field(min_length=1)
    slide_index: int = Field(ge=1)
    slide_type: Literal[
        "title",
        "agenda",
        "objectives",
        "concept",
        "process",
        "comparison",
        "example",
        "activity",
        "summary",
        "references",
    ]
    title_intent: str = Field(min_length=1)
    source_session_index: int | None = Field(default=None, ge=1)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    required_claims: list[str] = Field(default_factory=list)
    layout_role: str = Field(min_length=1)
    max_bullets: int = Field(default=6, ge=1, le=20)
    max_chars_per_bullet: int = Field(default=80, ge=10, le=500)
    notes_required: bool = True
    citation_required: bool = True
    asset_kind: Literal["none", "editable_table", "editable_shape", "replaceable_image"] = "none"
    risk_flags: list[
        Literal[
            "formula",
            "table",
            "ocr",
            "qkv_source",
            "encoder_process",
            "attention_comparison",
            "structure_placeholder",
            "calculation_example",
            "training_process",
            "occupation_risk_comparison",
        ]
    ] = Field(default_factory=list)
    evidence_snapshots: list[P16EvidenceSnapshot] = Field(default_factory=list)
    knowledge_point_snapshots: list[P16KnowledgePointSnapshot] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_target(self) -> P16SlideTargetGold:
        evidence_ids = {item.evidence_id for item in self.evidence_snapshots}
        kp_ids = {item.gold_kp_id for item in self.knowledge_point_snapshots}
        if set(self.evidence_ids) != evidence_ids:
            raise ValueError("P16 slide Evidence IDs must match readable snapshots")
        if set(self.knowledge_point_ids) != kp_ids:
            raise ValueError("P16 slide Knowledge Point IDs must match readable snapshots")
        if (
            self.citation_required
            and self.slide_type not in {"title", "agenda"}
            and not self.evidence_ids
        ):
            raise ValueError("factual P16 slides require direct Evidence")
        if self.asset_kind == "editable_table" and self.slide_type not in {"example", "comparison"}:
            raise ValueError("editable tables are restricted to example/comparison slides")
        return self


class P16PPTPilotCase(ReviewableRecord):
    case_role: Literal["gold_pilot"] = "gold_pilot"
    course_id: str = Field(min_length=1)
    template_id: Literal[
        "ppt_standard_lecture_v1",
        "ppt_concept_explanation_v1",
        "ppt_case_seminar_v1",
    ]
    lesson_artifact_id: str = Field(min_length=1)
    lesson_artifact_sha256: Sha256
    slide_count: int = Field(ge=3, le=80)
    include_references: bool = True
    include_speaker_notes: bool = True
    required_slide_types: list[str] = Field(min_length=1)
    slide_targets: list[P16SlideTargetGold] = Field(min_length=3)
    required_interrupts: list[Literal["ppt_architecture_review", "ppt_final_review"]] = Field(
        min_length=2, max_length=2
    )
    source_provenance: list[str] = Field(min_length=1)
    forbidden_claims: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_case(self) -> P16PPTPilotCase:
        if len(self.slide_targets) != self.slide_count:
            raise ValueError("P16 slide target count must equal slide_count")
        if [item.slide_index for item in self.slide_targets] != list(
            range(1, self.slide_count + 1)
        ):
            raise ValueError("P16 slide indexes must be contiguous")
        slide_types = {str(item.slide_type) for item in self.slide_targets}
        if not slide_types.issubset(set(self.required_slide_types)):
            raise ValueError("P16 required_slide_types must cover every slide type")
        if set(self.required_interrupts) != {"ppt_architecture_review", "ppt_final_review"}:
            raise ValueError("P16 Pilot requires Architecture and Final Review interrupts")
        for target in self.slide_targets:
            if any(item.course_id != self.course_id for item in target.evidence_snapshots):
                raise ValueError("P16 Evidence cannot cross courses")
            if any(item.course_id != self.course_id for item in target.knowledge_point_snapshots):
                raise ValueError("P16 Knowledge Points cannot cross courses")
        return self


class CPDS3P16PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds3-p16-pilot.v1"] = "coursepilot.cp-ds3-p16-pilot.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: Literal["p16-pilot-r1", "p16-pilot-r2"] = "p16-pilot-r1"
    approval_scope: Literal["cp_ds3_p16_pilot_input_only"] = "cp_ds3_p16_pilot_input_only"
    cases: list[P16PPTPilotCase] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_distribution(self) -> CPDS3P16PilotDataset:
        expected = {
            "ppt_standard_lecture_v1": 24,
            "ppt_concept_explanation_v1": 12,
            "ppt_case_seminar_v1": 10,
        }
        actual = {case.template_id: case.slide_count for case in self.cases}
        if actual != expected:
            raise ValueError(f"P16 CP-DS3 requires exact template/page distribution: {expected}")
        if sum(actual.values()) != 46:
            raise ValueError("P16 CP-DS3 requires 46 slides")
        return self


class P16TemplateRenderSnapshot(StrictModel):
    renderer_image: str = Field(min_length=1)
    renderer_version: Literal["7.4.7.2"] = "7.4.7.2"
    poppler_version: Literal["22.12.0"] = "22.12.0"
    source_pptx_sha256: Sha256
    rendered_pdf_sha256: Sha256
    slide_png_sha256s: list[Sha256] = Field(min_length=1)
    slide_count: int = Field(ge=1)
    repeat_render_pngs_identical: bool
    editable_shape_count: int = Field(ge=1)
    editable_table_count: int = Field(ge=0)
    editable_picture_count: int = Field(ge=0)
    placeholder_count: int = Field(ge=1)
    notes_slide_count: int = Field(ge=0)
    image_only_slide_count: int = Field(ge=0)
    source_theme_fonts: list[str] = Field(default_factory=list)
    rendered_pdf_fonts: list[str] = Field(default_factory=list)
    declared_font_fallbacks: list[str] = Field(default_factory=list)
    preview_paths: list[str] = Field(min_length=1)
    visible_template_findings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_render_snapshot(self) -> P16TemplateRenderSnapshot:
        if len(self.slide_png_sha256s) != self.slide_count:
            raise ValueError("P16 render PNG count must equal slide_count")
        if len(self.preview_paths) != self.slide_count:
            raise ValueError("P16 render preview count must equal slide_count")
        if not self.repeat_render_pngs_identical:
            raise ValueError("P16 fixed renderer snapshots must repeat exactly")
        return self


class P16TemplateImportCase(ReviewableRecord):
    case_role: Literal["gold_positive", "contract_negative"]
    artifact_type: Literal["ppt"] = "ppt"
    template_id: str = Field(min_length=1)
    template_version: str = Field(min_length=1)
    custom_template: bool
    source_kind: Literal["builtin", "owner_selected_external", "tampered", "incomplete_mapping"]
    source_uri: str = Field(min_length=1)
    source_sha256: Sha256
    normalized_pptx_sha256: Sha256 | None = None
    license: str = Field(min_length=1)
    master_count: int = Field(ge=0)
    layout_count: int = Field(ge=0)
    required_layout_roles: list[str] = Field(min_length=1)
    slide_type_layout_map: dict[str, str] = Field(min_length=1)
    required_placeholders: list[str] = Field(min_length=1)
    expected_file_roles: list[str] = Field(default_factory=list)
    render_required: bool = True
    source_provenance: list[str] = Field(min_length=1)
    expected_failure: (
        Literal["template_identity_mismatch", "template_mapping_incomplete"] | None
    ) = None
    render_snapshot: P16TemplateRenderSnapshot | None = None

    @model_validator(mode="after")
    def validate_template_case(self) -> P16TemplateImportCase:
        if self.case_role == "gold_positive" and self.expected_failure is not None:
            raise ValueError("positive template cases cannot have expected failures")
        if self.case_role == "contract_negative" and self.expected_failure is None:
            raise ValueError("negative template cases require an expected failure")
        if self.case_role == "gold_positive" and set(self.required_layout_roles) - set(
            self.slide_type_layout_map.values()
        ):
            raise ValueError("every required layout role must have a mapping")
        if self.source_kind == "owner_selected_external" and not self.custom_template:
            raise ValueError("external template must be marked custom_template")
        return self


class CPDS7P16PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds7-p16-pilot.v1"] = "coursepilot.cp-ds7-p16-pilot.v1"
    dataset_id: Literal["coursepilot-eval"] = "coursepilot-eval"
    dataset_version: Literal["p16-pilot-r1", "p16-pilot-r2"] = "p16-pilot-r1"
    approval_scope: Literal["cp_ds7_p16_pilot_input_only"] = "cp_ds7_p16_pilot_input_only"
    cases: list[P16TemplateImportCase] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_distribution(self) -> CPDS7P16PilotDataset:
        positive = [item for item in self.cases if item.case_role == "gold_positive"]
        negative = [item for item in self.cases if item.case_role == "contract_negative"]
        if len(positive) != 4 or len(negative) != 2:
            raise ValueError("P16 CP-DS7 requires four positive and two negative cases")
        if {item.template_id for item in positive} != {
            "ppt_standard_lecture_v1",
            "ppt_concept_explanation_v1",
            "ppt_case_seminar_v1",
            "p16_external_velis_v1",
        }:
            raise ValueError("P16 CP-DS7 positives must cover three built-ins and Velis")
        if self.dataset_version == "p16-pilot-r2" and any(
            item.render_snapshot is None for item in positive
        ):
            raise ValueError("P16 r2 template positives require fixed renderer snapshots")
        return self


class P16ReviewDecision(StrictModel):
    record_id: str = Field(min_length=1)
    decision: Literal["pass", "return"]
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_return_reason(self) -> P16ReviewDecision:
        if self.decision == "return" and not self.notes.strip():
            raise ValueError("P16 returned records require a reason")
        return self


class P16ReviewDecisions(StrictModel):
    schema_version: Literal["coursepilot.p16-review-decisions.v1"] = (
        "coursepilot.p16-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    expected_record_ids: list[str] = Field(min_length=1)
    decisions: list[P16ReviewDecision]

    @model_validator(mode="after")
    def validate_complete_review(self) -> P16ReviewDecisions:
        actual = [item.record_id for item in self.decisions]
        if actual != self.expected_record_ids:
            raise ValueError("P16 review decisions must match the expected record order")
        if len(set(actual)) != len(actual):
            raise ValueError("P16 review decision IDs must be unique")
        return self


class P16BundleManifest(StrictModel):
    schema_version: Literal["coursepilot.p16-cp-ds37-bundle-manifest.v1"] = (
        "coursepilot.p16-cp-ds37-bundle-manifest.v1"
    )
    bundle_sha256: Sha256
    candidate_hashes: dict[str, Sha256]
    record_hashes: dict[str, Sha256]
    record_counts: dict[str, int]
    upstream_hashes: dict[str, Sha256]
    external_template: dict[str, str]
    renderer_preflight: dict[str, bool | str]
    render_artifacts: dict[str, Sha256] = Field(default_factory=dict)
    review_sets: dict[str, list[str]] = Field(default_factory=dict)
    approval_scope: Literal["cp_ds3_and_cp_ds7_p16_pilot_input_only"] = (
        "cp_ds3_and_cp_ds7_p16_pilot_input_only"
    )
    gold_promotion: bool = False
    external_provider_calls: int = Field(default=0, ge=0)


class P16BundleApproval(StrictModel):
    schema_version: Literal["coursepilot.p16-bundle-approval.v1"] = (
        "coursepilot.p16-bundle-approval.v1"
    )
    bundle_sha256: Sha256
    candidate_hashes: dict[str, Sha256]
    record_hashes: dict[str, Sha256]
    approved_dataset_hashes: dict[str, Sha256]
    approved_record_hashes: dict[str, Sha256]
    record_approvals: dict[str, ApprovalRecord]
    first_review_sha256: Sha256
    second_review_sha256: Sha256
    record_count: Literal[55] = 55
    reviewer_id: str = Field(min_length=1)
    reviewed_at: datetime
    review_id: str = Field(min_length=1)
    approval_scope: Literal["cp_ds3_and_cp_ds7_p16_pilot_input_only"] = (
        "cp_ds3_and_cp_ds7_p16_pilot_input_only"
    )
    external_provider_calls: Literal[0] = 0
    final_coursepilot_gold_promoted: Literal[False] = False


class IssueScope(StrictModel):
    artifact_type: Literal["lesson", "exam", "ppt"]
    item_id: str | None = None
    json_path: str = Field(pattern=r"^\$")


class ValidationIssue(StrictModel):
    issue_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_.:-]+$")
    code: str = Field(min_length=1, max_length=160)
    severity: Literal["info", "warning", "error", "critical"]
    layer: Literal["L0", "L1", "L2", "L3", "L4"] = "L1"
    scope: IssueScope
    allowed_parent_paths: list[str] = Field(default_factory=list)
    auto_repairable: bool
    message: str = ""
    expected: object | None = None
    actual: object | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    repair_strategy: str = "deterministic_patch"


class ValidationFaultCase(ReviewableRecord):
    artifact_type: Literal["lesson", "exam", "ppt"]
    artifact_fixture_id: str
    injection_ids: list[str] = Field(default_factory=list)
    gold_issues: list[ValidationIssue] = Field(default_factory=list)
    clean_artifact: bool = False
    fixture_variant_id: str | None = None
    injection_paths: list[str] = Field(default_factory=list)
    source_provenance: list[str] = Field(default_factory=list)


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
    source_fault_case_id: str | None = None
    fixture_variant_id: str | None = None
    repair_strategy: str = "deterministic_patch"
    preconditions: list[str] = Field(default_factory=list)
    preservation_paths: list[str] = Field(default_factory=list)
    issue_layers: list[Literal["L0", "L1", "L2", "L3", "L4"]] = Field(default_factory=list)


class CPDS5RepairDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds5.v1"] = "coursepilot.cp-ds5.v1"
    cases: list[RepairCase] = Field(default_factory=list)


class CPDS4P13PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds4-p13.v1"] = "coursepilot.cp-ds4-p13.v1"
    dataset_version: Literal["p13-pilot-r1"] = "p13-pilot-r1"
    cases: list[ValidationFaultCase] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_distribution(self) -> CPDS4P13PilotDataset:
        counts = {
            kind: sum(item.artifact_type == kind for item in self.cases)
            for kind in ("lesson", "exam", "ppt")
        }
        if counts != {"lesson": 10, "exam": 10, "ppt": 10}:
            raise ValueError("P13 CP-DS4 requires ten Lesson, Exam and PPT cases")
        if sum(item.clean_artifact for item in self.cases) != 3:
            raise ValueError("P13 CP-DS4 requires one clean control per artifact type")
        return self


class CPDS5P13PilotDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds5-p13.v1"] = "coursepilot.cp-ds5-p13.v1"
    dataset_version: Literal["p13-pilot-r1"] = "p13-pilot-r1"
    cases: list[RepairCase] = Field(min_length=15, max_length=15)

    @model_validator(mode="after")
    def validate_distribution(self) -> CPDS5P13PilotDataset:
        counts = {
            kind: sum(item.artifact_type == kind for item in self.cases)
            for kind in ("lesson", "exam", "ppt")
        }
        if counts != {"lesson": 5, "exam": 5, "ppt": 5}:
            raise ValueError("P13 CP-DS5 requires five Lesson, Exam and PPT cases")
        return self


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


class P17FaultVariant(StrictModel):
    variant_id: str
    preconditions: list[str] = Field(default_factory=list)
    injection: str
    expected_error_class: str
    expected_user_status: str
    retryable: bool = False
    required_trace_fields: list[str] = Field(default_factory=list)
    expected_side_effect_count: int = Field(ge=0)
    forbidden_effects: list[str] = Field(default_factory=list)
    resume_expectation: str | None = None
    postconditions: list[str] = Field(default_factory=list)


class P17FaultSecurityCase(ReviewableRecord):
    category: Literal["provider", "courserag", "worker", "persistence", "security"]
    course_id: str | None = None
    scenario_family: str
    initial_state: dict[str, str | int | bool | None] = Field(min_length=1)
    injection_point: str
    variants: list[P17FaultVariant] = Field(min_length=1)
    trace_assertions: list[str] = Field(default_factory=list)
    forbidden_side_effects: list[str] = Field(default_factory=list)
    source_kind: Literal["contract_fixture", "course_grounded_security_wrapper"]


class CPDS8P17Dataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.cp-ds8-p17.v1"] = "coursepilot.cp-ds8-p17.v1"
    approval_scope: Literal["cp_ds8_p17_pilot_input_only"] = "cp_ds8_p17_pilot_input_only"
    cases: list[P17FaultSecurityCase] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_distribution(self) -> CPDS8P17Dataset:
        if len(self.cases) != 30:
            raise ValueError("P17 CP-DS8 requires exactly 30 scenarios")
        if sum(len(case.variants) for case in self.cases) != 34:
            raise ValueError("P17 CP-DS8 requires exactly 34 execution variants")
        return self


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


class P17JourneyStep(StrictModel):
    step_index: int = Field(ge=1)
    action: str
    state_before: str | None = None
    expected_state: str
    required_trace: list[str] = Field(default_factory=list)
    expected_side_effect_count: int = Field(ge=0)
    version_transition: str | None = None
    assertions: list[str] = Field(default_factory=list)


class P17SystemJourneyCase(ReviewableRecord):
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
    input_source: str
    upstream_artifact_refs: list[str] = Field(min_length=1)
    steps: list[P17JourneyStep] = Field(min_length=2)
    expected_final_status: str
    expected_side_effects: list[str] = Field(default_factory=list)
    forbidden_side_effects: list[str] = Field(default_factory=list)
    trace_version_assertions: list[str] = Field(default_factory=list)
    fixture_details: dict[str, str] = Field(default_factory=dict)


class SYSDS1P17Dataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.sys-ds1-p17.v1"] = "coursepilot.sys-ds1-p17.v1"
    approval_scope: Literal["sys_ds1_p17_pilot_input_only"] = "sys_ds1_p17_pilot_input_only"
    cases: list[P17SystemJourneyCase] = Field(min_length=8, max_length=8)

    @model_validator(mode="after")
    def validate_distribution(self) -> SYSDS1P17Dataset:
        expected = {
            "lesson",
            "exam",
            "ppt",
            "writeback_loop",
            "fault_recovery",
            "insufficient_evidence",
            "malicious_material",
            "version_change",
        }
        if {case.journey_type for case in self.cases} != expected:
            raise ValueError("P17 SYS-DS1 requires all eight canonical journey types")
        return self


class SYSDS1JourneyDataset(DatasetEnvelope):
    schema_version: Literal["coursepilot.sys-ds1.v1"] = "coursepilot.sys-ds1.v1"
    cases: list[SystemJourneyCase] = Field(default_factory=list)


CoursePilotDataset = Annotated[
    CPDS0ManifestDataset
    | CPDS1LessonDataset
    | CPDS1P14PilotDataset
    | CPDS2ExamDataset
    | CPDS2P15PilotDataset
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
