"""Promote the owner-approved P18 Dev freeze and create the one-way Test lock."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coursepilot.evals.formal_schemas import CPDS0ManifestDataset
from evaluation.contracts import (
    ApprovalRecord,
    DatasetSplit,
    ReviewLogEntry,
    ReviewStatus,
    TestLock,
)
from evaluation.datasets import (
    COURSEPILOT_SPECS,
    load_dataset_inventory,
    record_digest,
)
from evaluation.guard import approved_inventory_sha256, split_ids_sha256

CP_DS0_SHA256 = "8814701173860a76a9db559e3cfb6cc094c2580446bfc12be33ebf02a675ba01"
FROZEN_MANIFEST_SHA256 = "fb2c13716cc329110b58d87358667323c2ab825cd3b609f6ef2cf6aa6afb23d6"
PREFLIGHT_PROTOCOL_SHA256 = "2a9e3cd3b5e8135d40d27d53b83aab468f8cf22edb509657f1a6bea94309ccd1"
EMPTY_SPLIT_SHA256 = "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"


def create_test_release(*, repository_root: Path, output_dir: Path) -> dict[str, Any]:
    dataset_root = repository_root / "datasets/coursepilot_eval/v1"
    candidate_path = dataset_root / "candidates/cp_ds0/p18_manifest_candidate_r1.json"
    approved_path = dataset_root / "approved/cp_ds0/p18_formal.json"
    frozen_path = (
        repository_root
        / "storage_eval/p18/dev_freeze_candidate_r2/p18_frozen_manifest_candidate.json"
    )
    preflight_path = (
        repository_root
        / "storage_eval/p18/dev_freeze_candidate_r2/p18_test_preflight_protocol.json"
    )
    owner_approval_path = (
        repository_root / "storage_eval/p18/dev_freeze_candidate_r2/owner_freeze_approval.json"
    )
    _require_sha(candidate_path, CP_DS0_SHA256)
    _require_sha(frozen_path, FROZEN_MANIFEST_SHA256)
    _require_sha(preflight_path, PREFLIGHT_PROTOCOL_SHA256)
    owner = _json(owner_approval_path)
    if (
        owner.get("status") != "owner_approved"
        or owner.get("cp_ds0_candidate_sha256") != CP_DS0_SHA256
        or owner.get("frozen_manifest_candidate_sha256") != FROZEN_MANIFEST_SHA256
    ):
        raise ValueError("P18 owner freeze approval does not bind the exact candidates")

    candidate = CPDS0ManifestDataset.model_validate(_json(candidate_path))
    if len(candidate.records) != 1:
        raise ValueError("P18 CP-DS0 candidate must contain exactly one record")
    candidate_record = candidate.records[0]
    if approved_path.exists():
        approved = CPDS0ManifestDataset.model_validate(_json(approved_path))
        if len(approved.records) != 1 or approved.records[0].approval is None:
            raise ValueError("existing P18 CP-DS0 approval is invalid")
        approval = approved.records[0].approval
        if approval.candidate_sha256 != record_digest(candidate_record):
            raise ValueError("existing P18 CP-DS0 approval binds another candidate")
        reviewed_at = approval.reviewed_at
    else:
        reviewed_at = datetime.now(UTC)
        approved_without_approval = candidate_record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approval = ApprovalRecord(
            review_id="p18-freeze.cp_ds0.p18-cp-ds0-dev-freeze-r1",
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
            candidate_sha256=record_digest(candidate_record),
            approved_record_sha256=record_digest(approved_without_approval),
            notes=(
                "Exact CP-DS0 and Frozen Manifest owner approval; formal Test authorization "
                f"binds preflight {PREFLIGHT_PROTOCOL_SHA256}."
            ),
        )
        approved_record = approved_without_approval.model_copy(update={"approval": approval})
        approved = candidate.model_copy(
            update={"dataset_version": "p18-formal-freeze-r1", "records": [approved_record]}
        )
        _write_json(approved_path, approved.model_dump(mode="json"))
        _append_review(
            dataset_root / "reviews/review_log.jsonl",
            ReviewLogEntry(
                review_id=approval.review_id,
                record_id=approved_record.record_id,
                action="approve",
                reviewer_id="course_owner",
                reviewed_at=reviewed_at,
                candidate_sha256=approval.candidate_sha256,
                resulting_record_sha256=approval.approved_record_sha256,
                notes=approval.notes,
            ),
        )

    _sync_approved_p18_splits(dataset_root)
    inventory = load_dataset_inventory(dataset_root, COURSEPILOT_SPECS)
    test_ids = inventory.split_ids[DatasetSplit.TEST]
    lock = TestLock(
        dataset_id="coursepilot-eval",
        dataset_version="v1",
        locked=True,
        test_ids_sha256=split_ids_sha256(test_ids),
        approved_manifest_sha256=approved_inventory_sha256(inventory),
        locked_at=reviewed_at,
        locked_by="course_owner",
    )
    lock_path = dataset_root / "test.lock.json"
    existing = TestLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
    if existing.locked:
        if (
            existing.test_ids_sha256 != lock.test_ids_sha256
            or existing.approved_manifest_sha256 != lock.approved_manifest_sha256
        ):
            if existing.test_ids_sha256 != EMPTY_SPLIT_SHA256:
                raise ValueError("existing P18 Test lock has a different identity")
            _write_json(lock_path, lock.model_dump(mode="json"))
        else:
            lock = existing
    else:
        _write_json(lock_path, lock.model_dump(mode="json"))

    manifest_path = dataset_root / "manifest.json"
    manifest = _json(manifest_path)
    manifest["p18_test_lock_status"] = "locked_owner_authorized"
    _write_json(manifest_path, manifest)
    release = {
        "schema_version": "coursepilot.p18-test-release.v1",
        "status": "locked_ready_to_execute",
        "frozen_manifest_sha256": FROZEN_MANIFEST_SHA256,
        "cp_ds0_candidate_sha256": CP_DS0_SHA256,
        "test_preflight_protocol_sha256": PREFLIGHT_PROTOCOL_SHA256,
        "test_lock_sha256": _sha(lock_path),
        "test_ids_sha256": lock.test_ids_sha256,
        "approved_inventory_sha256": lock.approved_manifest_sha256,
        "external_calls_executed": 0,
        "limits": {
            "deepseek_cost_cny": "4.00",
            "deepseek_requests": 260,
            "deepseek_input_tokens": 1_200_000,
            "deepseek_output_and_thinking_tokens": 1_200_000,
            "cohere_search_units": 40,
        },
    }
    _write_json(output_dir / "test_release.json", release)
    return release


def validate_test_execution_authorization(*, repository_root: Path) -> dict[str, Any]:
    release_path = repository_root / "storage_eval/p18/formal_test/test_release.json"
    release = _json(release_path)
    if (
        release.get("status") != "locked_ready_to_execute"
        or release.get("frozen_manifest_sha256") != FROZEN_MANIFEST_SHA256
        or release.get("cp_ds0_candidate_sha256") != CP_DS0_SHA256
        or release.get("test_preflight_protocol_sha256") != PREFLIGHT_PROTOCOL_SHA256
    ):
        raise ValueError("P18 Test release is not authorized for the frozen identities")
    lock_path = repository_root / "datasets/coursepilot_eval/v1/test.lock.json"
    if release.get("test_lock_sha256") != _sha(lock_path):
        raise ValueError("P18 Test lock differs from the authorized release")
    return release


def _sync_approved_p18_splits(dataset_root: Path) -> None:
    """Materialise the already-approved component split commitment for the global lock."""

    payload = _json(dataset_root / "provenance/p18_component_splits.json")
    components = payload.get("components")
    if not isinstance(components, dict):
        raise ValueError("P18 component split commitment is invalid")
    dev_ids: set[str] = set()
    test_ids: set[str] = set()
    for split in components.values():
        if not isinstance(split, dict):
            raise ValueError("P18 component split entry is invalid")
        dev_ids.update(str(item) for item in split.get("dev", ()))
        dev_ids.update(str(item) for item in split.get("dev_contract", ()))
        test_ids.update(str(item) for item in split.get("test", ()))
        test_ids.update(str(item) for item in split.get("blind", ()))
        test_ids.update(str(item) for item in split.get("heldout_custom", ()))
    if len(test_ids) != 92:
        raise ValueError(f"P18 approved Test identity count must be 92, got {len(test_ids)}")
    split_dir = dataset_root / "splits"
    split_dir.mkdir(parents=True, exist_ok=True)
    (split_dir / "dev_ids.txt").write_text("\n".join(sorted(dev_ids)) + "\n", encoding="utf-8")
    (split_dir / "test_ids.txt").write_text("\n".join(sorted(test_ids)) + "\n", encoding="utf-8")


def _append_review(path: Path, entry: ReviewLogEntry) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    for line in lines:
        if line and json.loads(line).get("review_id") == entry.review_id:
            return
    lines.append(
        json.dumps(entry.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _require_sha(path: Path, expected: str) -> None:
    actual = _sha(path)
    if actual != expected:
        raise ValueError(f"P18 identity mismatch for {path}: {actual}")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p18/formal_test"))
    args = parser.parse_args()
    result = create_test_release(
        repository_root=args.repository_root.resolve(), output_dir=args.output_dir.resolve()
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
