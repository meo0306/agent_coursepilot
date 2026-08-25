"""Create P18 Dev freeze candidates; approval and Test locking remain manual."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from coursepilot.evals.formal_schemas import CPDS0ManifestDataset, CPManifestRecord
from evaluation.datasets import canonical_json_bytes


def build_freeze_candidate(
    *, report: dict[str, Any], identities: dict[str, str], output_path: Path
) -> dict[str, Any]:
    required = {
        "git_workspace",
        "dataset_approval",
        "model_profile",
        "prompt",
        "template",
        "validator",
        "exporter",
        "renderer",
        "courserag_fixture",
    }
    missing = required - identities.keys()
    if missing:
        raise ValueError(f"P18 freeze identities missing: {sorted(missing)}")
    if report.get("mode") != "dev":
        raise ValueError("P18 freeze candidate can only be produced from Dev")
    payload = {
        "schema_version": "coursepilot.p18-freeze-candidate.v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "awaiting_course_owner_approval",
        "test_access": False,
        "identities": dict(sorted(identities.items())),
        "dev_report_sha256": hashlib.sha256(canonical_json_bytes(report)).hexdigest(),
        "fallback_allowed": False,
        "model_routing_claim": "mr1_single_physical_model_profiled",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {**payload, "candidate_sha256": hashlib.sha256(output_path.read_bytes()).hexdigest()}


def build_dev_freeze_package(
    *,
    repository_root: Path,
    business_report_path: Path,
    component_report_path: Path,
    export_report_path: Path,
    exam_parallel_report_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Create the unapproved CP-DS0 and P18 Dev freeze candidates."""

    business = _json(business_report_path)
    components = _json(component_report_path)
    exports = _json(export_report_path)
    parallel = _json(exam_parallel_report_path)
    rows = _json(Path(str(business["rows_path"])))
    ledger_path = business_report_path.parent / "ledger.json"
    identities = collect_freeze_identities(
        repository_root=repository_root,
        ledger_path=ledger_path,
    )
    by_component: dict[str, dict[str, int]] = {}
    for component in ("cp_ds1", "cp_ds2", "cp_ds3"):
        selected = [
            row for row in rows if row["component"] == component and row["track"] == "cp_b10"
        ]
        by_component[component] = {
            "samples": len(selected),
            "succeeded": sum(row.get("status") == "succeeded" for row in selected),
            "contract_passed": sum(bool(row.get("contract_pass")) for row in selected),
        }
    quality_debt = [
        f"{component} CP-B10 contract passed {values['contract_passed']}/{values['samples']}."
        for component, values in by_component.items()
        if values["contract_passed"] != values["samples"]
    ]
    if exports["failed"]:
        quality_debt.append(
            f"Export/render passed {exports['passed']}/{exports['executed']} Dev artifacts."
        )
    l0_pass = all(value == 0 for value in business["metrics"]["l0"].values())
    summary = {
        "schema_version": "coursepilot.p18-dev-freeze-summary.v1",
        "status": (
            "freeze_candidate_ready_with_dev_quality_debt"
            if quality_debt
            else "freeze_candidate_ready"
        ),
        "test_access": False,
        "test_locked": False,
        "external_provider_usage": business.get("cumulative_provider_usage", business["ledger"]),
        "closure_provider_usage": business["ledger"],
        "business_metrics": business["metrics"],
        "business_by_component": by_component,
        "offline_components": {
            key: {
                field: components[key][field]
                for field in ("executed", "passed", "failed", "carried")
            }
            for key in ("validation", "repair", "recovery", "templates", "faults")
        },
        "export_render": {
            "executed": exports["executed"],
            "passed": exports["passed"],
            "failed": exports["failed"],
        },
        "exam_parallel_contract": {
            "mode": parallel["mode"],
            "cases": len(parallel["cases"]),
            "questions": sum(int(case["question_count"]) for case in parallel["cases"]),
            "external_provider_calls": 0,
        },
        "model_routing": _model_routing(ledger_path),
        "l0_pass": l0_pass,
        "fallback_samples": sum(
            track["fallback_samples"] for track in business["metrics"]["tracks"].values()
        ),
        "dev_revision_count": 1,
        "quality_debt": quality_debt,
        "limitations": [
            "CP-B0 retains four Legacy Provider/schema failures as observed baseline behavior.",
            "Main and Light resolve to one physical model; dual-model savings are not claimed.",
            "P17 prompt-injection automation remains default-off isolated debt; P18 relies on independent hard controls.",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "dev_freeze_summary.json"
    _write_json(summary_path, summary)

    cp_ds0 = CPDS0ManifestDataset(
        dataset_id="coursepilot-eval",
        dataset_version="p18-dev-freeze-candidate-r1",
        records=[
            CPManifestRecord(
                record_id="p18-cp-ds0-dev-freeze-r1",
                review_status="candidate",
                candidate_source="p18_dev_freeze",
                graph_version=identities["git_workspace"],
                courserag_fixture_version=identities["courserag_fixture"],
                template_registry_version=identities["template"],
                validator_version=identities["validator"],
                repair_policy_version=identities["validator"],
                exporter_version=identities["exporter"],
                rubric_version="p18-human-review-v1",
            )
        ],
    )
    cp_ds0_path = (
        repository_root
        / "datasets/coursepilot_eval/v1/candidates/cp_ds0/p18_manifest_candidate_r1.json"
    )
    _write_json(cp_ds0_path, cp_ds0.model_dump(mode="json"))
    combined_report = {
        "mode": "dev",
        "summary_sha256": _sha(summary_path),
        "cp_ds0_candidate_sha256": _sha(cp_ds0_path),
        "l0_pass": summary["l0_pass"],
        "fallback_samples": summary["fallback_samples"],
        "quality_debt": summary["quality_debt"],
        "limitations": summary["limitations"],
    }
    freeze_path = output_dir / "p18_frozen_manifest_candidate.json"
    candidate = build_freeze_candidate(
        report=combined_report,
        identities=identities,
        output_path=freeze_path,
    )
    return {
        "summary": str(summary_path),
        "cp_ds0_candidate": str(cp_ds0_path),
        "cp_ds0_candidate_sha256": _sha(cp_ds0_path),
        "frozen_manifest_candidate": str(freeze_path),
        "frozen_manifest_candidate_sha256": candidate["candidate_sha256"],
    }


def build_test_preflight_protocol(
    *,
    frozen_manifest_path: Path,
    cp_ds0_candidate_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Describe the still-unexecuted Test boundary without loading Test bodies."""

    payload = {
        "schema_version": "coursepilot.p18-test-preflight.v1",
        "status": "awaiting_course_owner_approval",
        "external_calls_executed": 0,
        "test_access": False,
        "test_lock_written": False,
        "frozen_manifest_sha256": _sha(frozen_manifest_path),
        "cp_ds0_candidate_sha256": _sha(cp_ds0_candidate_path),
        "scope": {
            "track_a_test_tasks": 12,
            "stability_additional_runs": 6,
            "track_b_sys_journeys": 8,
            "blind_fault_security_cases": 10,
            "outbound_data": "approved Test task text plus bounded KP/Evidence only",
            "forbidden_outbound_data": [
                "Gold labels",
                "full course documents",
                "review decisions",
                "user identity",
                "Secrets",
            ],
        },
        "estimate": {
            "deepseek_requests": 235,
            "deepseek_input_tokens": 810000,
            "deepseek_output_and_thinking_tokens": 840000,
            "deepseek_cost_cny": "2.49",
            "cohere_search_units": 24,
        },
        "hard_limits": {
            "deepseek_cost_cny": "4.00",
            "deepseek_requests": 260,
            "deepseek_input_tokens": 1200000,
            "deepseek_output_and_thinking_tokens": 1200000,
            "cohere_search_units": 40,
        },
        "execution_policy": {
            "single_locked_test_run": True,
            "same_manifest_resume_only": True,
            "fallback_allowed": False,
            "post_test_tuning_allowed": False,
            "automatic_budget_extension": False,
        },
    }
    _write_json(output_path, payload)
    return {**payload, "protocol_sha256": _sha(output_path)}


def collect_freeze_identities(*, repository_root: Path, ledger_path: Path) -> dict[str, str]:
    approval = (
        repository_root / "datasets/coursepilot_eval/v1/provenance/p18_formal_gold_approval.json"
    )
    ledger = _json(ledger_path)
    prompt_rows = sorted(
        {
            (
                str(item.get("invocation", {}).get("prompt_name")),
                str(item.get("invocation", {}).get("prompt_sha256")),
            )
            for item in ledger["requests"].values()
            if item.get("invocation", {}).get("prompt_name")
        }
    )
    return {
        "git_workspace": _tree_sha(
            repository_root,
            ["src", "alembic", "resources", "datasets/schemas", "pyproject.toml", "uv.lock"],
        ),
        "dataset_approval": _sha(approval),
        "model_profile": _tree_sha(repository_root, ["resources/model_profiles"]),
        "prompt": hashlib.sha256(canonical_json_bytes(prompt_rows)).hexdigest(),
        "template": _tree_sha(repository_root, ["resources/templates"]),
        "validator": _tree_sha(
            repository_root, ["src/coursepilot/validation", "src/coursepilot/repair"]
        ),
        "exporter": _tree_sha(repository_root, ["src/coursepilot/exporters"]),
        "renderer": _tree_sha(
            repository_root, ["src/coursepilot/rendering", "resources/renderers"]
        ),
        "courserag_fixture": _tree_sha(
            repository_root,
            [
                "datasets/coursepilot_eval/v1/approved/cp_ds1/p18_formal.json",
                "datasets/coursepilot_eval/v1/approved/cp_ds2/p18_formal.json",
                "datasets/coursepilot_eval/v1/approved/cp_ds3/p18_formal.json",
            ],
        ),
    }


def _model_routing(ledger_path: Path) -> dict[str, Any]:
    ledger = _json(ledger_path)
    counts: dict[str, int] = {}
    for item in ledger["requests"].values():
        profile = item.get("invocation", {}).get("profile_id")
        if profile:
            counts[str(profile)] = counts.get(str(profile), 0) + 1
    return {
        "profile_counts": dict(sorted(counts.items())),
        "logical_profiles_observed": sorted(counts),
        "fallback_or_switch": False,
        "physical_model_claim": "single_physical_model_profiled",
    }


def _tree_sha(repository_root: Path, relatives: list[str]) -> str:
    paths: list[Path] = []
    for relative in relatives:
        target = repository_root / relative
        if target.is_dir():
            paths.extend(
                path
                for path in target.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
            )
        elif target.is_file():
            paths.append(target)
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.relative_to(repository_root).as_posix()):
        digest.update(path.relative_to(repository_root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build unapproved P18 Dev freeze candidates")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--business-report", type=Path, default=Path("storage_eval/p18/dev_real_r2/report.json")
    )
    parser.add_argument(
        "--component-report", type=Path, default=Path("storage_eval/p18/dev_components/report.json")
    )
    parser.add_argument(
        "--export-report",
        type=Path,
        default=Path("storage_eval/p18/dev_exports_docker/report.json"),
    )
    parser.add_argument(
        "--exam-parallel-report",
        type=Path,
        default=Path("storage_eval/p18/dev_exam_parallel_fake/report.json"),
    )
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p18/freeze"))
    args = parser.parse_args()
    result = build_dev_freeze_package(
        repository_root=args.repository_root.resolve(),
        business_report_path=args.business_report.resolve(),
        component_report_path=args.component_report.resolve(),
        export_report_path=args.export_report.resolve(),
        exam_parallel_report_path=args.exam_parallel_report.resolve(),
        output_dir=args.output_dir.resolve(),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
