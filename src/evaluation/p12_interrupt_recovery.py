"""Offline structural runner for the approved CP-DS6 P12 input package."""

from __future__ import annotations

import json
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS6P12PilotDataset

ROOT = Path(__file__).resolve().parents[2]
APPROVED = ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds6/p12_interrupt_recovery.json"


def run(input_path: Path = APPROVED) -> dict[str, object]:
    dataset = CPDS6P12PilotDataset.model_validate_json(input_path.read_text(encoding="utf-8"))
    by_interrupt: dict[str, int] = {}
    for case in dataset.cases:
        by_interrupt[case.interrupt_type] = by_interrupt.get(case.interrupt_type, 0) + 1
    return {
        "dataset_version": dataset.dataset_version,
        "case_count": len(dataset.cases),
        "interrupt_counts": by_interrupt,
        "external_calls": 0,
        "gold_promotion": False,
        "status": "input_validated",
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
