"""Run the six frozen P18 Test stability repeats under the cumulative budget."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, cast

from coursepilot.evals.p18_metrics import aggregate_run_rows
from evaluation.p18_case_adapters import P18TrackAExecutor
from evaluation.p18_loader import load_p18_test
from evaluation.p18_runner import P18_FORMAL_TEST_BUDGET, P18Ledger, _atomic_json
from evaluation.p18_schemas import P18TaskBase
from evaluation.p18_test_release import validate_test_execution_authorization


def run_stability(
    *, repository_root: Path, source_run_dir: Path, output_dir: Path, resume: bool = False
) -> dict[str, Any]:
    """Repeat the lexicographically first Test task per component twice.

    The selection rule is data-only and fixed before observing model quality;
    the original Track-A result plus these two repeats gives three observations
    for Lesson, Exam, and PPT.  A copy of the Track-A ledger enforces the same
    cumulative Test budget rather than opening a second allowance.
    """

    validate_test_execution_authorization(repository_root=repository_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = output_dir / "ledger.json"
    if not ledger_path.exists():
        shutil.copy2(source_run_dir / "ledger.json", ledger_path)
    ledger = P18Ledger(ledger_path, P18_FORMAL_TEST_BUDGET, resume=True)
    rows_path = output_dir / "rows.json"
    rows: list[dict[str, Any]] = (
        json.loads(rows_path.read_text(encoding="utf-8")) if resume and rows_path.exists() else []
    )
    done = {(row["component"], row["repeat"]) for row in rows}
    loaded = load_p18_test(repository_root / "datasets/coursepilot_eval/v1")
    executor = P18TrackAExecutor(repository_root=repository_root, use_provider=True)
    selected: dict[str, str] = {}
    for component in ("cp_ds1", "cp_ds2", "cp_ds3"):
        original = cast(
            P18TaskBase,
            min(loaded.components[component], key=lambda item: getattr(item, "record_id")),
        )
        selected[component] = original.record_id
        for repeat in (2, 3):
            if (component, repeat) in done:
                continue
            # The suffix changes only the invocation identity/thread so the
            # provider response cache cannot turn an independent repeat into a
            # replay.  Task content, Evidence, Profile, and model stay frozen.
            case = original.model_copy(
                update={"record_id": f"{original.record_id}--stability-{repeat}"}
            )
            row = executor(case, "cp_b10", ledger)
            row.update(
                component=component,
                record_id=original.record_id,
                invocation_record_id=case.record_id,
                track="cp_b10",
                repeat=repeat,
            )
            rows.append(row)
            _atomic_json(rows_path, rows)
    report = {
        "schema_version": "coursepilot.p18-test-stability.v1",
        "selection_rule": "lexicographically_first_test_record_per_component",
        "selected_records": selected,
        "additional_runs": len(rows),
        "ledger": ledger.totals(),
        "metrics": aggregate_run_rows(rows),
        "fallback_allowed": False,
    }
    _atomic_json(output_dir / "report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    report = run_stability(
        repository_root=args.repository_root.resolve(),
        source_run_dir=args.source_run_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        resume=args.resume,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
