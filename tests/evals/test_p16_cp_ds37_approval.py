from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from coursepilot.evals.formal_schemas import (
    CPDS3P16PilotDataset,
    CPDS7P16PilotDataset,
    P16BundleApproval,
    P16ReviewDecisions,
)
from evaluation.p16_cp_ds37_approval import (
    APPROVAL_PATH,
    APPROVED_DS3,
    APPROVED_DS7,
    FIRST_REVIEW_PATH,
    SECOND_REVIEW_PATH,
    approve_p16_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_SHA = "e8fa261a4bc8066432072255f18ed7e4fb3d607eeee74ffde29b840e212f4f91"


def test_p16_approved_bundle_is_complete_and_pilot_scoped() -> None:
    ds3 = CPDS3P16PilotDataset.model_validate_json(
        (ROOT / APPROVED_DS3).read_text(encoding="utf-8")
    )
    ds7 = CPDS7P16PilotDataset.model_validate_json(
        (ROOT / APPROVED_DS7).read_text(encoding="utf-8")
    )
    approval = P16BundleApproval.model_validate_json(
        (ROOT / APPROVAL_PATH).read_text(encoding="utf-8")
    )
    assert all(case.review_status == "approved" and case.approval for case in ds3.cases)
    assert all(case.review_status == "approved" and case.approval for case in ds7.cases)
    assert approval.bundle_sha256 == BUNDLE_SHA
    assert approval.record_count == 55
    assert len(approval.record_approvals) == 55
    assert approval.external_provider_calls == 0
    assert approval.final_coursepilot_gold_promoted is False


def test_p16_reviews_and_governance_are_consistent() -> None:
    first = P16ReviewDecisions.model_validate_json(
        (ROOT / FIRST_REVIEW_PATH).read_text(encoding="utf-8")
    )
    second = P16ReviewDecisions.model_validate_json(
        (ROOT / SECOND_REVIEW_PATH).read_text(encoding="utf-8")
    )
    assert len(first.decisions) == 55
    assert len(second.decisions) == 23
    assert all(item.decision == "pass" for item in [*first.decisions, *second.decisions])
    manifest = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["gold_components"]["cp_ds3_p16_pilot"] == "approved"
    assert manifest["gold_components"]["cp_ds7_p16_pilot"] == "approved"
    assert manifest["gold_status"] == "p18_formal_gold_approved"
    assert manifest["phase_input_status"]["p16"] == "completed_gate_passed"
    assert manifest["phase_execution_status"]["p16"] == "completed_with_quality_debt"


def test_p16_approval_is_idempotent_and_rejects_wrong_bundle() -> None:
    approval = P16BundleApproval.model_validate_json(
        (ROOT / APPROVAL_PATH).read_text(encoding="utf-8")
    )
    source_root = Path("storage_eval/cpds37_p16_review") / BUNDLE_SHA
    result = approve_p16_bundle(
        repository_root=ROOT,
        expected_bundle_sha256=BUNDLE_SHA,
        reviewer_id=approval.reviewer_id,
        reviewed_at=approval.reviewed_at,
        review_id=approval.review_id,
        first_review_path=source_root / "p16_first_review_e8fa261a4bc8.json",
        second_review_path=source_root / "p16_second_review_e8fa261a4bc8.json",
    )
    assert result["approval_sha256"]
    with pytest.raises(ValueError, match="literal P16 Bundle"):
        approve_p16_bundle(
            repository_root=ROOT,
            expected_bundle_sha256="0" * 64,
            reviewer_id=approval.reviewer_id,
            reviewed_at=datetime.fromisoformat(approval.reviewed_at.isoformat()),
            review_id=approval.review_id,
            first_review_path=source_root / "p16_first_review_e8fa261a4bc8.json",
            second_review_path=source_root / "p16_second_review_e8fa261a4bc8.json",
        )
