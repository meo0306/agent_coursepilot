from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from evaluation.datasets import (
    COURSEPILOT_SPECS,
    COURSERAG_SPECS,
    load_dataset_inventory,
)
from evaluation.p18_formal_approval import (
    BUSINESS_SHA,
    INTEGRATION_SHA,
    QUALITY_SHA,
    approve_p18_formal,
)
from evaluation.p18_schemas import P18FormalApproval

ROOT = Path("datasets/coursepilot_eval/v1")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_p18_formal_approval_outputs_and_boundaries() -> None:
    approval = P18FormalApproval.model_validate(
        _load(ROOT / "provenance/p18_formal_gold_approval.json")
    )
    assert approval.approved_record_count == 208
    assert not approval.cp_ds0_created
    assert not approval.test_locked
    assert set(approval.approved_dataset_sha256s) == {
        "cp_ds1",
        "cp_ds2",
        "cp_ds3",
        "cp_ds4",
        "cp_ds5",
        "cp_ds6",
        "cp_ds7",
        "cp_ds8",
        "sys_ds1",
    }
    # The approval record describes the historical pre-freeze boundary.  The
    # repository itself is now in the separately authorized locked-Test state.
    assert _load(ROOT / "test.lock.json")["locked"]
    assert not (ROOT / "approved/cp_ds0/p18_runtime_foundation.json").exists()

    manifest = _load(ROOT / "manifest.json")
    assert manifest["gold_status"] == "p18_formal_gold_approved"
    assert manifest["phase_input_status"]["p18"] == "formal_dev_eval_ready"
    assert manifest["p18_test_lock_status"] == "locked_owner_authorized"

    splits = _load(ROOT / "provenance/p18_component_splits.json")
    business_dev = sum(
        len(splits["components"][component]["dev"]) for component in ("cp_ds1", "cp_ds2", "cp_ds3")
    )
    business_test = sum(
        len(splits["components"][component]["test"]) for component in ("cp_ds1", "cp_ds2", "cp_ds3")
    )
    assert (business_dev, business_test) == (18, 12)
    assert splits["global_test_lock_required_for_test_and_blind"]


def test_p18_approved_inventory_validates_and_approval_is_idempotent() -> None:
    inventory = load_dataset_inventory(ROOT, COURSEPILOT_SPECS)
    p18_ids = {
        record_id for record_id in inventory.approved_records if record_id.startswith("p18-")
    }
    assert len(p18_ids) == 209
    assert "p18-cp-ds0-dev-freeze-r1" in p18_ids
    load_dataset_inventory(Path("datasets/courserag_eval/v1"), COURSERAG_SPECS)

    existing = P18FormalApproval.model_validate(
        _load(ROOT / "provenance/p18_formal_gold_approval.json")
    )
    with pytest.raises(ValueError, match="already locked Test"):
        approve_p18_formal(
            repository_root=Path("."),
            business_bundle_sha256=BUSINESS_SHA,
            quality_bundle_sha256=QUALITY_SHA,
            integration_bundle_sha256=INTEGRATION_SHA,
            reviewed_at=existing.reviewed_at,
        )

    with pytest.raises(ValueError, match="unexpected P18 formal Bundle identity"):
        approve_p18_formal(
            repository_root=Path("."),
            business_bundle_sha256="0" * 64,
            quality_bundle_sha256=QUALITY_SHA,
            integration_bundle_sha256=INTEGRATION_SHA,
            reviewed_at=datetime.now().astimezone(),
        )
