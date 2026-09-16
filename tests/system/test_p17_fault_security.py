import json
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS8P17Dataset
from evaluation.p17_system_eval import run_faults


def test_all_approved_fault_variants_are_isolated_without_side_effects() -> None:
    path = Path("datasets/coursepilot_eval/v1/approved/cp_ds8/p17_fault_security.json")
    dataset = CPDS8P17Dataset.model_validate(json.loads(path.read_text(encoding="utf-8")))
    result = run_faults(dataset)
    assert result["scenario_count"] == 30
    assert result["variant_count"] == 34
    assert result["passed_count"] == 34
    assert all(item["duplicate_side_effect_count"] == 0 for item in result["records"])
