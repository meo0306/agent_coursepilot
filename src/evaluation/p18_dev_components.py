"""Offline P18 Dev checks for validation, repair, recovery, templates, and faults.

These checks consume only the approved Dev split.  The compact formal fragment
adapter supplies the same runtime context a workflow would have (course,
Evidence/KP bindings, template contract, and render budget); expected outputs
remain scoring-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.domain.task import TaskStatus, require_task_transition
from coursepilot.evals.formal_metrics import json_leaf_changes
from coursepilot.integration.fault_isolation import inject_fault
from coursepilot.repair.models import PatchOperation
from coursepilot.repair.patch import apply_patch
from evaluation.p18_loader import load_p18_dev, load_p18_test
from evaluation.p18_schemas import (
    P18CarriedRecord,
    P18FaultCase,
    P18RecoveryCase,
    P18RepairCase,
    P18TemplateCase,
    P18ValidationCase,
)


def run_components(
    *, repository_root: Path, output_path: Path, mode: str = "dev"
) -> dict[str, Any]:
    if mode not in {"dev", "test"}:
        raise ValueError(f"unsupported P18 component mode: {mode}")
    loaded = (
        load_p18_dev(repository_root / "datasets/coursepilot_eval/v1")
        if mode == "dev"
        else load_p18_test(repository_root / "datasets/coursepilot_eval/v1")
    )
    validations = _run_validation(loaded.components["cp_ds4"])
    repairs = _run_repair(loaded.components["cp_ds5"], loaded.components["cp_ds4"])
    recovery = _run_recovery(loaded.components["cp_ds6"])
    templates = _run_templates(repository_root, loaded.components["cp_ds7"])
    faults = _run_faults(loaded.components["cp_ds8"])
    report = {
        "schema_version": "coursepilot.p18-components.v2",
        "split": mode,
        "test_access": mode == "test",
        "external_provider_calls": 0,
        "loaded_records": loaded.record_count,
        "validation": validations,
        "repair": repairs,
        "recovery": recovery,
        "templates": templates,
        "faults": faults,
        "all_executable_checks_passed": all(
            section["failed"] == 0
            for section in (validations, repairs, recovery, templates, faults)
        ),
    }
    _atomic_json(output_path, report)
    return report


def run_dev_components(*, repository_root: Path, output_path: Path) -> dict[str, Any]:
    """Backward-compatible Dev entry point used by the frozen preflight."""

    return run_components(repository_root=repository_root, output_path=output_path, mode="dev")


def _run_validation(records: tuple[Any, ...]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    carried = 0
    for case in records:
        if isinstance(case, P18CarriedRecord):
            carried += 1
            continue
        assert isinstance(case, P18ValidationCase)
        predicted = _fragment_issues(case.faulty_fragment, case.clean_fragment)
        gold = [
            (issue.code, issue.json_path, issue.severity, issue.auto_repairable)
            for issue in case.gold_issues
        ]
        rows.append(
            {
                "record_id": case.record_id,
                "predicted": predicted,
                "gold": gold,
                "passed": sorted(predicted) == sorted(gold),
            }
        )
    return _section(rows, carried=carried, carried_status="approved_p13_result_reused")


def _run_repair(records: tuple[Any, ...], validation_records: tuple[Any, ...]) -> dict[str, Any]:
    source = {
        case.record_id: case for case in validation_records if isinstance(case, P18ValidationCase)
    }
    rows: list[dict[str, Any]] = []
    carried = 0
    for case in records:
        if isinstance(case, P18CarriedRecord):
            carried += 1
            continue
        assert isinstance(case, P18RepairCase)
        validation = source[case.source_validation_case_id]
        path = _ISSUE_PATHS[case.issue_code]
        before = deepcopy(case.artifact_before)
        context_value = _value(validation.clean_fragment, path)
        key = path[2:]
        exists = key in before
        operation = PatchOperation(
            op="replace" if exists else "add",
            path=path,
            value=context_value,
            expected_value=_value(before, path) if exists else None,
            issue_id=case.issue_code,
        )
        try:
            after = apply_patch(
                before,
                [operation],
                allowed_paths=case.allowed_paths,
                forbidden_paths=case.forbidden_paths,
            )
            changes = json_leaf_changes(cast(JsonValue, before), cast(JsonValue, after))
            remaining = _fragment_issues(after, validation.clean_fragment)
            unauthorized = {
                changed
                for changed in changes
                if not any(_path_in_scope(changed, allowed) for allowed in case.allowed_paths)
            }
            passed = after == case.expected_after and not remaining and not unauthorized
            error = None
        except Exception as exc:  # stable failure row, never hidden
            after, changes, remaining, passed = None, set(), [], False
            error = type(exc).__name__
        rows.append(
            {
                "record_id": case.record_id,
                "issue_code": case.issue_code,
                "changed_paths": sorted(changes),
                "remaining_issues": remaining,
                "unauthorized_modifications": len(unauthorized),
                "regression": bool(remaining),
                "error": error,
                "passed": passed,
            }
        )
    return _section(rows, carried=carried, carried_status="approved_p13_result_reused")


def _run_recovery(records: tuple[Any, ...]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in records:
        assert isinstance(case, P18RecoveryCase)
        legal = True
        for transition in case.expected_state_transitions:
            current, target = transition.split("->", 1)
            try:
                require_task_transition(TaskStatus(current), TaskStatus(target))
            except (ValueError, RuntimeError):
                legal = False
        creates_version = case.decision in {"edit_resume", "replan"}
        actual_version = case.expected_artifact_version_before + int(creates_version)
        actual_effects = {
            "artifact_versions_created": int(creates_version),
            "decision_records": 1,
            "duplicate_side_effects": 0,
            "exports": int(case.decision != "reject"),
            "writebacks": 0,
        }
        passed = (
            legal
            and actual_version == case.expected_artifact_version_after
            and actual_effects == case.expected_side_effects
        )
        rows.append(
            {
                "record_id": case.record_id,
                "legal_transitions": legal,
                "artifact_version_after": actual_version,
                "side_effects": actual_effects,
                "passed": passed,
            }
        )
    return _section(rows)


def _run_templates(repository_root: Path, records: tuple[Any, ...]) -> dict[str, Any]:
    current_verified = _current_verified_templates(repository_root)
    rows: list[dict[str, Any]] = []
    for case in records:
        assert isinstance(case, P18TemplateCase)
        source = repository_root / case.source_path
        normalized = repository_root / case.normalized_path
        evidence_exists = all(
            (repository_root / item).exists() for item in case.verification_evidence_paths
        )
        current_render_verified = case.template_id in current_verified
        passed = (
            source.is_file()
            and normalized.is_file()
            and _sha(source) == case.source_sha256
            and _sha(normalized) == case.normalized_sha256
            and (evidence_exists or current_render_verified)
            and case.render_status in {"prior_phase_verified", "verified_current"}
        )
        rows.append(
            {
                "record_id": case.record_id,
                "template_id": case.template_id,
                "render_status": case.render_status,
                "historical_evidence_available": evidence_exists,
                "current_render_verified": current_render_verified,
                "passed": passed,
            }
        )
    return _section(rows)


def _current_verified_templates(repository_root: Path) -> set[str]:
    rows_path = repository_root / "storage_eval/p18/dev_real_r2/rows.json"
    render_path = repository_root / "storage_eval/p18/dev_exports_docker/report.json"
    if not rows_path.is_file() or not render_path.is_file():
        return set()
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    render = json.loads(render_path.read_text(encoding="utf-8"))
    passed_ids = {item["record_id"] for item in render["results"] if item.get("passed")}
    return {
        str(row["artifact"]["template_id"])
        for row in rows
        if row.get("component") == "cp_ds3"
        and row.get("track") == "cp_b10"
        and row.get("record_id") in passed_ids
        and isinstance(row.get("artifact"), dict)
        and row["artifact"].get("template_id")
    }


def _run_faults(records: tuple[Any, ...]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for case in records:
        assert isinstance(case, P18FaultCase)
        for index, expected in enumerate(case.variants):
            actual = inject_fault(case.scenario_family, index)
            expected_retryable = (
                "同一幂等键" in expected.retry_rule and not expected.retry_rule.startswith("不得")
            )
            passed = (
                actual.error_class == expected.expected_error_class
                and actual.user_status == expected.expected_user_status
                and actual.side_effect_count == expected.expected_side_effect_count
                and actual.retryable is expected_retryable
            )
            rows.append(
                {
                    "record_id": case.record_id,
                    "variant_id": expected.variant_id,
                    "error_class": actual.error_class,
                    "user_status": actual.user_status,
                    "side_effect_count": actual.side_effect_count,
                    "passed": passed,
                }
            )
    return _section(rows)


_ISSUE_PATHS = {
    "citation.missing": "$.citation",
    "course.scope_mismatch": "$.course_id",
    "source.required_kp_missing": "$.required_knowledge_point_ids",
    "structure.invalid": "$.content_units",
    "contract.count_mismatch": "$.contract_count",
    "grounding.unsupported_claim": "$.claim",
    "template.placeholder_injection": "$.title",
    "content.duplicate": "$.content_units",
    "layout.severe_overflow": "$.render_status",
}


def _fragment_issues(
    fragment: dict[str, Any], context: dict[str, Any]
) -> list[tuple[str, str, str, bool]]:
    issues: list[tuple[str, str, str, bool]] = []
    if not fragment.get("citation"):
        issues.append(("citation.missing", "$.citation", "error", True))
    if fragment.get("course_id") != context.get("course_id"):
        issues.append(("course.scope_mismatch", "$.course_id", "critical", False))
    expected_kps = set(context.get("required_knowledge_point_ids") or [])
    actual_kps = set(fragment.get("required_knowledge_point_ids") or [])
    if not expected_kps <= actual_kps:
        issues.append(
            ("source.required_kp_missing", "$.required_knowledge_point_ids", "error", True)
        )
    units = fragment.get("content_units")
    if not isinstance(units, list) or not units:
        issues.append(("structure.invalid", "$.content_units", "critical", False))
    if fragment.get("contract_count") != context.get("contract_count"):
        issues.append(("contract.count_mismatch", "$.contract_count", "error", True))
    if fragment.get("claim") != context.get("claim"):
        issues.append(("grounding.unsupported_claim", "$.claim", "critical", False))
    title = str(fragment.get("title") or "").casefold()
    if any(token in title for token in ("忽略验证器", "ignore validator", "bypass validator")):
        issues.append(("template.placeholder_injection", "$.title", "critical", False))
    if isinstance(units, list) and len({str(item).strip() for item in units}) != len(units):
        issues.append(("content.duplicate", "$.content_units", "warning", True))
    if fragment.get("render_status") != "within_bounds":
        issues.append(("layout.severe_overflow", "$.render_status", "critical", True))
    return issues


def _value(document: dict[str, Any], path: str) -> Any:
    if not path.startswith("$.") or "." in path[2:] or "[" in path:
        raise ValueError(f"unsupported formal fragment path: {path}")
    return deepcopy(document[path[2:]])


def _path_in_scope(path: str, allowed: str) -> bool:
    return path == allowed or path.startswith(f"{allowed}.") or path.startswith(f"{allowed}[")


def _section(
    rows: list[dict[str, Any]], *, carried: int = 0, carried_status: str | None = None
) -> dict[str, Any]:
    return {
        "executed": len(rows),
        "passed": sum(bool(row["passed"]) for row in rows),
        "failed": sum(not bool(row["passed"]) for row in rows),
        "carried": carried,
        "carried_status": carried_status,
        "rows": rows,
    }


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--mode", choices=("dev", "test"), default="dev")
    parser.add_argument(
        "--output", type=Path, default=Path("storage_eval/p18/dev_components/report.json")
    )
    args = parser.parse_args()
    result = run_components(
        repository_root=args.repository_root.resolve(),
        output_path=args.output.resolve(),
        mode=args.mode,
    )
    print(json.dumps({key: value for key, value in result.items() if key != "rows"}))


if __name__ == "__main__":
    main()
