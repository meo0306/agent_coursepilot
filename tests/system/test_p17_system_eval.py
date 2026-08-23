import json
from pathlib import Path

from coursepilot.evals.formal_schemas import SYSDS1P17Dataset
from evaluation.p17_system_eval import run, run_journeys


def test_all_eight_journeys_preserve_trace_and_idempotent_side_effects(tmp_path: Path) -> None:
    path = Path("datasets/coursepilot_eval/v1/approved/sys_ds1/p17_system_journeys.json")
    dataset = SYSDS1P17Dataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
    result = run_journeys(dataset)
    assert result["journey_count"] == 8
    assert result["passed_count"] == 8
    for journey in result["records"]:
        trace_ids = {step["trace"]["trace_id"] for step in journey["steps"]}
        assert len(trace_ids) == 1
        assert all(step["replay_side_effect_count"] == 0 for step in journey["steps"])

    report = run(tmp_path)
    assert report["passed"] is True
    assert report["external_provider_calls"] == 0
    assert (tmp_path / "report.json").is_file()
