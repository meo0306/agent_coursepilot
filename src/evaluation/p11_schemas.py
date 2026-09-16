"""Evaluation-only contracts for the pre-P11 foundation input work package."""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from evaluation.contracts import HashedArtifact, Sha256, StrictModel

P11Component = Literal["foundation_manifest", "template_contract", "model_gateway", "runtime"]


class P11SourceReference(StrictModel):
    authority: Literal[
        "frozen_document",
        "b0_snapshot",
        "p10_contract",
        "approved_dev_gold",
        "owner_approved_waiver",
        "failed_profile_report",
        "blind_commitment",
    ]
    relative_path: str = Field(min_length=1, max_length=1024)
    sha256: Sha256
    section: str = Field(min_length=1, max_length=240)


class P11FoundationIdentityContract(StrictModel):
    frozen_document_hashes: dict[str, Sha256]
    b0_interface_snapshot_sha256: Sha256
    p10_frozen_manifest_sha256: Sha256 | None = None
    p10_contract_sha256: Sha256 | None = None
    logical_template_ids: list[str] = Field(min_length=9, max_length=9)
    physical_template_roles: list[str] = Field(min_length=5, max_length=5)
    model_profile_ids: list[str] = Field(min_length=6, max_length=6)
    runtime_binding_status: Literal["pending_p11_output"] = "pending_p11_output"
    template_registry_sha256: None = None
    prompt_manifest_sha256: None = None
    model_capability_manifest_sha256: None = None
    state_schema_sha256: None = None
    artifact_schema_sha256: None = None
    migration_sha256: None = None


class P11TemplateContract(StrictModel):
    template_id: str = Field(min_length=1, max_length=160)
    artifact_type: Literal["lesson", "exam", "ppt"]
    input_schema_role: str = Field(min_length=1, max_length=160)
    output_schema_role: str = Field(min_length=1, max_length=160)
    planner_prompt_profile: str = Field(min_length=1, max_length=160)
    generator_prompt_profile: str = Field(min_length=1, max_length=160)
    validator_profile: str = Field(min_length=1, max_length=160)
    repair_profile: str = Field(min_length=1, max_length=160)
    model_route_profile: str = Field(min_length=1, max_length=160)
    exporter_profile: str = Field(min_length=1, max_length=160)
    default_parameters: list[str] = Field(min_length=1)
    required_snapshot_fields: list[str] = Field(min_length=1)
    physical_resource_roles: list[str] = Field(min_length=1)
    visual_quality_in_scope: Literal[False] = False


class P11ModelGatewayContract(StrictModel):
    requested_profile: str = Field(min_length=1, max_length=160)
    fake_provider_capabilities: list[str]
    invocation_condition: str = Field(min_length=1, max_length=1000)
    expected_resolution: str = Field(min_length=1, max_length=2000)
    expected_trace_fields: list[str] = Field(min_length=1)
    external_provider_calls: Literal[0] = 0


class P11CourseRAGContract(StrictModel):
    scenario: Literal["docx_dev", "pdf_dev", "fail_closed"]
    dev_query_id: str | None = Field(default=None, max_length=160)
    expected_course_id: str | None = Field(default=None, max_length=160)
    approved_query_record_sha256: Sha256 | None = None
    context_contract_version: str = Field(min_length=1, max_length=160)
    expected_context_fields: list[str] = Field(min_length=1)
    test_or_holdout_ids_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_query_identity(self) -> P11CourseRAGContract:
        if self.scenario == "fail_closed":
            if self.dev_query_id is not None or self.approved_query_record_sha256 is not None:
                raise ValueError("fail-closed fixture must not bind an Approved query")
        elif self.dev_query_id is None or self.approved_query_record_sha256 is None:
            raise ValueError("normal CourseRAG fixtures require one Approved Dev query")
        return self


class P11FoundationCase(StrictModel):
    record_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    component: P11Component
    title: str = Field(min_length=1, max_length=240)
    dependency: Literal["independent", "p10_d013_waiver"] = "independent"
    input_fixture: list[str] = Field(min_length=1)
    expected_behavior: list[str] = Field(min_length=1)
    forbidden_behavior: list[str] = Field(min_length=1)
    pass_conditions: list[str] = Field(min_length=1)
    source_references: list[P11SourceReference] = Field(min_length=1)
    foundation_contract: P11FoundationIdentityContract | None = None
    template_contract: P11TemplateContract | None = None
    model_gateway_contract: P11ModelGatewayContract | None = None
    courserag_contract: P11CourseRAGContract | None = None

    @model_validator(mode="after")
    def validate_component_detail(self) -> P11FoundationCase:
        detail_count = sum(
            detail is not None
            for detail in (
                self.foundation_contract,
                self.template_contract,
                self.model_gateway_contract,
                self.courserag_contract,
            )
        )
        expected_detail = self.component != "runtime" or self.dependency == "p10_d013_waiver"
        if detail_count != int(expected_detail):
            raise ValueError("P11 case detail does not match component/dependency")
        if self.component == "foundation_manifest" and self.foundation_contract is None:
            raise ValueError("foundation manifest case requires its identity contract")
        if self.component == "template_contract" and self.template_contract is None:
            raise ValueError("template case requires a template contract")
        if self.component == "model_gateway" and self.model_gateway_contract is None:
            raise ValueError("model case requires a gateway contract")
        if self.dependency == "p10_d013_waiver" and self.courserag_contract is None:
            raise ValueError("deferred runtime case requires a CourseRAG contract")
        return self


class P11FoundationDraftDataset(StrictModel):
    schema_version: Literal["coursepilot.p11-foundation-draft.v1"] = (
        "coursepilot.p11-foundation-draft.v1"
    )
    dataset_id: Literal["coursepilot-p11-foundation-input"] = "coursepilot-p11-foundation-input"
    dataset_version: Literal["r1-draft"] = "r1-draft"
    status: Literal["independent_draft_incomplete"] = "independent_draft_incomplete"
    target_record_count: Literal[40] = 40
    records: list[P11FoundationCase] = Field(min_length=37, max_length=37)

    @model_validator(mode="after")
    def validate_draft(self) -> P11FoundationDraftDataset:
        _validate_unique_ids(self.records)
        if any(item.dependency != "independent" for item in self.records):
            raise ValueError("37-record Draft must contain only independent cases")
        _validate_component_counts(
            self.records,
            {"foundation_manifest": 1, "template_contract": 9, "model_gateway": 12, "runtime": 15},
        )
        return self


class P11DraftBundleManifest(StrictModel):
    schema_version: Literal["coursepilot.p11-foundation-draft-manifest.v1"] = (
        "coursepilot.p11-foundation-draft-manifest.v1"
    )
    state: Literal["draft_incomplete"] = "draft_incomplete"
    target_count: Literal[40] = 40
    present_count: Literal[37] = 37
    expected_record_ids: list[str] = Field(min_length=40, max_length=40)
    present_record_ids: list[str] = Field(min_length=37, max_length=37)
    missing_record_ids: list[str] = Field(min_length=3, max_length=3)
    unexpected_record_ids: list[str] = Field(default_factory=list, max_length=0)
    draft_artifact: HashedArtifact
    generation_strategy_sha256: Sha256
    p10_gate_audit: HashedArtifact

    @model_validator(mode="after")
    def validate_sets(self) -> P11DraftBundleManifest:
        expected, present, missing = map(
            set, (self.expected_record_ids, self.present_record_ids, self.missing_record_ids)
        )
        if len(expected) != 40 or len(present) != 37 or len(missing) != 3:
            raise ValueError("P11 Draft IDs must be unique")
        if present | missing != expected or present & missing:
            raise ValueError("P11 Draft present/missing partition differs from expected IDs")
        return self


class P11P10GateCheck(StrictModel):
    check_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    passed: bool
    observed: str = Field(min_length=1, max_length=2000)
    required: str = Field(min_length=1, max_length=2000)


class P11P10GateAudit(StrictModel):
    schema_version: Literal["coursepilot.p11-p10-gate-audit.v1"] = (
        "coursepilot.p11-p10-gate-audit.v1"
    )
    eligible_for_full_candidate: bool
    checks: list[P11P10GateCheck] = Field(min_length=1)
    deferred_record_ids: list[str] = Field(min_length=3, max_length=3)
    disposition: Literal["fail_closed_draft_only", "eligible_for_candidate"]
    eligibility_basis: Literal["p10_exit_gate", "p10_d013_dependency_waiver"]
    security_profile_status: Literal["candidate_rejected_default_off"]
    p11_inherited_security_constraints: list[str] = Field(min_length=6)

    @model_validator(mode="after")
    def validate_disposition(self) -> P11P10GateAudit:
        all_passed = all(item.passed for item in self.checks)
        if self.eligible_for_full_candidate != all_passed:
            raise ValueError("P10 gate eligibility must equal conjunction of checks")
        if all_passed != (self.disposition == "eligible_for_candidate"):
            raise ValueError("P10 gate disposition differs from eligibility")
        return self


class P11FoundationCandidateDataset(StrictModel):
    schema_version: Literal["coursepilot.p11-foundation-input.v1"] = (
        "coursepilot.p11-foundation-input.v1"
    )
    dataset_id: Literal["coursepilot-p11-foundation-input"] = "coursepilot-p11-foundation-input"
    dataset_version: Literal["r1"] = "r1"
    approval_scope: Literal["p11_foundation_input_contract_only"] = (
        "p11_foundation_input_contract_only"
    )
    records: list[P11FoundationCase] = Field(min_length=40, max_length=40)

    @model_validator(mode="after")
    def validate_candidate(self) -> P11FoundationCandidateDataset:
        _validate_unique_ids(self.records)
        _validate_component_counts(
            self.records,
            {"foundation_manifest": 1, "template_contract": 9, "model_gateway": 12, "runtime": 18},
        )
        if sum(item.dependency == "p10_d013_waiver" for item in self.records) != 3:
            raise ValueError("P11 Candidate requires exactly three P10-D013-bound cases")
        return self


class P11CandidateBundleManifest(StrictModel):
    schema_version: Literal["coursepilot.p11-foundation-bundle-manifest.v1"] = (
        "coursepilot.p11-foundation-bundle-manifest.v1"
    )
    state: Literal["candidate_pending_course_owner"] = "candidate_pending_course_owner"
    bundle_sha256: Sha256
    predecessor_draft_sha256: Sha256
    candidate: HashedArtifact
    candidate_record_sha256: dict[str, Sha256]
    first_review_ids: list[str] = Field(min_length=40, max_length=40)
    second_review_ids: list[str] = Field(min_length=27, max_length=27)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    second_review_index_sha256: Sha256
    p10_frozen_manifest: HashedArtifact
    p10_contract: HashedArtifact
    p10_d013_decision_log: HashedArtifact
    p10_d013_quality_policy: HashedArtifact
    p10_d013_execution_status: HashedArtifact
    p10_3_failed_profile_report: HashedArtifact
    p10_3_blind_commitment: HashedArtifact
    p10_3_profile_emitted: Literal[False] = False
    p10_3_blind_content_visible: Literal[False] = False
    p10_3_runtime_default: Literal["legacy_rules"] = "legacy_rules"
    inherited_security_constraints: list[str] = Field(min_length=6)


class P11ReviewDecision(StrictModel):
    record_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    decision: Literal["pass", "return"]
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_note(self) -> P11ReviewDecision:
        if self.decision == "return" and not self.notes.strip():
            raise ValueError("returned P11 records require a note")
        return self


class P11ReviewDecisions(StrictModel):
    schema_version: Literal["coursepilot.p11-foundation-review-decisions.v1"] = (
        "coursepilot.p11-foundation-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    expected_record_ids: list[str] = Field(min_length=1)
    decisions: list[P11ReviewDecision] = Field(min_length=1)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime

    @model_validator(mode="after")
    def validate_complete(self) -> P11ReviewDecisions:
        expected = self.expected_record_ids
        actual = [item.record_id for item in self.decisions]
        if len(expected) != len(set(expected)) or len(actual) != len(set(actual)):
            raise ValueError("P11 review IDs must be unique")
        if set(expected) != set(actual):
            raise ValueError("P11 review decisions must exactly cover expected IDs")
        return self


class P11FoundationApproval(StrictModel):
    schema_version: Literal["coursepilot.p11-foundation-approval.v1"] = (
        "coursepilot.p11-foundation-approval.v1"
    )
    bundle_sha256: Sha256
    approval_scope: Literal["p11_foundation_input_contract_only"] = (
        "p11_foundation_input_contract_only"
    )
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    review_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    candidate: HashedArtifact
    approved_work_package: HashedArtifact
    candidate_record_sha256: dict[str, Sha256]
    first_review_decisions: HashedArtifact
    second_review_decisions: HashedArtifact
    gold_status_after: Literal["skeleton_no_formal_gold"] = "skeleton_no_formal_gold"
    formal_gold_promoted: Literal[False] = False
    p11_start_authorized: Literal[True] = True


class P11RuntimeFoundationSnapshot(StrictModel):
    schema_version: Literal["coursepilot.p11-runtime-foundation-snapshot.v1"] = (
        "coursepilot.p11-runtime-foundation-snapshot.v1"
    )
    bundle_sha256: Sha256
    template_resource_hashes: dict[str, Sha256]
    model_profile_manifest_sha256: Sha256
    capability_manifest_sha256: Sha256
    prompt_manifest_sha256: Sha256
    state_schema_sha256: Sha256
    artifact_schema_sha256: Sha256
    template_snapshot_schema_sha256: Sha256
    p10_contract_sha256: Sha256
    p10_frozen_manifest_sha256: Sha256
    migration_version: str = Field(min_length=1, max_length=160)
    migration_sha256: Sha256
    b0_compatibility_report_sha256: Sha256
    p11_test_report_sha256: Sha256
    p11_phase_report_sha256: Sha256
    legacy_compatibility_roles: list[Literal["validator", "repair", "exporter"]] = Field(
        min_length=3, max_length=3
    )


def _validate_unique_ids(records: list[P11FoundationCase]) -> None:
    ids = [item.record_id for item in records]
    if len(ids) != len(set(ids)):
        raise ValueError("P11 record IDs must be unique")


def _validate_component_counts(records: list[P11FoundationCase], expected: dict[str, int]) -> None:
    actual = {name: sum(item.component == name for item in records) for name in expected}
    if actual != expected:
        raise ValueError(f"P11 component counts differ: expected={expected}, actual={actual}")


def identity_sha256(value: object) -> str:
    import json

    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
