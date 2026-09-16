from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evaluation.contracts import DatasetSplit, ReviewStatus, TestLock
from evaluation.datasets import (
    COURSEPILOT_SPECS,
    COURSERAG_SPECS,
    DatasetInventory,
    DatasetSpec,
    canonical_json_bytes,
    load_dataset_inventory,
)
from evaluation.manifest import RunManifest, sha256_file


class TestLeakageGuardError(ValueError):
    """Raised when a formal Test run crosses a Gold or tuning boundary."""


class DatasetIntegrityError(ValueError):
    """Raised when Run Manifest dataset hashes do not match the selected files."""


def validate_dataset_ref_files(manifest: RunManifest, dataset_root: Path) -> None:
    root = dataset_root.resolve()
    dataset_manifest_path = root / "manifest.json"
    split_path = root / "splits" / f"{manifest.dataset.split.value}_ids.txt"
    if not dataset_manifest_path.is_file():
        raise DatasetIntegrityError(f"dataset Manifest is missing: {dataset_manifest_path}")
    if not split_path.is_file():
        raise DatasetIntegrityError(f"dataset split is missing: {split_path}")
    if sha256_file(dataset_manifest_path) != manifest.dataset.manifest_sha256:
        raise DatasetIntegrityError("dataset Manifest hash differs from Run Manifest")
    if sha256_file(split_path) != manifest.dataset.split_sha256:
        raise DatasetIntegrityError("dataset split hash differs from Run Manifest")

    try:
        dataset_metadata = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DatasetIntegrityError("dataset Manifest is not readable JSON") from exc
    if not isinstance(dataset_metadata, dict):
        raise DatasetIntegrityError("dataset Manifest must be a JSON object")
    if (
        dataset_metadata.get("dataset_id") != manifest.dataset.dataset_id
        or dataset_metadata.get("dataset_version") != manifest.dataset.dataset_version
    ):
        raise DatasetIntegrityError("dataset identity differs from Run Manifest")


def approved_inventory_sha256(inventory: DatasetInventory) -> str:
    payload = [
        inventory.approved_records[record_id].model_dump(mode="json")
        for record_id in sorted(inventory.approved_records)
    ]
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def split_ids_sha256(ids: set[str]) -> str:
    return hashlib.sha256(canonical_json_bytes(sorted(ids))).hexdigest()


def validate_test_lock(
    manifest: RunManifest,
    lock: TestLock,
    inventory: DatasetInventory,
    *,
    lock_file_sha256: str,
) -> None:
    if manifest.dataset.split is not DatasetSplit.TEST:
        return
    if not lock.locked:
        raise TestLeakageGuardError("the Test split is not locked")
    if (
        lock.dataset_id != manifest.dataset.dataset_id
        or lock.dataset_version != manifest.dataset.dataset_version
    ):
        raise TestLeakageGuardError("Test lock dataset identity differs from Run Manifest")
    if manifest.dataset.test_lock_sha256 != lock_file_sha256:
        raise TestLeakageGuardError("Test lock file hash differs from Run Manifest")

    test_ids = inventory.split_ids[DatasetSplit.TEST]
    if not test_ids:
        raise TestLeakageGuardError("a locked Test split cannot be empty")
    non_approved = {
        record_id
        for record_id in test_ids
        if record_id not in inventory.approved_records
        or inventory.approved_records[record_id].review_status is not ReviewStatus.APPROVED
    }
    if non_approved:
        raise TestLeakageGuardError(f"Test contains non-approved records: {sorted(non_approved)}")
    if lock.test_ids_sha256 != split_ids_sha256(test_ids):
        raise TestLeakageGuardError("locked Test ID hash differs from the current split")
    if lock.approved_manifest_sha256 != approved_inventory_sha256(inventory):
        raise TestLeakageGuardError("locked approved-record hash differs from the current dataset")


def validate_test_run_files(manifest: RunManifest, dataset_root: Path) -> None:
    specs: tuple[DatasetSpec, ...]
    if manifest.dataset.dataset_id == "courserag-eval":
        specs = COURSERAG_SPECS
    elif manifest.dataset.dataset_id == "coursepilot-eval":
        specs = COURSEPILOT_SPECS
    else:
        raise TestLeakageGuardError(
            f"unsupported formal Test dataset: {manifest.dataset.dataset_id}"
        )
    lock_path = dataset_root / "test.lock.json"
    if not lock_path.is_file():
        raise TestLeakageGuardError(f"Test lock file is missing: {lock_path}")
    lock = TestLock.model_validate_json(lock_path.read_text(encoding="utf-8"))
    inventory = load_dataset_inventory(dataset_root, specs)
    validate_test_lock(
        manifest,
        lock,
        inventory,
        lock_file_sha256=sha256_file(lock_path),
    )
