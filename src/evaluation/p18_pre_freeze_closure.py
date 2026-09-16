"""Narrow P18 Dev closure for six Exam V2 cases and one exact PPT resume."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from coursepilot.evals.p18_metrics import aggregate_run_rows
from evaluation.p18_case_adapters import P18TrackAExecutor
from evaluation.p18_loader import load_p18_dev
from evaluation.p18_runner import (
    P18Budget,
    P18BudgetExceeded,
    P18Ledger,
    P18ProviderPeakPause,
    require_provider_off_peak,
)
from evaluation.p18_schemas import P18TaskBase

PPT_CASE_ID = "p18-ppt-06"
PPT_THREAD_ID = f"p18:{PPT_CASE_ID}:cp_b10"


def closure_budget() -> P18Budget:
    return P18Budget(
        max_cost_cny=Decimal("2.00"),
        max_input_tokens=900_000,
        max_output_tokens=600_000,
        max_requests=100,
        cache_miss_input_cny_per_million=Decimal("0.5"),
        output_cny_per_million=Decimal("1.0"),
    )


def verify_ppt_retry_source(source_ledger_path: Path) -> str:
    source = json.loads(source_ledger_path.read_text(encoding="utf-8"))
    failures: list[tuple[str, dict[str, Any]]] = []
    for identity, item in source.get("requests", {}).items():
        invocation = item.get("invocation") or {}
        if invocation.get("thread_id") != PPT_THREAD_ID:
            continue
        if item.get("response") is None:
            failures.append((identity, item))
    if len(failures) != 1:
        raise RuntimeError("P18 PPT retry requires exactly one unresolved prior request")
    identity, item = failures[0]
    invocation = item.get("invocation") or {}
    if (
        invocation.get("prompt_name") != "ppt/p16_generate_slide"
        or invocation.get("error_category") != "llm_provider_error"
        or (invocation.get("usage") or {}).get("output_tokens", 0) not in {0, None}
    ):
        raise RuntimeError("P18 PPT unresolved request is not the approved connection failure")
    return identity


def run_closure(
    *,
    repository_root: Path,
    source_dir: Path,
    output_dir: Path,
    use_provider: bool,
    resume: bool,
) -> dict[str, Any]:
    loaded = load_p18_dev(repository_root / "datasets/coursepilot_eval/v1")
    source_rows = json.loads((source_dir / "rows.json").read_text(encoding="utf-8"))
    source_report = json.loads((source_dir / "report.json").read_text(encoding="utf-8"))
    if any(row.get("track") == "test" for row in source_rows):
        raise RuntimeError("P18 closure source must not contain Test rows")

    output_dir.mkdir(parents=True, exist_ok=True)
    ledger = P18Ledger(
        output_dir / "ledger.json",
        closure_budget(),
        resume=resume,
        provider_window_guard=require_provider_off_peak if use_provider else None,
    )
    unresolved_ppt_request = verify_ppt_retry_source(source_dir / "ledger.json")
    if use_provider:
        ledger.seed_successful_responses(source_dir / "ledger.json", thread_id=PPT_THREAD_ID)
    carried_ppt_responses = sum(
        bool(item.get("carried_from_prior_run")) for item in ledger.data["requests"].values()
    )

    revision_path = output_dir / "revision_rows.json"
    revision_rows: list[dict[str, Any]] = (
        json.loads(revision_path.read_text(encoding="utf-8"))
        if resume and revision_path.exists()
        else []
    )
    revision_by_key = {
        (row["component"], row["record_id"], row["track"]): row for row in revision_rows
    }
    done = {
        key
        for key, row in revision_by_key.items()
        if row.get("status") == "succeeded" and row.get("contract_pass") is True
    }
    selected: list[tuple[str, P18TaskBase]] = [
        ("cp_ds2", cast(P18TaskBase, case)) for case in loaded.components["cp_ds2"]
    ]
    selected.extend(
        ("cp_ds3", cast(P18TaskBase, case))
        for case in loaded.components["cp_ds3"]
        if cast(P18TaskBase, case).record_id == PPT_CASE_ID
    )
    executor = P18TrackAExecutor(repository_root=repository_root, use_provider=use_provider)
    status = "completed"
    for component, case in selected:
        key = (component, case.record_id, "cp_b10")
        if key in done:
            continue
        try:
            row = executor(
                case,
                "cp_b10",
                ledger,
                prior_row=revision_by_key.get(key),
            )
        except P18ProviderPeakPause:
            status = "scheduled_off_peak_pause"
            break
        except P18BudgetExceeded:
            status = "budget_paused"
            break
        row.update(component=component, record_id=case.record_id, track="cp_b10")
        revision_by_key[key] = row
        revision_rows = list(revision_by_key.values())
        _atomic_json(revision_path, revision_rows)

    replacement_keys = {(row["component"], row["record_id"], row["track"]) for row in revision_rows}
    merged_rows = [
        row
        for row in source_rows
        if (row["component"], row["record_id"], row["track"]) not in replacement_keys
    ]
    merged_rows.extend(revision_rows)
    merged_rows.sort(key=lambda row: (row["component"], row["record_id"], row["track"]))
    _atomic_json(output_dir / "merged_rows.json", merged_rows)

    expected_keys = {
        ("cp_ds2", cast(P18TaskBase, case).record_id, "cp_b10")
        for case in loaded.components["cp_ds2"]
    }
    expected_keys.add(("cp_ds3", PPT_CASE_ID, "cp_b10"))
    completed_keys = replacement_keys & expected_keys
    if status == "completed" and completed_keys != expected_keys:
        status = "incomplete"
    closure_usage = ledger.totals()
    source_usage = source_report["ledger"]
    cumulative_usage = {
        "requests": int(source_usage["requests"]) + int(closure_usage["requests"]),
        "input_tokens": int(source_usage["input_tokens"]) + int(closure_usage["input_tokens"]),
        "output_tokens": int(source_usage["output_tokens"]) + int(closure_usage["output_tokens"]),
        "cost_cny": str(
            Decimal(str(source_usage["cost_cny"])) + Decimal(str(closure_usage["cost_cny"]))
        ),
    }
    report = {
        "schema_version": "coursepilot.p18-pre-freeze-closure.v1",
        "status": status,
        "test_access": False,
        "source_dir": str(source_dir.resolve()),
        "source_rows": len(source_rows),
        "revision_rows": len(revision_rows),
        "expected_revision_rows": len(expected_keys),
        "carried_ppt_responses": carried_ppt_responses,
        "approved_ppt_retry_request_sha256": unresolved_ppt_request,
        "source_provider_usage": source_usage,
        "ledger": closure_usage,
        "cumulative_provider_usage": cumulative_usage,
        "budget": {key: str(value) for key, value in asdict(closure_budget()).items()},
        "metrics": aggregate_run_rows(merged_rows),
        "rows_path": str((output_dir / "merged_rows.json").resolve()),
    }
    _atomic_json(output_dir / "report.json", report)
    return report


def _atomic_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the narrow P18 pre-freeze closure")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--source-dir", type=Path, default=Path("storage_eval/p18/dev_real_r2"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    execution = parser.add_mutually_exclusive_group(required=True)
    execution.add_argument("--offline-smoke", action="store_true")
    execution.add_argument("--real-provider", action="store_true")
    args = parser.parse_args()
    report = run_closure(
        repository_root=args.repository_root.resolve(),
        source_dir=args.source_dir.resolve(),
        output_dir=args.output_dir.resolve(),
        use_provider=args.real_provider,
        resume=args.resume,
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
