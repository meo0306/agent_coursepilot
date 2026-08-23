from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from evaluation.p12_cp_ds6_approval import approve_p12_cp_ds6

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_SHA = "e0b854c2fe261571b6319447e9e0feabd732e67a1b509e121ddb18b3ae1701a1"


def test_p12_approved_package_and_governance_are_hash_bound() -> None:
    result = approve_p12_cp_ds6(
        repository_root=ROOT,
        expected_candidate_sha256=CANDIDATE_SHA,
        reviewer_id="course_owner",
        reviewed_at=datetime.fromisoformat("2026-08-13T00:00:00+08:00"),
        review_id="p12-cp-ds6-input-approval-e0b854c2",
    )
    assert result["formal_gold_promoted"] is False
    assert result["record_count"] == 24
    approval = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/provenance/p12_cp_ds6_approval.json").read_text(
            encoding="utf-8"
        )
    )
    assert approval["candidate_sha256"] == CANDIDATE_SHA
    assert len(approval["candidate_record_sha256"]) == 24
    assert len(approval["approved_record_sha256"]) == 24
    manifest = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["gold_status"] == "p17_integration_pilot_approved"
    assert manifest["phase_input_status"]["p12"] == "completed_gate_passed"
    assert manifest["phase_input_status"]["p13"] == "completed_gate_passed"
    assert '"locked": false' in (ROOT / "datasets/coursepilot_eval/v1/test.lock.json").read_text(
        encoding="utf-8"
    )


def test_p12_approval_replay_is_idempotent() -> None:
    first = approve_p12_cp_ds6(
        repository_root=ROOT,
        expected_candidate_sha256=CANDIDATE_SHA,
        reviewer_id="course_owner",
        reviewed_at=datetime.fromisoformat("2026-08-13T00:00:00+08:00"),
        review_id="p12-cp-ds6-input-approval-e0b854c2",
    )
    second = approve_p12_cp_ds6(
        repository_root=ROOT,
        expected_candidate_sha256=CANDIDATE_SHA,
        reviewer_id="course_owner",
        reviewed_at=datetime.fromisoformat("2026-08-13T00:00:00+08:00"),
        review_id="p12-cp-ds6-input-approval-e0b854c2",
    )
    assert first == second
