from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from evaluation.p18_loader import load_p18_test
from evaluation.p18_test_release import create_test_release, validate_test_execution_authorization

ROOT = Path(__file__).resolve().parents[2]


def test_p18_exact_freeze_creates_loadable_test_lock(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    shutil.copytree(ROOT / "datasets/coursepilot_eval", repository / "datasets/coursepilot_eval")
    shutil.copytree(
        ROOT / "storage_eval/p18/dev_freeze_candidate_r2",
        repository / "storage_eval/p18/dev_freeze_candidate_r2",
    )
    result = create_test_release(
        repository_root=repository,
        output_dir=repository / "storage_eval/p18/formal_test",
    )
    lock_path = repository / "datasets/coursepilot_eval/v1/test.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    assert result["status"] == "locked_ready_to_execute"
    assert lock["locked"] is True
    assert (
        len(
            (repository / "datasets/coursepilot_eval/v1/splits/test_ids.txt")
            .read_text()
            .splitlines()
        )
        == 92
    )
    assert result["test_lock_sha256"] == hashlib.sha256(lock_path.read_bytes()).hexdigest()
    loaded = load_p18_test(repository / "datasets/coursepilot_eval/v1")
    assert loaded.record_count == 92
    assert len(loaded.components["cp_ds1"]) == 4
    assert len(loaded.components["cp_ds2"]) == 4
    assert len(loaded.components["cp_ds3"]) == 4
    assert len(loaded.components["cp_ds4"]) == 30
    assert len(loaded.components["cp_ds5"]) == 18
    assert len(loaded.components["cp_ds6"]) == 12
    assert len(loaded.components["cp_ds7"]) == 2
    assert len(loaded.components["cp_ds8"]) == 10
    assert len(loaded.components["sys_ds1"]) == 8
    authorized = validate_test_execution_authorization(repository_root=repository)
    assert authorized["limits"]["deepseek_requests"] == 260
