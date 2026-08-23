import json
from pathlib import Path

from evaluation.p13_validation_repair_eval import run_pilot


def test_approved_cp_ds4_and_cp_ds5_contracts(tmp_path: Path) -> None:
    result = run_pilot(Path(__file__).parents[3], tmp_path / "report.json")
    assert result["summary"]["detection_recall"] == 1.0
    assert result["summary"]["scope_precision"] == 1.0
    assert result["repair_summary"]["cases"] == 15
    assert result["repair_summary"]["path_violations"] == 0
    assert (
        json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))["test_loaded"] is False
    )
