from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from coursepilot.evals.formal_schemas import (
    CPDS0ManifestDataset,
    CPManifestRecord,
    P11FoundationInputBinding,
)
from evaluation.p11_foundation_approval import approve_p11_foundation
from evaluation.p11_foundation_data import (
    CANDIDATE_MANIFEST_PATH,
    CANDIDATE_PATH,
    DATASET_ROOT,
    DEFERRED_IDS,
    DRAFT_MANIFEST_PATH,
    DRAFT_PATH,
    SECOND_REVIEW_IDS,
    audit_p10_gate,
    build_independent_records,
    compile_candidate,
)
from evaluation.p11_schemas import (
    P11CandidateBundleManifest,
    P11DraftBundleManifest,
    P11FoundationCandidateDataset,
    P11FoundationDraftDataset,
    P11ReviewDecisions,
)

ROOT = Path(__file__).resolve().parents[2]


def test_p11_draft_is_exactly_37_and_candidate_is_exactly_40() -> None:
    draft = P11FoundationDraftDataset.model_validate_json(
        (ROOT / DRAFT_PATH).read_text(encoding="utf-8")
    )
    manifest = P11DraftBundleManifest.model_validate_json(
        (ROOT / DRAFT_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert len(draft.records) == 37
    assert len({item.record_id for item in draft.records}) == 37
    assert {
        kind: sum(item.component == kind for item in draft.records)
        for kind in ("foundation_manifest", "template_contract", "model_gateway", "runtime")
    } == {"foundation_manifest": 1, "template_contract": 9, "model_gateway": 12, "runtime": 15}
    assert manifest.missing_record_ids == list(DEFERRED_IDS)
    assert set(manifest.present_record_ids) | set(manifest.missing_record_ids) == set(
        manifest.expected_record_ids
    )
    candidate = P11FoundationCandidateDataset.model_validate_json(
        (ROOT / CANDIDATE_PATH).read_text(encoding="utf-8")
    )
    assert len(candidate.records) == 40
    assert {item.record_id for item in candidate.records[-3:]} == set(DEFERRED_IDS)
    assert all(item.dependency == "p10_d013_waiver" for item in candidate.records[-3:])


def test_p11_candidate_binds_d013_failure_and_inherited_constraints() -> None:
    manifest = P11CandidateBundleManifest.model_validate_json(
        (ROOT / CANDIDATE_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    gate = audit_p10_gate(ROOT)
    assert manifest.p10_3_failed_profile_report.sha256 == (
        "26e5eb98bfe08536987cd8a6b36d769ce3e3370319f8479d57c15b1ba596f0bb"
    )
    assert not manifest.p10_3_profile_emitted
    assert not manifest.p10_3_blind_content_visible
    assert manifest.p10_3_runtime_default == "legacy_rules"
    assert manifest.inherited_security_constraints == gate.p11_inherited_security_constraints
    assert gate.security_profile_status == "candidate_rejected_default_off"


def test_p11_invalid_waiver_blocks_candidate_compilation() -> None:
    draft = P11FoundationDraftDataset(records=build_independent_records(ROOT))
    gate = audit_p10_gate(ROOT)
    assert gate.disposition == "eligible_for_candidate"
    invalid = gate.model_copy(
        update={
            "eligible_for_full_candidate": False,
            "disposition": "fail_closed_draft_only",
        }
    )
    with pytest.raises(ValueError, match="P10-D013"):
        compile_candidate(ROOT, draft, invalid)


def test_p11_second_review_is_fixed_27() -> None:
    assert len(SECOND_REVIEW_IDS) == 27
    assert len(set(SECOND_REVIEW_IDS)) == 27
    manifest = P11DraftBundleManifest.model_validate_json(
        (ROOT / DRAFT_MANIFEST_PATH).read_text(encoding="utf-8")
    )
    assert set(SECOND_REVIEW_IDS).issubset(set(manifest.expected_record_ids))


def test_p11_frozen_template_profile_and_security_sets_are_exact() -> None:
    draft = P11FoundationDraftDataset.model_validate_json(
        (ROOT / DRAFT_PATH).read_text(encoding="utf-8")
    )
    foundation = draft.records[0].foundation_contract
    assert foundation is not None
    assert set(foundation.logical_template_ids) == {
        "lesson_standard_university_v1",
        "lesson_seminar_v1",
        "lesson_lab_practice_v1",
        "exam_chapter_assignment_v1",
        "exam_unit_quiz_v1",
        "exam_midterm_final_v1",
        "ppt_standard_lecture_v1",
        "ppt_concept_explanation_v1",
        "ppt_case_seminar_v1",
    }
    assert set(foundation.model_profile_ids) == {
        "planner_main",
        "generator_main",
        "content_repair_main",
        "classifier_light",
        "json_repair_light",
        "compression_light",
    }
    assert foundation.runtime_binding_status == "pending_p11_output"
    assert foundation.template_registry_sha256 is None
    serialized = (ROOT / DRAFT_PATH).read_text(encoding="utf-8")
    assert re.search(r"sk-[A-Za-z0-9]{20,}", serialized) is None
    assert "api_key" not in serialized.lower()
    assert "D:\\" not in serialized


def test_p11_review_requires_exact_coverage_and_return_note() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        P11ReviewDecisions(
            bundle_sha256="0" * 64,
            review_pass="first",
            expected_record_ids=["a", "b"],
            decisions=[{"record_id": "a", "decision": "pass", "notes": ""}],
            reviewer_id="course_owner",
            reviewed_at=now,
        )
    with pytest.raises(ValidationError):
        P11ReviewDecisions(
            bundle_sha256="0" * 64,
            review_pass="first",
            expected_record_ids=["a"],
            decisions=[{"record_id": "a", "decision": "return", "notes": ""}],
            reviewer_id="course_owner",
            reviewed_at=now,
        )


def test_legacy_cpds0_record_remains_valid_and_future_hashes_are_guarded() -> None:
    record = CPManifestRecord(
        record_id="legacy-cp-ds0",
        graph_version="legacy",
        courserag_fixture_version="legacy",
        template_registry_version="legacy",
        validator_version="legacy",
        repair_policy_version="legacy",
        exporter_version="legacy",
        rubric_version="legacy",
    )
    CPDS0ManifestDataset(dataset_id="legacy", dataset_version="v1", records=[record])
    with pytest.raises(ValidationError, match="pending P11 bindings"):
        P11FoundationInputBinding(
            frozen_document_hashes={"doc": "1" * 64},
            b0_interface_snapshot_sha256="2" * 64,
            p10_frozen_manifest_sha256="3" * 64,
            p10_contract_sha256="4" * 64,
            logical_template_ids=[f"t-{index}" for index in range(9)],
            model_profile_ids=[f"p-{index}" for index in range(6)],
            binding_status="pending_p11_output",
            template_registry_sha256="5" * 64,
        )


def test_p11_approval_rejects_wrong_bundle_hash() -> None:
    with pytest.raises(ValueError, match="literal P11"):
        approve_p11_foundation(
            repository_root=ROOT,
            expected_bundle_sha256="0" * 64,
            first_review_path=ROOT / "missing-first.json",
            second_review_path=ROOT / "missing-second.json",
            reviewer_id="course_owner",
            reviewed_at=datetime.now(UTC),
            review_id="p11-review-test",
        )


def test_p11_existing_approval_replays_after_governance_reporting_changes() -> None:
    result = approve_p11_foundation(
        repository_root=ROOT,
        expected_bundle_sha256=("ed28509cfbfdba2c530b91b63fa879f1dd50700bd8b4ca4858c271838fb25522"),
        first_review_path=ROOT / "unused-after-approval-first.json",
        second_review_path=ROOT / "unused-after-approval-second.json",
        reviewer_id="course_owner",
        reviewed_at=datetime.fromisoformat("2026-08-12T15:47:36.648000+00:00"),
        review_id="p11-foundation-input-approval-ed28509cfbfd",
    )
    assert result["approval_sha256"] == (
        "09b2525848469d219590c373095415dc454de7d37590aeb2ab68990dce4fc234"
    )
    assert result["p11_start_authorized"] is True
    assert result["formal_gold_promoted"] is False


def test_coursepilot_formal_splits_and_lock_reflect_consumed_p18_release() -> None:
    dataset_root = ROOT / DATASET_ROOT
    manifest = (dataset_root / "manifest.json").read_text(encoding="utf-8")
    lock = (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    dev_ids = (dataset_root / "splits/dev_ids.txt").read_text(encoding="utf-8").splitlines()
    test_ids = (dataset_root / "splits/test_ids.txt").read_text(encoding="utf-8").splitlines()
    business_prefixes = ("p18-lesson-", "p18-exam-", "p18-ppt-")
    assert '"gold_status": "p18_formal_gold_approved"' in manifest
    assert sum(item.startswith(business_prefixes) for item in dev_ids) == 18
    assert sum(item.startswith(business_prefixes) for item in test_ids) == 12
    assert '"locked": true' in lock
    assert '"locked_by": "course_owner"' in lock
