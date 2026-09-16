"""Approve one exact, twice-reviewed P13 CP-DS4/5 Pilot Gold bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import CPDS4P13PilotDataset, CPDS5P13PilotDataset
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p13_cp_ds45_data import DS4_PATH, DS5_PATH, FIXTURE_PATH, MANIFEST_PATH, _digest

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
APPROVED_DS4_PATH = DATASET_ROOT / "approved/cp_ds4/p13_validation.json"
APPROVED_DS5_PATH = DATASET_ROOT / "approved/cp_ds5/p13_repair.json"
APPROVAL_PATH = DATASET_ROOT / "provenance/p13_gold_bundle_approval.json"
FIRST_REVIEW_PATH = DATASET_ROOT / "reviews/p13_first_review_decisions.json"
SECOND_REVIEW_PATH = DATASET_ROOT / "reviews/p13_second_review_decisions.json"


def _append_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline")
    existing = {
        item.review_id: item
        for line in existing_text.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    new_lines: list[str] = []
    for addition in additions:
        current = existing.get(addition.review_id)
        if current is not None and current != addition:
            raise ValueError(f"existing P13 review log entry differs: {addition.review_id}")
        if current is None:
            new_lines.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(new_lines))


def _load_review(
    path: Path,
    *,
    bundle_sha256: str,
    review_pass: str,
    expected_ids: list[str],
    reviewer_id: str,
    approved_at: datetime,
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "coursepilot.p13-review-decisions.v1":
        raise ValueError(f"P13 {review_pass} review schema is invalid")
    if payload.get("bundle_sha256") != bundle_sha256 or payload.get("review_pass") != review_pass:
        raise ValueError(f"P13 {review_pass} review binds another Bundle or pass")
    if payload.get("reviewer_id") != reviewer_id:
        raise ValueError(f"P13 {review_pass} review has a different reviewer")
    reviewed_at = datetime.fromisoformat(str(payload["reviewed_at"]).replace("Z", "+00:00"))
    if reviewed_at > approved_at:
        raise ValueError(f"P13 {review_pass} review occurred after approval")
    decisions = payload.get("decisions")
    if not isinstance(decisions, list):
        raise ValueError(f"P13 {review_pass} review decisions are missing")
    ids = [item.get("record_id") for item in decisions]
    if ids != expected_ids or any(item.get("decision") != "pass" for item in decisions):
        raise ValueError(f"P13 {review_pass} review is incomplete, reordered, or contains returns")
    return cast(dict[str, Any], payload)


def _promote_records(
    records: list[Any],
    *,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
) -> tuple[list[Any], dict[str, str], dict[str, str], list[ReviewLogEntry]]:
    approved_records: list[Any] = []
    candidate_hashes: dict[str, str] = {}
    approved_hashes: dict[str, str] = {}
    logs: list[ReviewLogEntry] = []
    for index, record in enumerate(records, 1):
        if record.review_status is not ReviewStatus.CANDIDATE or record.approval is not None:
            raise ValueError("P13 approval accepts Candidate records only")
        candidate_hash = record_digest(record)
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_hash = record_digest(provisional)
        item_review_id = f"{review_id}.record.{index:03d}"
        values = provisional.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=item_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_hash,
            approved_record_sha256=approved_hash,
            notes="P13 CP-DS4/5 Pilot Gold approval; not the P18 final CoursePilot Gold freeze.",
        ).model_dump(mode="json")
        approved = type(record).model_validate(values)
        approved_records.append(approved)
        candidate_hashes[record.record_id] = candidate_hash
        approved_hashes[record.record_id] = approved_hash
        logs.append(
            ReviewLogEntry(
                review_id=item_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_hash,
                resulting_record_sha256=approved_hash,
                notes="P13 Pilot Gold only; final CP-DS4/5 freeze remains P18 scope.",
            )
        )
    return approved_records, candidate_hashes, approved_hashes, logs


def _existing_result(
    root: Path, *, expected_bundle_sha256: str, reviewer_id: str, review_id: str
) -> dict[str, object] | None:
    path = root / APPROVAL_PATH
    if not path.is_file():
        return None
    approval = json.loads(path.read_text(encoding="utf-8"))
    if (
        approval.get("bundle_sha256") != expected_bundle_sha256
        or approval.get("reviewer_id") != reviewer_id
        or approval.get("review_id") != review_id
    ):
        raise ValueError("existing P13 approval differs from the requested approval")
    expected = {
        "approved_ds4_sha256": root / APPROVED_DS4_PATH,
        "approved_ds5_sha256": root / APPROVED_DS5_PATH,
        "first_review_copy_sha256": root / FIRST_REVIEW_PATH,
        "second_review_copy_sha256": root / SECOND_REVIEW_PATH,
    }
    for field, artifact in expected.items():
        if not artifact.is_file() or sha256_file(artifact) != approval.get(field):
            raise ValueError(f"existing P13 approved artifact changed: {artifact}")
    return {
        "bundle_sha256": expected_bundle_sha256,
        "approval_sha256": sha256_file(path),
        "approved_ds4_sha256": approval["approved_ds4_sha256"],
        "approved_ds5_sha256": approval["approved_ds5_sha256"],
        "record_count": approval["record_count"],
        "p13_formal_eval_ready": True,
        "final_coursepilot_gold_promoted": False,
    }


def approve_p13_bundle(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    first_review_path: Path,
    second_review_path: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
) -> dict[str, object]:
    root = repository_root.resolve()
    manifest = json.loads((root / MANIFEST_PATH).read_text(encoding="utf-8"))
    if manifest.get("bundle_sha256") != expected_bundle_sha256:
        raise ValueError("literal P13 Gold Bundle SHA-256 does not match")
    hashes = {
        "ds4": sha256_file(root / DS4_PATH),
        "ds5": sha256_file(root / DS5_PATH),
        "fixtures": sha256_file(root / FIXTURE_PATH),
    }
    if hashes != manifest.get("candidate_hashes") or _digest(hashes) != expected_bundle_sha256:
        raise ValueError("P13 Candidate, Fixture, Manifest, or Bundle identity changed")

    existing = _existing_result(
        root,
        expected_bundle_sha256=expected_bundle_sha256,
        reviewer_id=reviewer_id,
        review_id=review_id,
    )
    if existing is not None:
        return existing

    ds4 = CPDS4P13PilotDataset.model_validate_json((root / DS4_PATH).read_text(encoding="utf-8"))
    ds5 = CPDS5P13PilotDataset.model_validate_json((root / DS5_PATH).read_text(encoding="utf-8"))
    first_ids = [item.record_id for item in ds4.cases] + [item.record_id for item in ds5.cases]
    second_ids = [
        item.record_id
        for item in ds4.cases
        if any(issue.layer in {"L3", "L4"} for issue in item.gold_issues)
        or len(item.gold_issues) > 1
    ] + [item.record_id for item in ds5.cases]
    first_source = first_review_path.resolve()
    second_source = second_review_path.resolve()
    for path in (first_source, second_source):
        if not path.is_file() or not path.is_relative_to(root):
            raise ValueError("P13 review decisions must exist under the repository")
    first = _load_review(
        first_source,
        bundle_sha256=expected_bundle_sha256,
        review_pass="first",
        expected_ids=first_ids,
        reviewer_id=reviewer_id,
        approved_at=reviewed_at,
    )
    second = _load_review(
        second_source,
        bundle_sha256=expected_bundle_sha256,
        review_pass="second",
        expected_ids=second_ids,
        reviewer_id=reviewer_id,
        approved_at=reviewed_at,
    )

    dataset_root = root / DATASET_ROOT
    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P13 Pilot approval cannot modify a locked Test set")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("P13 Pilot approval requires empty CoursePilot Dev/Test")

    records = [*ds4.cases, *ds5.cases]
    approved, candidate_hashes, approved_hashes, logs = _promote_records(
        records,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )
    approved_ds4 = ds4.model_copy(update={"cases": approved[: len(ds4.cases)]})
    approved_ds5 = ds5.model_copy(update={"cases": approved[len(ds4.cases) :]})
    atomic_write_json(root / APPROVED_DS4_PATH, approved_ds4.model_dump(mode="json"))
    atomic_write_json(root / APPROVED_DS5_PATH, approved_ds5.model_dump(mode="json"))
    atomic_write_json(root / FIRST_REVIEW_PATH, cast(JsonValue, first))
    atomic_write_json(root / SECOND_REVIEW_PATH, cast(JsonValue, second))

    approval_payload = {
        "schema_version": "coursepilot.p13-gold-bundle-approval.v1",
        "bundle_sha256": expected_bundle_sha256,
        "candidate_hashes": hashes,
        "candidate_record_sha256": candidate_hashes,
        "approved_record_sha256": approved_hashes,
        "approved_ds4_sha256": sha256_file(root / APPROVED_DS4_PATH),
        "approved_ds5_sha256": sha256_file(root / APPROVED_DS5_PATH),
        "source_first_review_sha256": sha256_file(first_source),
        "source_second_review_sha256": sha256_file(second_source),
        "first_review_copy_sha256": sha256_file(root / FIRST_REVIEW_PATH),
        "second_review_copy_sha256": sha256_file(root / SECOND_REVIEW_PATH),
        "record_count": {"cp_ds4": len(ds4.cases), "cp_ds5": len(ds5.cases), "total": 45},
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at.isoformat(),
        "review_id": review_id,
        "scope": "p13_cp_ds4_validation_and_cp_ds5_targeted_repair_pilot_gold",
        "p13_formal_eval_ready": True,
        "final_coursepilot_gold_promoted": False,
    }
    atomic_write_json(root / APPROVAL_PATH, cast(JsonValue, approval_payload))
    _append_log(dataset_root / "reviews/review_log.jsonl", logs)

    governance.setdefault("gold_components", {}).update(
        {"cp_ds4_p13_pilot": "approved", "cp_ds5_p13_pilot": "approved"}
    )
    governance["gold_status"] = "p13_cp_ds4_ds5_pilot_approved"
    governance.setdefault("phase_input_status", {})["p12"] = "completed_gate_passed"
    governance["phase_input_status"]["p13"] = "completed_gate_passed"
    governance.setdefault("phase_execution_status", {})["p12"] = "completed"
    governance["phase_execution_status"]["p13"] = "completed"
    atomic_write_json(governance_path, cast(JsonValue, governance))
    return {
        "bundle_sha256": expected_bundle_sha256,
        "approval_sha256": sha256_file(root / APPROVAL_PATH),
        "approved_ds4_sha256": approval_payload["approved_ds4_sha256"],
        "approved_ds5_sha256": approval_payload["approved_ds5_sha256"],
        "record_count": approval_payload["record_count"],
        "p13_formal_eval_ready": True,
        "final_coursepilot_gold_promoted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", default="p13-cp-ds45-pilot-gold-approval")
    args = parser.parse_args()
    print(
        json.dumps(
            approve_p13_bundle(
                repository_root=args.repository_root,
                expected_bundle_sha256=args.bundle_sha256,
                first_review_path=args.first_review,
                second_review_path=args.second_review,
                reviewer_id=args.reviewer_id,
                reviewed_at=datetime.fromisoformat(args.reviewed_at),
                review_id=args.review_id,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
