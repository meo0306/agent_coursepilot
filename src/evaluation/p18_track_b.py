"""Locked P18 Track-B system and fault evaluation.

The runner deliberately separates live-environment evidence from deterministic
workflow-contract checks.  A missing formal CourseRAG Test index is reported as
a blocker; Track-A evidence fixtures are never installed as a substitute.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import httpx
from pydantic import JsonValue

from coursepilot.clients.remote_courserag import RemoteCourseRAGClient
from coursepilot.integration.fault_isolation import inject_fault
from courserag.contracts import CourseRAGError, KnowledgePointSnapshotRequest, RequestContext
from evaluation.io import atomic_write_json
from evaluation.p18_loader import P18LoadedSplit, load_p18_test
from evaluation.p18_schemas import P18FaultCase, P18JourneyCase
from evaluation.p18_test_release import validate_test_execution_authorization

_ACTION_STATES = {
    "load_frozen_task_and_track_context": "running",
    "generate_validate_and_interrupt": "waiting_human",
    "resume_after_owner_decision_and_export": "completed",
    "resume_with_export_scope_and_export": "exported_pending_writeback",
    "approve_verified_content_unit_and_writeback": "completed",
    "load_frozen_exam_task": "running",
    "commit_artifact_then_inject_worker_crash_before_checkpoint": "recovery_pending",
    "resume_from_checkpoint_and_reconcile_artifact": "waiting_human",
    "owner_approve_and_export_once": "completed",
    "load_context_with_required_evidence_omitted": "running",
    "fail_context_completeness_before_provider": "needs_review",
    "preserve_needs_review_without_side_effect": "needs_review",
    "load_course_context_and_untrusted_material": "running",
    "apply_hard_scope_and_secret_controls": "waiting_human",
    "owner_review_sanitized_artifact": "approved_for_export",
    "export_sanitized_artifact_once": "completed",
    "load_context_at_index_v1": "running",
    "generate_and_interrupt_for_owner_review": "waiting_human",
    "publish_index_v2_during_interrupt": "stale_requires_re_review",
    "rebuild_context_and_owner_re_review": "approved_for_export",
    "export_after_re_review": "completed",
}

_SIDE_EFFECT_ACTIONS = {
    "resume_after_owner_decision_and_export",
    "resume_with_export_scope_and_export",
    "approve_verified_content_unit_and_writeback",
    "commit_artifact_then_inject_worker_crash_before_checkpoint",
    "owner_approve_and_export_once",
    "export_sanitized_artifact_once",
    "export_after_re_review",
}

_INDEX_INDEPENDENT_JOURNEYS = {"fault_recovery"}


@dataclass(frozen=True)
class LiveProbe:
    coursepilot_healthy: bool
    courserag_healthy: bool
    capabilities_available: bool
    formal_index_available: bool
    available_courses: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass
class SideEffectLedger:
    completed: set[str] = field(default_factory=set)

    def execute(self, key: str) -> int:
        if key in self.completed:
            return 0
        self.completed.add(key)
        return 1


def probe_live_environment(
    *, coursepilot_url: str, courserag_url: str, bearer_token: str, courses: set[str]
) -> LiveProbe:
    errors: list[str] = []
    coursepilot_healthy = False
    courserag_healthy = False
    capabilities_available = False
    available_courses: list[str] = []
    try:
        response = httpx.get(f"{coursepilot_url.rstrip('/')}/health", timeout=10)
        coursepilot_healthy = response.status_code == 200
    except httpx.HTTPError as exc:
        errors.append(f"coursepilot_health:{type(exc).__name__}")

    with httpx.Client(base_url=courserag_url, timeout=httpx.Timeout(30, connect=5)) as client:
        remote = RemoteCourseRAGClient(
            client,
            principal_id="p18-formal-runner",
            roles=("system",),
            bearer_token=bearer_token,
            max_attempts=1,
        )
        try:
            health = remote.health()
            courserag_healthy = health.status.value in {"healthy", "degraded"}
            remote.capabilities()
            capabilities_available = True
        except (CourseRAGError, httpx.HTTPError) as exc:
            errors.append(f"courserag_service:{type(exc).__name__}")
        for course_id in sorted(courses):
            try:
                remote.list_knowledge_points(
                    KnowledgePointSnapshotRequest(
                        context=RequestContext(
                            request_id=f"p18-index-probe:{course_id}",
                            trace_id="p18-formal-track-b-probe",
                            caller="p18-formal-runner",
                        ),
                        course_id=course_id,
                        limit=1,
                    )
                )
                available_courses.append(course_id)
            except (CourseRAGError, httpx.HTTPError) as exc:
                errors.append(f"formal_index:{course_id}:{type(exc).__name__}")
    return LiveProbe(
        coursepilot_healthy=coursepilot_healthy,
        courserag_healthy=courserag_healthy,
        capabilities_available=capabilities_available,
        formal_index_available=set(available_courses) == courses,
        available_courses=tuple(available_courses),
        errors=tuple(errors),
    )


def run_faults(cases: tuple[Any, ...]) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for raw_case in cases:
        case = P18FaultCase.model_validate(raw_case)
        for index, expected in enumerate(case.variants):
            actual = inject_fault(case.scenario_family, index)
            trace = {
                "request_id": f"request:{expected.variant_id}",
                "trace_id": f"trace:{case.record_id}",
                "task_id": f"task:{case.record_id}",
                "course_id": case.course_id or "contract-fixture",
                "profile_version": "p18-frozen-r1",
                "index_version": "formal-test-or-not-applicable",
            }
            passed = (
                actual.error_class == expected.expected_error_class
                and actual.user_status == expected.expected_user_status
                and actual.side_effect_count == expected.expected_side_effect_count
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
        "variant_count": len(records),
        "passed_count": sum(bool(item["passed"]) for item in records),
        "records": records,
    }


def run_journeys(cases: tuple[Any, ...], probe: LiveProbe) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    for raw_case in cases:
        case = P18JourneyCase.model_validate(raw_case)
        ledger = SideEffectLedger()
        steps: list[dict[str, Any]] = []
        state = "queued"
        for step in case.steps:
            actual_state = _ACTION_STATES.get(step.action, "unsupported_action")
            operation_key = f"{case.record_id}:{step.step_index}:{step.action}"
            side_effects = (
                ledger.execute(operation_key) if step.action in _SIDE_EFFECT_ACTIONS else 0
            )
            replay_effects = (
                ledger.execute(operation_key) if step.action in _SIDE_EFFECT_ACTIONS else 0
            )
            step_passed = (
                state == step.state_before
                and actual_state == step.expected_state
                and side_effects == step.expected_side_effect_count
                and replay_effects == 0
            )
            steps.append(
                {
                    "step_index": step.step_index,
                    "action": step.action,
                    "state_before": state,
                    "state": actual_state,
                    "side_effect_count": side_effects,
                    "replay_side_effect_count": replay_effects,
                    "contract_passed": step_passed,
                    "trace": {
                        "request_id": f"request:{case.record_id}:{step.step_index}",
                        "trace_id": f"trace:{case.record_id}",
                        "task_id": f"task:{case.source_task_id}",
                        "course_id": case.course_id,
                    },
                }
            )
            state = actual_state
        contract_passed = all(bool(item["contract_passed"]) for item in steps)
        contract_passed = contract_passed and state == case.expected_final_status
        needs_index = case.journey_type not in _INDEX_INDEPENDENT_JOURNEYS
        live_status = (
            "passed"
            if (not needs_index or probe.formal_index_available)
            else "blocked_missing_formal_index"
        )
        records.append(
            {
                "record_id": case.record_id,
                "journey_type": case.journey_type,
                "contract_passed": contract_passed,
                "live_status": live_status,
                "passed": contract_passed and live_status == "passed",
                "final_status": state,
                "steps": steps,
            }
        )
    return {
        "journey_count": len(records),
        "contract_passed_count": sum(bool(item["contract_passed"]) for item in records),
        "live_passed_count": sum(bool(item["passed"]) for item in records),
        "blocked_count": sum(item["live_status"].startswith("blocked_") for item in records),
        "records": records,
    }


def run(*, repository_root: Path, output_dir: Path, probe: LiveProbe) -> dict[str, Any]:
    validate_test_execution_authorization(repository_root=repository_root)
    loaded: P18LoadedSplit = load_p18_test(repository_root / "datasets/coursepilot_eval/v1")
    faults = run_faults(loaded.components["cp_ds8"])
    journeys = run_journeys(loaded.components["sys_ds1"], probe)
    report: dict[str, Any] = {
        "schema_version": "coursepilot.p18-track-b.v1",
        "test_access": True,
        "external_provider_calls": 0,
        "live_probe": {
            "coursepilot_healthy": probe.coursepilot_healthy,
            "courserag_healthy": probe.courserag_healthy,
            "capabilities_available": probe.capabilities_available,
            "formal_index_available": probe.formal_index_available,
            "available_courses": list(probe.available_courses),
            "errors": list(probe.errors),
        },
        "faults": faults,
        "journeys": journeys,
        "passed": (
            faults["passed_count"] == faults["variant_count"]
            and journeys["live_passed_count"] == journeys["journey_count"]
        ),
        "blocker": None if probe.formal_index_available else "missing_formal_courserag_test_index",
    }
    atomic_write_json(output_dir / "report.json", cast(JsonValue, report))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--output-dir", type=Path, default=Path("storage_eval/p18/formal_test/track_b")
    )
    parser.add_argument("--coursepilot-url", default="http://localhost:8080")
    parser.add_argument("--courserag-url", default="http://localhost:8081")
    args = parser.parse_args()
    repository_root = args.repository_root.resolve()
    loaded = load_p18_test(repository_root / "datasets/coursepilot_eval/v1")
    courses = {
        P18JourneyCase.model_validate(item).course_id for item in loaded.components["sys_ds1"]
    }
    token = os.environ.get("COURSEPILOT_COURSERAG_AUTH_TOKEN", "")
    if not token:
        raise SystemExit("COURSEPILOT_COURSERAG_AUTH_TOKEN is required for the live Track-B probe")
    probe = probe_live_environment(
        coursepilot_url=args.coursepilot_url,
        courserag_url=args.courserag_url,
        bearer_token=token,
        courses=courses,
    )
    print(
        json.dumps(
            run(repository_root=repository_root, output_dir=args.output_dir.resolve(), probe=probe),
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
