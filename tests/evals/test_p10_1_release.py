from __future__ import annotations

import json
from pathlib import Path

from evaluation.p10_1_release import write_test_lock_lifecycle_report


def test_lifecycle_report_binds_consumed_lock_without_modifying_it(tmp_path: Path) -> None:
    lock_path = Path("datasets/courserag_eval/v1/test.lock.json")
    before = lock_path.read_bytes()
    output = write_test_lock_lifecycle_report(
        repository_root=Path.cwd(),
        output_path=tmp_path / "lifecycle.json",
        eval_passed=188,
        eval_skipped=1,
        failures_before_repair=23,
    )
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["status"] == "passed"
    assert report["formal_test_rerun"] is False
    assert lock_path.read_bytes() == before
