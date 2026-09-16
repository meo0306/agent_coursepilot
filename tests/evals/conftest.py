from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from evaluation.contracts import TestLock

ROOT = Path(__file__).resolve().parents[2]
SOURCE_DATASET = ROOT / "datasets/courserag_eval/v1"


@pytest.fixture
def prelock_dataset_root(tmp_path: Path) -> Path:
    target = tmp_path / "prelock/v1"
    shutil.copytree(SOURCE_DATASET, target)
    (target / "test.lock.json").write_text(
        json.dumps(
            {
                "schema_version": "course-eval.test-lock.v1",
                "dataset_id": "courserag-eval",
                "dataset_version": "v1",
                "locked": False,
                "test_ids_sha256": None,
                "approved_manifest_sha256": None,
                "locked_at": None,
                "locked_by": None,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return target


@pytest.fixture
def locked_dataset_root(tmp_path: Path) -> Path:
    target = tmp_path / "locked/v1"
    shutil.copytree(SOURCE_DATASET, target)
    lock = TestLock.model_validate_json((target / "test.lock.json").read_text(encoding="utf-8"))
    assert lock.locked
    return target


@pytest.fixture
def consumed_formal_release() -> dict[str, str]:
    paths = {
        "lock": ROOT / "datasets/courserag_eval/v1/test.lock.json",
        "component": ROOT / "storage_eval/p10/formal/component_test_report.json",
        "retrieval": ROOT / "storage_eval/p10/formal/retrieval-run-1/report.json",
        "qa": ROOT / "storage_eval/p10/formal/qa-run-1/report.json",
    }
    return {name: _sha256(path) for name, path in paths.items()}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
