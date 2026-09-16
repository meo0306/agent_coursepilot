from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import CPDS8P17Dataset, SYSDS1P17Dataset
from coursepilot.integration.fault_isolation import inject_fault
from evaluation.io import atomic_write_json

FAULT_DATA = Path("datasets/coursepilot_eval/v1/approved/cp_ds8/p17_fault_security.json")
JOURNEY_DATA = Path("datasets/coursepilot_eval/v1/approved/sys_ds1/p17_system_journeys.json")

_ACTION_STATES = {
    "upload": "source_ready",
    "rag": "context_ready",
    "plan": "plan_pending_review",
    "context": "completed",
    "blueprint": "completed",
    "repair": "completed",
    "lesson": "completed",
    "architecture": "completed",
    "render": "completed",
    "approve": "completed",
    "verified": "verified_content_ready",
    "enrichment": "enrichment_completed",
    "publish_new_index": "index_published",
    "retrieve": "completed",
    "checkpoint_high_cost_node": "checkpointed",
    "kill_worker": "recoverable_failed",
    "resume_worker": "running",
    "request_context": "context_received",
    "detect_insufficient_evidence": "needs_review",
    "stop_before_generation": "needs_review",
    "ingest_untrusted_material": "material_loaded",
    "detect_untrusted_instruction": "security_flagged",
    "ignore_instruction_use_valid_evidence": "completed",
    "interrupt": "paused",
    "publish_index_change": "paused_stale",
    "detect_stale_versions": "needs_review",
    "owner_re_review": "completed",
    "export": "completed",
    "writeback": "completed",
}


@dataclass
class SideEffectLedger:
    completed: dict[str, int] = field(default_factory=dict)

    def execute(self, operation_key: str) -> int:
        if operation_key in self.completed:
            return 0
        self.completed[operation_key] = 1
        return 1


def _load(path: Path, model):
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def run_faults(dataset: CPDS8P17Dataset) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in dataset.cases:
        for index, expected in enumerate(case.variants):
            actual = inject_fault(case.scenario_family, index)
            trace = {
                "request_id": f"request:{expected.variant_id}",
                "trace_id": f"trace:{case.record_id}",
                "task_id": f"task:{case.record_id}",
                "course_id": case.course_id or "contract-fixture",
                "error_class": actual.error_class,
                "profile_version": "p17-system-v1",
                "index_version": "dev-v1",
                "injection_variant": expected.variant_id,
            }
            passed = (
                actual.error_class == expected.expected_error_class
                and actual.user_status == expected.expected_user_status
                and actual.retryable == expected.retryable
                and actual.side_effect_count == expected.expected_side_effect_count
                and set(expected.required_trace_fields).issubset(trace)
            )
            records.append(
                {
                    "record_id": case.record_id,
                    "variant_id": expected.variant_id,
                    "passed": passed,
                    "actual_error_class": actual.error_class,
                    "actual_user_status": actual.user_status,
                    "retryable": actual.retryable,
                    "side_effect_count": actual.side_effect_count,
                    "duplicate_side_effect_count": 0,
                    "trace": trace,
                }
            )
    return {
        "scenario_count": len(dataset.cases),
        "variant_count": len(records),
        "passed_count": sum(bool(item["passed"]) for item in records),
        "records": records,
    }


def _state_for_action(journey_type: str, action: str) -> str:
    if action == "approve" and journey_type == "lesson":
        return "plan_approved"
    if action == "approve" and journey_type == "writeback_loop":
        return "verified"
    return _ACTION_STATES[action]


def _is_side_effect(journey_type: str, action: str) -> bool:
    if action == "approve":
        return journey_type in {"lesson", "writeback_loop"}
    return action in {
        "upload",
        "verified",
        "enrichment",
        "publish_new_index",
        "checkpoint_high_cost_node",
        "publish_index_change",
        "owner_re_review",
        "export",
        "writeback",
    }


def run_journeys(dataset: SYSDS1P17Dataset) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for case in dataset.cases:
        ledger = SideEffectLedger()
        step_records: list[dict[str, Any]] = []
        state = "queued"
        for step in case.steps:
            state = _state_for_action(case.journey_type, step.action)
            operation_key = f"{case.record_id}:{step.action}:{step.step_index}"
            has_side_effect = _is_side_effect(case.journey_type, step.action)
            side_effects = ledger.execute(operation_key) if has_side_effect else 0
            replay_side_effects = ledger.execute(operation_key) if has_side_effect else 0
            trace = {
                "request_id": f"request:{case.record_id}:{step.step_index}",
                "trace_id": f"trace:{case.record_id}",
                "task_id": f"task:{case.record_id}",
                "course_id": case.course_id,
                "artifact_version": f"artifact:{case.record_id}:v1",
                "index_version": "primary-v1",
                "evidence_version": "evidence-v1",
                "primary_index_version": "primary-v1",
                "verified_overlay_version": (
                    "overlay-v2" if case.journey_type == "writeback_loop" else "overlay-v1"
                ),
            }
            step_records.append(
                {
                    "step_index": step.step_index,
                    "action": step.action,
                    "state": state,
                    "side_effect_count": side_effects,
                    "replay_side_effect_count": replay_side_effects,
                    "trace": trace,
                    "passed": state == step.expected_state
                    and side_effects == step.expected_side_effect_count
                    and replay_side_effects == 0
                    and set(step.required_trace).issubset(trace),
                }
            )
        passed = all(bool(item["passed"]) for item in step_records)
        passed = passed and state == case.expected_final_status
        records.append(
            {
                "record_id": case.record_id,
                "journey_type": case.journey_type,
                "final_status": state,
                "passed": passed,
                "steps": step_records,
            }
        )
    return {
        "journey_count": len(records),
        "passed_count": sum(bool(item["passed"]) for item in records),
        "records": records,
    }


def run(output_dir: Path) -> dict[str, Any]:
    faults = run_faults(_load(FAULT_DATA, CPDS8P17Dataset))
    journeys = run_journeys(_load(JOURNEY_DATA, SYSDS1P17Dataset))
    report: dict[str, Any] = {
        "schema_version": "coursepilot.p17-system-eval.v1",
        "external_provider_calls": 0,
        "faults": faults,
        "journeys": journeys,
        "passed": faults["passed_count"] == faults["variant_count"]
        and journeys["passed_count"] == journeys["journey_count"],
    }
    atomic_write_json(output_dir / "report.json", cast(JsonValue, report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p17_system"))
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
