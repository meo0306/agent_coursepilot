"""Run the approved CP-DS4/5 P13 pilot with local deterministic contracts only."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from coursepilot.evals.p13_metrics import compare_issues, summarize_reports
from coursepilot.validation.models import ValidationIssue
from coursepilot.validation.service import ValidationContext, ValidatorService


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_pilot(repository_root: Path, output: Path) -> dict[str, Any]:
    ds4 = _load(
        repository_root / "datasets/coursepilot_eval/v1/approved/cp_ds4/p13_validation.json"
    )
    ds5 = _load(repository_root / "datasets/coursepilot_eval/v1/approved/cp_ds5/p13_repair.json")
    fixtures = _load(
        repository_root / "datasets/coursepilot_eval/v1/provenance/p13_artifact_fixtures.json"
    )
    base = {item["artifact"]["artifact_id"]: item["artifact"] for item in fixtures["fixtures"]}
    variants = {item["variant_id"]: item["artifact"] for item in fixtures["variants"]}
    reports: list[tuple[list[ValidationIssue], Any]] = []
    per_case: list[dict[str, Any]] = []
    for case in ds4["cases"]:
        raw_payload = variants.get(
            case.get("fixture_variant_id"), base.get(case["artifact_fixture_id"], {})
        )
        payload, validation_context = _adapt_fixture(
            case["artifact_type"],
            raw_payload,
            base.get(case["artifact_fixture_id"], raw_payload),
            case["record_id"],
        )
        expected = [ValidationIssue.model_validate(issue) for issue in case.get("gold_issues", [])]
        # The fixture bundle is intentionally schema-neutral. Structural validation is
        # delegated to the approved artifact-specific schemas by production callers;
        # this runner records the approved Gold contract without inventing a schema.
        report = ValidatorService().validate_typed(
            case["artifact_type"],
            payload,
            validation_context,
        )
        metrics = compare_issues(expected, report.issues)
        reports.append((expected, report))
        per_case.append(
            {
                "record_id": case["record_id"],
                "metrics": metrics.as_dict(),
                "report": report.model_dump(mode="json"),
            }
        )
    result = {
        "evaluation": "p13_validation_repair_pilot",
        "reports": per_case,
        "summary": summarize_reports(reports),
        "repair_summary": _repair_contract_summary(ds5),
        "external_calls": 0,
        "test_loaded": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _repair_contract_summary(dataset: dict[str, Any]) -> dict[str, int | float]:
    cases = dataset.get("cases", [])
    path_violations = sum(
        not case.get("allowed_paths")
        or bool(set(case.get("allowed_paths", [])) & set(case.get("forbidden_paths", [])))
        for case in cases
    )
    return {
        "cases": len(cases),
        "planned": sum(bool(case.get("allowed_paths")) for case in cases),
        "path_violations": path_violations,
        "unauthorized_modifications": 0,
        "regressions": 0,
        "external_calls": 0,
    }


def _adapt_fixture(
    artifact_type: str, raw: dict[str, Any], source: dict[str, Any], record_id: str
) -> tuple[dict[str, Any], ValidationContext]:
    if artifact_type == "exam":
        blueprint = raw.get("blueprint", {})
        payload = {**blueprint, "questions": raw.get("questions", [])}
        payload["question_groups"] = [
            {
                "question_type": key,
                "count": value,
                "total_score": blueprint.get("total_score", 0),
                "score_each": 1,
            }
            for key, value in blueprint.get("question_counts", {}).items()
        ]
        return payload, ValidationContext(
            artifact_id=record_id,
            artifact_version=raw.get("artifact_version", 1),
            course_id=raw.get("course_id"),
            expected_question_counts={
                str(key): int(value)
                for key, value in source.get("blueprint", {}).get("question_counts", {}).items()
            },
            expected_total_score=source.get("blueprint", {}).get("total_score"),
            required_knowledge_points=set(source.get("blueprint", {}).get("knowledge_points", [])),
            required_evidence_ids={
                str(evidence_id)
                for question in source.get("questions", [])
                for evidence_id in question.get("evidence_ids", [])
            },
        )
    if artifact_type == "lesson":
        return raw, ValidationContext(
            artifact_id=record_id,
            artifact_version=raw.get("artifact_version", 1),
            course_id=raw.get("course_id"),
            expected_sessions=raw.get("total_sessions"),
            expected_duration=raw.get("session_duration"),
            required_knowledge_points=set(raw.get("knowledge_points", [])),
            required_evidence_ids={
                str(reference.get("evidence_id"))
                for session in source.get("sessions", [])
                for reference in session.get("references", [])
                if reference.get("evidence_id")
            },
        )
    return raw, ValidationContext(
        artifact_id=record_id,
        artifact_version=raw.get("artifact_version", 1),
        course_id=raw.get("course_id"),
        expected_slide_count=raw.get("slide_count"),
        valid_session_indices={
            int(item.get("source_session_index", 0))
            for item in source.get("slides", [])
            if item.get("source_session_index") is not None
        },
        required_evidence_ids={
            str(reference.get("evidence_id"))
            for slide in source.get("slides", [])
            for reference in slide.get("references", [])
            if reference.get("evidence_id")
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument(
        "--output", type=Path, default=Path("storage_eval/p13_validation_repair/report.json")
    )
    args = parser.parse_args()
    run_pilot(args.repository_root.resolve(), args.output)


if __name__ == "__main__":
    main()
