"""P18 final report cross-check and public-claim extraction."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_final_report(
    *, automatic: dict[str, Any], human: dict[str, Any] | None, locked_test: bool
) -> dict[str, Any]:
    l0 = automatic.get("l0", {})
    l0_pass = all(value == 0 for value in l0.values())
    human_complete = human is not None and human.get("review_units", 0) > 0
    status = "gate_failed" if not l0_pass else "gate_pending_owner_review"
    if l0_pass and human_complete and human is not None:
        quality_pass = (
            human["acceptable_rate"] >= 0.8
            and human["mean_rubric"] >= 4
            and human["mean_edit_burden"] <= 1.5
        )
        status = (
            "completed"
            if l0_pass and quality_pass
            else ("completed_with_quality_debt" if l0_pass else "gate_failed")
        )
    public = []
    if status in {"completed", "completed_with_quality_debt"} and locked_test and human is not None:
        public = [
            {
                "metric": "human_acceptable_rate",
                "value": human["acceptable_rate"],
                "sample_scope": human["review_units"],
            },
            {
                "metric": "mean_edit_burden",
                "value": human["mean_edit_burden"],
                "sample_scope": human["review_units"],
            },
        ]
    return {
        "status": status,
        "locked_test": locked_test,
        "l0_pass": l0_pass,
        "automatic": automatic,
        "human": human,
        "public_metric_candidates": public,
        "limitations": [
            "Main and Light resolve to one physical model; no dual-model savings claim.",
            "P17 prompt-injection automation is not a frozen capability.",
        ],
    }


def build_automatic_summary(*, root: Path) -> dict[str, Any]:
    rows = _json(root / "track_a/rows.json")
    track_a = _json(root / "track_a/report.json")
    components = _json(root / "components/report.json")
    exports = _json(root / "exports_docker/report.json")
    stability = _json(root / "stability/report.json")
    track_b = _json(root / "track_b/report.json")
    l0 = dict(track_a["metrics"]["l0"])
    l0.update(
        {
            "generation_failures": sum(item["status"] != "succeeded" for item in rows),
            "contract_failures": sum(not bool(item["contract_pass"]) for item in rows),
            "citation_failures": sum(not bool(item["citations_resolvable"]) for item in rows),
            "trace_failures": sum(not bool(item["trace_complete"]) for item in rows),
            "render_failures": int(exports["failed"]),
            "fault_variant_failures": int(track_b["faults"]["variant_count"])
            - int(track_b["faults"]["passed_count"]),
            "track_b_blocked_journeys": int(track_b["journeys"]["blocked_count"]),
        }
    )
    failed_cases = [
        {
            "record_id": item["record_id"],
            "track": item["track"],
            "component": item["component"],
            "status": item["status"],
            "contract_pass": item["contract_pass"],
            "error_class": item.get("error_class"),
        }
        for item in rows
        if item["status"] != "succeeded" or not item["contract_pass"]
    ]
    return {
        "schema_version": "coursepilot.p18-automatic-summary.v1",
        "l0": l0,
        "track_a": track_a,
        "components": components,
        "exports": exports,
        "stability": stability,
        "track_b": track_b,
        "failed_cases": failed_cases,
        "provider_budget": stability["ledger"],
        "cohere_search_units": 0,
    }


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("storage_eval/p18/formal_test"))
    parser.add_argument("--output", type=Path, default=Path("reports/p18/formal_test_report.json"))
    parser.add_argument("--human-decisions", type=Path)
    args = parser.parse_args()
    automatic = build_automatic_summary(root=args.root)
    human = None
    if args.human_decisions is not None:
        from evaluation.p18_human_review import finalize_reviews

        human = finalize_reviews(args.human_decisions)
    report = build_final_report(automatic=automatic, human=human, locked_test=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
