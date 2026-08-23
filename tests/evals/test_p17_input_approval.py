from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS8P17Dataset, SYSDS1P17Dataset
from evaluation.p10_schemas import P17SecurityQualificationDataset
from evaluation.p17_input_approval import approve_p17_inputs

CP_ROOT = Path("datasets/coursepilot_eval/v1")
SECURITY_ROOT = Path("datasets/courserag_eval/releases/p17_security")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p17_approved_datasets_have_complete_record_approvals() -> None:
    faults = CPDS8P17Dataset.model_validate_json(
        (CP_ROOT / "approved/cp_ds8/p17_fault_security.json").read_text(encoding="utf-8")
    )
    journeys = SYSDS1P17Dataset.model_validate_json(
        (CP_ROOT / "approved/sys_ds1/p17_system_journeys.json").read_text(encoding="utf-8")
    )
    security = P17SecurityQualificationDataset.model_validate_json(
        (SECURITY_ROOT / "approved/qualification_dev.json").read_text(encoding="utf-8")
    )
    assert len(faults.cases) == 30
    assert len(journeys.cases) == 8
    assert len(security.cases) == 120
    assert all(
        item.approval is not None and item.review_status == "approved" for item in faults.cases
    )
    assert all(
        item.approval is not None and item.review_status == "approved" for item in journeys.cases
    )
    assert all(
        item.approval is not None and item.review_status == "approved" for item in security.cases
    )


def test_p17_approval_governance_preserves_blind_boundary() -> None:
    cp_manifest = _load(CP_ROOT / "manifest.json")
    cr_manifest = _load(Path("datasets/courserag_eval/v1/manifest.json"))
    blind = _load(SECURITY_ROOT / "blind_commitment.json")
    security_approval = _load(SECURITY_ROOT / "approved/qualification_dev_approval.json")
    assert cp_manifest["gold_components"]["cp_ds8_p17_pilot"] == "approved"
    assert cp_manifest["gold_components"]["sys_ds1_p17_pilot"] == "approved"
    assert cp_manifest["phase_input_status"]["p17"] == "formal_dev_eval_ready"
    assert cr_manifest["gold_components"]["p17_security_qualification_dev"] == "approved"
    assert blind["content_status"] == "empty_unread"
    assert security_approval["blind_content_status"] == "empty_unread"


def test_p17_normalized_reviews_cover_all_final_records() -> None:
    integration = _load(CP_ROOT / "reviews/p17_integration_review_decisions.json")
    security = _load(SECURITY_ROOT / "approved/review_decisions.json")
    assert integration["reviewer_id"] == "course_owner"
    assert security["reviewer_id"] == "course_owner"
    assert len(integration["records"]) == 38
    assert len(security["records"]) == 120
    assert all(item["decision"] == "approve" for item in integration["records"])
    assert all(item["decision"] == "approve" for item in security["records"])


def test_p17_approval_replay_is_idempotent() -> None:
    result = approve_p17_inputs(
        repository_root=Path("."),
        integration_bundle_sha256=(
            "c44c94779b83731a3a3029498703ff3929173e36637272faac548ed2662bc7d1"
        ),
        security_bundle_sha256=("be1f7a235b5c40e55b8b6814b78f8759d17b4987dfcbe0175af3ab099f869b8b"),
        reviewed_at=datetime(2099, 1, 1, tzinfo=UTC),
    )
    assert result["approved_record_counts"] == {"integration": 38, "security": 120}
    assert result["blind_content_status"] == "empty_unread"
