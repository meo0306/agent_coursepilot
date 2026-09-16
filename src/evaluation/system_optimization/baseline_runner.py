"""Offline EP-00 baseline and coverage runner.

This first-stage runner performs data, structure and historical-reference
checks only.  It never invokes CoursePilot generators, CourseRAG services or an
external Provider, and it never converts candidate labels into quality Gold.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from evaluation.system_optimization.dev_loader import (
    DEFAULT_ROOT,
    SystemOptimizationApprovalPending,
    load_approved,
    load_candidate,
)
from evaluation.system_optimization.schemas import ArtifactType, MaterialType


def run_baseline(
    root: Path = DEFAULT_ROOT,
    *,
    artifact: Literal["all", "lesson", "exam", "ppt"] = "all",
    prefer_approved: bool = True,
) -> dict[str, Any]:
    approval_message: str | None = None
    if prefer_approved:
        try:
            loaded = load_approved(root)
        except SystemOptimizationApprovalPending as exc:
            loaded = load_candidate(root)
            approval_message = str(exc)
    else:
        loaded = load_candidate(root)
    records = [
        item
        for item in loaded.cases.records
        if artifact == "all" or item.artifact_type.value == artifact
    ]
    historical_path = root / "candidates" / "historical_baseline.json"
    historical = json.loads(historical_path.read_text(encoding="utf-8"))
    if loaded.metric_eligible:
        historical["new_dev_baseline"]["status"] = "pending_provider_authorization"
    by_artifact: dict[str, Any] = {}
    for artifact_type in ArtifactType:
        selected = [item for item in records if item.artifact_type is artifact_type]
        if not selected:
            continue
        capacities = Counter(item.evidence_package.capacity_tier.value for item in selected)
        materials = Counter(
            material.value
            for item in selected
            for material in item.task_demand.required_material_types
        )
        adequacy = Counter(item.candidate_adequacy.status.value for item in selected)
        by_artifact[artifact_type.value] = {
            "cases": len(selected),
            "capacity_tiers": dict(sorted(capacities.items())),
            "material_types": {
                material.value: materials[material.value] for material in MaterialType
            },
            "candidate_adequacy": dict(sorted(adequacy.items())),
            "output_counts": sorted({item.task_demand.output_count for item in selected}),
        }
    return {
        "schema_version": "system-optimization.offline-baseline-report.v1",
        "split": "dev",
        "artifact_filter": artifact,
        "dataset_status": loaded.status if loaded.metric_eligible else "pending_human_approval",
        "approval_message": approval_message,
        "quality_metrics_eligible": loaded.metric_eligible,
        "candidate_labels_are_gold": False,
        "human_approved_adequacy_eligible": loaded.metric_eligible,
        "task_cases_checked": len(records),
        "failure_replays_checked": len(loaded.failures.records),
        "coverage": by_artifact,
        "historical_reference": historical,
        "external_provider_calls": 0,
        "p18_test_or_blind_loaded": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--artifact", choices=("all", "lesson", "exam", "ppt"), default="all")
    parser.add_argument("--split", choices=("dev",), default="dev")
    parser.add_argument("--candidate-only", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run_baseline(
        args.root,
        artifact=args.artifact,
        prefer_approved=not args.candidate_only,
    )
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
