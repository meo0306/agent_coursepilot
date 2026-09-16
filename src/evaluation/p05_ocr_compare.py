"""Compare two runs per OCR candidate without selecting or scoring a default engine."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import JsonValue

from courserag.parsers.ocr import OCRPageResult
from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file


def compare_runs(
    *,
    reports: dict[str, tuple[Path, Path]],
    output_path: Path,
    deployment_evidence_path: Path | None = None,
) -> dict[str, JsonValue]:
    providers: dict[str, JsonValue] = {}
    for provider, (first_path, second_path) in reports.items():
        first = _load_results(first_path)
        second = _load_results(second_path)
        if set(first) != set(second):
            raise ValueError(f"repeat runs differ in case IDs for {provider}")
        mismatches: list[JsonValue] = [
            case_id
            for case_id in first
            if first[case_id].semantic_sha256 != second[case_id].semantic_sha256
        ]
        providers[provider] = {
            "semantic_repeat_match": not mismatches,
            "mismatched_case_ids": mismatches,
            "run_1_report": first_path.as_posix(),
            "run_2_report": second_path.as_posix(),
            "run_1_metrics": _load_report_metrics(first_path),
            "run_2_metrics": _load_report_metrics(second_path),
        }
    comparison: dict[str, JsonValue] = {
        "schema_version": "courserag.p05-ocr-comparison.v1",
        "providers": providers,
        "automatic_composite_score": None,
        "default_selection": "requires_explicit_human_decision",
    }
    if deployment_evidence_path is not None:
        evidence = _load_deployment_evidence(deployment_evidence_path, set(reports))
        comparison["deployment_evidence"] = evidence
        comparison["deployment_evidence_sha256"] = sha256_file(deployment_evidence_path)
    atomic_write_json(output_path, comparison)
    return comparison


def _load_deployment_evidence(path: Path, providers: set[str]) -> dict[str, JsonValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("P05 deployment evidence must be a JSON object")
    if value.get("schema_version") != "courserag.p05-ocr-deployment-evidence.v1":
        raise ValueError("P05 deployment evidence schema is unsupported")
    entries = value.get("providers")
    if not isinstance(entries, dict) or set(entries) != providers:
        raise ValueError("P05 deployment evidence must cover each compared provider exactly")
    return value


def _payload(path: Path) -> dict[str, JsonValue]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("status") != "completed":
        raise ValueError(f"P05 provider report is incomplete: {path}")
    return value


def _load_results(path: Path) -> dict[str, OCRPageResult]:
    payload = _payload(path)
    cases = payload.get("cases")
    if not isinstance(cases, dict):
        raise ValueError("P05 report cases are invalid")
    results: dict[str, OCRPageResult] = {}
    for case_id, state in cases.items():
        if not isinstance(case_id, str) or not isinstance(state, dict):
            raise ValueError("P05 report case entry is invalid")
        results[case_id] = OCRPageResult.model_validate(state.get("result"))
    return results


def _load_report_metrics(path: Path) -> JsonValue:
    return _payload(path).get("report")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare repeat P05 OCR provider runs.")
    for provider in ("rapidocr", "tesseract", "paddleocr"):
        parser.add_argument(f"--{provider}-run-1", type=Path, required=True)
        parser.add_argument(f"--{provider}-run-2", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deployment-evidence", type=Path)
    args = parser.parse_args()
    reports = {
        provider: (
            getattr(args, f"{provider}_run_1"),
            getattr(args, f"{provider}_run_2"),
        )
        for provider in ("rapidocr", "tesseract", "paddleocr")
    }
    result = compare_runs(
        reports=reports,
        output_path=args.output,
        deployment_evidence_path=args.deployment_evidence,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
