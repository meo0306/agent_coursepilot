from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coursepilot.evals.formal_schemas import SYSDS1P17Dataset

ROOT = Path("datasets/coursepilot_eval/v1")


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_p17_r3_changes_only_two_journeys() -> None:
    r2 = _load(ROOT / "candidates/sys_ds1/p17_system_journeys_r2.json")
    r3 = _load(ROOT / "candidates/sys_ds1/p17_system_journeys_r3.json")
    SYSDS1P17Dataset.model_validate(r3)
    old = {item["record_id"]: item for item in r2["cases"]}
    new = {item["record_id"]: item for item in r3["cases"]}
    changed = {key for key in old if _digest(old[key]) != _digest(new[key])}
    assert changed == {"p17-sys-ds1-06", "p17-sys-ds1-08"}


def test_p17_r3_repairs_artifact_identity_and_final_status() -> None:
    dataset = SYSDS1P17Dataset.model_validate_json(
        (ROOT / "candidates/sys_ds1/p17_system_journeys_r3.json").read_text(encoding="utf-8")
    )
    by_id = {case.record_id: case for case in dataset.cases}
    six = by_id["p17-sys-ds1-06"]
    assert any("P14 Lesson Artifact identity" in item for item in six.trace_version_assertions)
    assert all("P16/P15" not in item for item in six.trace_version_assertions)
    assert six.fixture_details["artifact_owner"] == "P14"
    assert six.fixture_details["lesson_artifact_file_sha256"] == (
        "4533545ca0355e6c9a1581dd7024fc008b7e7f95e71e9c73b35dc52f88340e13"
    )
    eight = by_id["p17-sys-ds1-08"]
    assert eight.steps[-1].expected_state == "completed"
    assert eight.expected_final_status == "completed"


def test_p17_r3_review_contains_only_delta_and_reuses_r2_faults() -> None:
    manifest = _load(ROOT / "provenance/p17_integration_bundle_manifest_r3.json")
    review = _load(
        Path("storage_eval/p17_integration_review")
        / manifest["bundle_sha256"]
        / "p17_integration_r3_review_template.json"
    )
    assert {item["record_id"] for item in review["records"]} == {
        "p17-sys-ds1-06",
        "p17-sys-ds1-08",
    }
    assert manifest["fault_candidate_relative_path"].endswith("p17_fault_security_r2.json")
    assert manifest["repaired_record_ids"] == ["p17-sys-ds1-06", "p17-sys-ds1-08"]
    assert len(manifest["carried_forward_approved_ids"]) == 36
