import json
import shutil
from pathlib import Path

import pytest

from evaluation.system_optimization.dev_loader import (
    SystemOptimizationApprovalPending,
    SystemOptimizationBoundaryError,
    load_approved,
    load_candidate,
)

ROOT = Path("datasets/system_optimization/v1")


def test_loader_rejects_p18_path_before_attempting_to_read(tmp_path: Path) -> None:
    with pytest.raises(SystemOptimizationBoundaryError, match="forbidden"):
        load_candidate(tmp_path / "p18")


def test_approved_loader_never_falls_back_to_candidates(tmp_path: Path) -> None:
    candidate_dir = tmp_path / "candidates"
    candidate_dir.mkdir()
    shutil.copy(ROOT / "candidates/dev_cases.json", candidate_dir)
    shutil.copy(ROOT / "candidates/failure_replays.json", candidate_dir)
    with pytest.raises(SystemOptimizationApprovalPending, match="human approval"):
        load_approved(tmp_path)


def test_repository_approved_loader_validates_review_bindings() -> None:
    loaded = load_approved(ROOT)
    assert loaded.metric_eligible is True
    assert all(item.approval is not None for item in loaded.cases.records)
    assert all(item.approval is not None for item in loaded.failures.records)


def test_loader_rejects_p18_source_identifier(tmp_path: Path) -> None:
    candidate_dir = tmp_path / "candidates"
    candidate_dir.mkdir()
    shutil.copy(ROOT / "candidates/failure_replays.json", candidate_dir)
    payload = json.loads((ROOT / "candidates/dev_cases.json").read_text(encoding="utf-8"))
    payload["records"][0]["evidence_package"]["items"][0]["source_record_id"] = "p18-copy"
    (candidate_dir / "dev_cases.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )

    with pytest.raises(SystemOptimizationBoundaryError, match="P18-derived"):
        load_candidate(tmp_path)


def test_candidate_loader_reports_non_metric_eligible() -> None:
    loaded = load_candidate(ROOT)
    assert loaded.status == "candidate"
    assert loaded.metric_eligible is False
    assert all(item.p18_case_reused is False for item in loaded.cases.records)
