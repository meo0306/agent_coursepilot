"""Validate both owner reviews and emit the P17 Blind approval candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.p10_schemas import P17SecurityBlindDataset


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def validate_and_build(package_root: Path) -> dict[str, Any]:
    candidate_path = package_root / "blind_candidate_r1.json"
    manifest_path = package_root / "manifest.json"
    first_path = package_root / "blind_first_review_decisions_r1.json"
    second_path = package_root / "blind_second_review_decisions_r1.json"
    output_path = package_root / "blind_approval_candidate_r1.json"
    for path in (candidate_path, manifest_path, first_path, second_path):
        if not path.is_file():
            raise FileNotFoundError(path)
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite approval candidate: {output_path}")

    dataset = P17SecurityBlindDataset.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    manifest = _load(manifest_path)
    first = _load(first_path)
    second = _load(second_path)

    candidate_sha = _sha256(candidate_path)
    bundle_sha = manifest.get("bundle_sha256")
    if candidate_sha != manifest.get("candidate_sha256"):
        raise ValueError("Blind Candidate hash does not match Manifest")
    for name, review in (("first", first), ("second", second)):
        if review.get("bundle_sha256") != bundle_sha:
            raise ValueError(f"{name} review Bundle hash mismatch")
        if review.get("candidate_sha256") != candidate_sha:
            raise ValueError(f"{name} review Candidate hash mismatch")
        if not review.get("reviewed_at") or review.get("reviewer_id") != "course_owner":
            raise ValueError(f"{name} review lacks owner identity or timestamp")

    expected_ids = [case.record_id for case in dataset.cases]
    first_records = first.get("records")
    second_records = second.get("records")
    if not isinstance(first_records, list) or not isinstance(second_records, list):
        raise ValueError("review records must be arrays")
    if [record.get("record_id") for record in first_records] != expected_ids:
        raise ValueError("first review IDs/order do not match Candidate")
    if [record.get("record_id") for record in second_records] != expected_ids:
        raise ValueError("second review IDs/order do not match Candidate")

    returned = [record for record in first_records if record.get("decision") != "pass"]
    if returned:
        raise ValueError(f"first review contains {len(returned)} non-pass decisions")

    by_id = {case.record_id: case for case in dataset.cases}
    mismatches: list[dict[str, str | None]] = []
    for record in second_records:
        case = by_id[str(record["record_id"])]
        label = record.get("decision_label")
        family = record.get("decision_family")
        if label != case.label or family != case.family:
            mismatches.append(
                {
                    "record_id": case.record_id,
                    "expected_label": case.label,
                    "actual_label": label,
                    "expected_family": case.family,
                    "actual_family": family,
                }
            )
    if mismatches:
        raise ValueError(f"second review disagrees with Candidate: {mismatches}")

    approval = {
        "schema_version": "courserag.p17-security-blind-approval-candidate.v1",
        "approval_status": "pending_course_owner_exact_sha256",
        "approval_scope": "p17_security_blind_bundle_and_single_run",
        "bundle_sha256": bundle_sha,
        "candidate_sha256": candidate_sha,
        "candidate_path": str(candidate_path.as_posix()),
        "manifest_sha256": _sha256(manifest_path),
        "first_review_sha256": _sha256(first_path),
        "second_review_sha256": _sha256(second_path),
        "qualification_report_sha256": manifest["qualification_report_sha256"],
        "protocol_sha256": manifest["protocol_sha256"],
        "profile_sha256": manifest["profile_sha256"],
        "record_count": len(dataset.cases),
        "first_review_pass_count": len(first_records),
        "second_review_match_count": len(second_records),
        "malicious_count": sum(case.label == "malicious" for case in dataset.cases),
        "benign_count": sum(case.label == "benign" for case in dataset.cases),
        "blind_run_limit": 1,
        "blind_runs_completed": 0,
        "runtime_network_required": False,
        "external_provider_calls_allowed": 0,
        "post_blind_tuning_allowed": False,
    }
    _write_json(output_path, approval)
    return {
        "approval_candidate": str(output_path.resolve()),
        "approval_candidate_sha256": _sha256(output_path),
        **approval,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate_and_build(args.package_root),
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
