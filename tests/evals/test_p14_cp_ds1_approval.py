from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from coursepilot.evals.formal_schemas import (
    CPDS1P14PilotDataset,
    P14BundleApproval,
    P14ReviewDecisions,
)
from evaluation.p14_cp_ds1_approval import (
    APPROVAL_PATH,
    APPROVED_PATH,
    FIRST_REVIEW_PATH,
    SECOND_REVIEW_PATH,
    approve_p14_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_SHA = "3e47c85c624ab0c3a751b34de38a8b1147a0d6187314ef9a27210b85cc9c1708"


def test_p14_approved_bundle_is_complete_and_pilot_scoped() -> None:
    dataset = CPDS1P14PilotDataset.model_validate_json(
        (ROOT / APPROVED_PATH).read_text(encoding="utf-8")
    )
    approval = P14BundleApproval.model_validate_json(
        (ROOT / APPROVAL_PATH).read_text(encoding="utf-8")
    )
    assert len(dataset.cases) == 3
    assert all(item.review_status == "approved" and item.approval for item in dataset.cases)
    assert approval.bundle_sha256 == BUNDLE_SHA
    assert approval.record_count == 3
    assert approval.external_provider_calls == 0
    assert approval.final_coursepilot_gold_promoted is False


def test_p14_conversation_reviews_and_governance_are_consistent() -> None:
    first = P14ReviewDecisions.model_validate_json(
        (ROOT / FIRST_REVIEW_PATH).read_text(encoding="utf-8")
    )
    second = P14ReviewDecisions.model_validate_json(
        (ROOT / SECOND_REVIEW_PATH).read_text(encoding="utf-8")
    )
    assert first.review_pass == "first"
    assert second.review_pass == "second"
    assert first.attestation_source == "conversation_exact_bundle_approval"
    assert second.attestation_source == "conversation_exact_bundle_approval"
    assert all(item.decision == "pass" for item in [*first.decisions, *second.decisions])
    manifest = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["gold_components"]["cp_ds1_p14_pilot"] == "approved"
    assert manifest["gold_status"] == "p18_formal_gold_approved"
    assert manifest["phase_input_status"]["p14"] == "completed_gate_passed"
    assert manifest["phase_execution_status"]["p14"] == "completed_with_quality_debt"
    dev_ids = (ROOT / "datasets/coursepilot_eval/v1/splits/dev_ids.txt").read_text(encoding="utf-8")
    test_ids = (ROOT / "datasets/coursepilot_eval/v1/splits/test_ids.txt").read_text(
        encoding="utf-8"
    )
    business_prefixes = ("p18-lesson-", "p18-exam-", "p18-ppt-")
    assert sum(item.startswith(business_prefixes) for item in dev_ids.splitlines()) == 18
    assert sum(item.startswith(business_prefixes) for item in test_ids.splitlines()) == 12


def test_p14_approval_is_idempotent_and_rejects_wrong_bundle() -> None:
    approval = P14BundleApproval.model_validate_json(
        (ROOT / APPROVAL_PATH).read_text(encoding="utf-8")
    )
    result = approve_p14_bundle(
        repository_root=ROOT,
        expected_bundle_sha256=BUNDLE_SHA,
        reviewer_id=approval.reviewer_id,
        reviewed_at=approval.reviewed_at,
        review_id=approval.review_id,
    )
    assert result["approval_sha256"]
    with pytest.raises(ValueError, match="literal P14 CP-DS1 Pilot Bundle"):
        approve_p14_bundle(
            repository_root=ROOT,
            expected_bundle_sha256="0" * 64,
            reviewer_id=approval.reviewer_id,
            reviewed_at=datetime.fromisoformat(approval.reviewed_at.isoformat()),
            review_id=approval.review_id,
        )
