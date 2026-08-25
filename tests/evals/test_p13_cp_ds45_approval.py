from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from coursepilot.evals.formal_schemas import CPDS4P13PilotDataset, CPDS5P13PilotDataset
from evaluation.p13_cp_ds45_approval import (
    APPROVAL_PATH,
    APPROVED_DS4_PATH,
    APPROVED_DS5_PATH,
    FIRST_REVIEW_PATH,
    SECOND_REVIEW_PATH,
    approve_p13_bundle,
)

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_SHA = "b436f6e1901bb9447359e4fd0524f27ba39bfa24742b3ec006e451ae0bec9cd0"


def test_p13_approved_bundle_is_complete_and_still_pilot_scoped() -> None:
    ds4 = CPDS4P13PilotDataset.model_validate_json(
        (ROOT / APPROVED_DS4_PATH).read_text(encoding="utf-8")
    )
    ds5 = CPDS5P13PilotDataset.model_validate_json(
        (ROOT / APPROVED_DS5_PATH).read_text(encoding="utf-8")
    )
    assert len(ds4.cases) == 30
    assert len(ds5.cases) == 15
    assert all(item.review_status == "approved" and item.approval for item in ds4.cases)
    assert all(item.review_status == "approved" and item.approval for item in ds5.cases)
    approval = json.loads((ROOT / APPROVAL_PATH).read_text(encoding="utf-8"))
    assert approval["bundle_sha256"] == BUNDLE_SHA
    assert approval["record_count"] == {"cp_ds4": 30, "cp_ds5": 15, "total": 45}
    assert approval["p13_formal_eval_ready"] is True
    assert approval["final_coursepilot_gold_promoted"] is False


def test_p13_approved_reviews_and_governance_are_consistent() -> None:
    first = json.loads((ROOT / FIRST_REVIEW_PATH).read_text(encoding="utf-8"))
    second = json.loads((ROOT / SECOND_REVIEW_PATH).read_text(encoding="utf-8"))
    assert len(first["decisions"]) == 45
    assert len(second["decisions"]) == 27
    assert all(item["decision"] == "pass" for item in [*first["decisions"], *second["decisions"]])
    manifest = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["gold_components"]["cp_ds1_p14_pilot"] == "approved"
    assert manifest["gold_components"]["cp_ds4_p13_pilot"] == "approved"
    assert manifest["gold_components"]["cp_ds5_p13_pilot"] == "approved"
    assert manifest["gold_components"]["cp_ds2_p15_pilot"] == "approved"
    assert manifest["gold_status"] == "p18_formal_gold_approved"
    assert manifest["phase_input_status"]["p13"] == "completed_gate_passed"
    assert manifest["phase_execution_status"]["p13"] == "completed"
    dev_ids = (ROOT / "datasets/coursepilot_eval/v1/splits/dev_ids.txt").read_text(encoding="utf-8")
    test_ids = (ROOT / "datasets/coursepilot_eval/v1/splits/test_ids.txt").read_text(
        encoding="utf-8"
    )
    business_prefixes = ("p18-lesson-", "p18-exam-", "p18-ppt-")
    assert sum(item.startswith(business_prefixes) for item in dev_ids.splitlines()) == 18
    assert sum(item.startswith(business_prefixes) for item in test_ids.splitlines()) == 12


def test_p13_approval_is_idempotent_and_rejects_wrong_bundle() -> None:
    approval = json.loads((ROOT / APPROVAL_PATH).read_text(encoding="utf-8"))
    review_root = ROOT / "storage_eval/cpds45_p13_review" / BUNDLE_SHA
    result = approve_p13_bundle(
        repository_root=ROOT,
        expected_bundle_sha256=BUNDLE_SHA,
        first_review_path=review_root / "p13_first_review_b436f6e1901b.json",
        second_review_path=review_root / "p13_second_review_b436f6e1901b.json",
        reviewer_id="course_owner",
        reviewed_at=datetime.fromisoformat(approval["reviewed_at"]),
        review_id=approval["review_id"],
    )
    assert result["approval_sha256"]
    with pytest.raises(ValueError, match="literal P13 Gold Bundle"):
        approve_p13_bundle(
            repository_root=ROOT,
            expected_bundle_sha256="0" * 64,
            first_review_path=review_root / "p13_first_review_b436f6e1901b.json",
            second_review_path=review_root / "p13_second_review_b436f6e1901b.json",
            reviewer_id="course_owner",
            reviewed_at=datetime.fromisoformat(approval["reviewed_at"]),
            review_id=approval["review_id"],
        )
