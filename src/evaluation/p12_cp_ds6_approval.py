"""Promote the exact, owner-approved P12 CP-DS6 Pilot Candidate."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import CPDS6P12PilotDataset
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
CANDIDATE_PATH = DATASET_ROOT / "candidates/cp_ds6/p12_interrupt_recovery_r1.json"
APPROVED_PATH = DATASET_ROOT / "approved/cp_ds6/p12_interrupt_recovery.json"
APPROVAL_PATH = DATASET_ROOT / "provenance/p12_cp_ds6_approval.json"
REVIEW_PATH = DATASET_ROOT / "reviews/p12_cp_ds6_review_decisions.json"


def _append_log(path: Path, entries: list[ReviewLogEntry]) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    parsed = [ReviewLogEntry.model_validate_json(line) for line in existing.splitlines() if line]
    by_id = {item.review_id: item for item in parsed}
    for entry in entries:
        current = by_id.get(entry.review_id)
        if current is not None and current != entry:
            raise ValueError(f"existing review log entry differs: {entry.review_id}")
        if current is None:
            parsed.append(entry)
    atomic_write_text(path, "".join(item.model_dump_json() + "\n" for item in parsed))


def approve_p12_cp_ds6(
    *,
    repository_root: Path,
    expected_candidate_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
) -> dict[str, Any]:
    root = repository_root.resolve()
    candidate_path = root / CANDIDATE_PATH
    if not candidate_path.is_file():
        raise ValueError("P12 Candidate is missing")
    candidate_sha = sha256_file(candidate_path)
    if candidate_sha != expected_candidate_sha256:
        raise ValueError("literal P12 Candidate SHA-256 does not match")
    candidate = CPDS6P12PilotDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    approval_path = root / APPROVAL_PATH
    if approval_path.is_file():
        existing = json.loads(approval_path.read_text(encoding="utf-8"))
        if (
            existing.get("candidate_sha256") != candidate_sha
            or existing.get("reviewer_id") != reviewer_id
            or existing.get("reviewed_at") != reviewed_at.isoformat()
            or existing.get("review_id") != review_id
        ):
            raise ValueError("existing P12 approval differs from requested approval")
        approved_path = root / APPROVED_PATH
        if not approved_path.is_file() or sha256_file(approved_path) != existing.get(
            "approved_sha256"
        ):
            raise ValueError("existing P12 approved package changed")
        return {
            "candidate_sha256": candidate_sha,
            "approved_sha256": existing["approved_sha256"],
            "approval_sha256": sha256_file(approval_path),
            "record_count": existing["record_count"],
            "formal_gold_promoted": False,
        }
    dataset_root = root / DATASET_ROOT
    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    if governance.get("gold_status") != "skeleton_no_formal_gold":
        raise ValueError("P12 approval requires skeleton_no_formal_gold")
    lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P12 approval cannot run after Test lock")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("P12 approval requires empty Dev/Test")

    approved_cases = []
    approved_hashes: dict[str, str] = {}
    logs: list[ReviewLogEntry] = []
    decision_items = []
    for index, record in enumerate(candidate.cases, start=1):
        candidate_record_sha = record_digest(record)
        approved_without_meta = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_record_sha = record_digest(approved_without_meta)
        record_review_id = f"{review_id}.{index:03d}"
        values = approved_without_meta.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=record_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_record_sha,
            approved_record_sha256=approved_record_sha,
            notes="P12 CP-DS6 Pilot input approval only; no runtime evaluation or formal Gold promotion.",
        ).model_dump(mode="json")
        approved = type(record).model_validate(values)
        approved_cases.append(approved)
        approved_hashes[record.record_id] = approved_record_sha
        decision_items.append(
            {
                "record_id": record.record_id,
                "decision": "pass",
                "notes": "Exact Candidate approved.",
            }
        )
        logs.append(
            ReviewLogEntry(
                review_id=record_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_record_sha,
                resulting_record_sha256=approved_record_sha,
                notes="P12 input only; no runtime evaluation.",
            )
        )
    approved_dataset = candidate.model_copy(update={"cases": approved_cases})
    atomic_write_json(root / APPROVED_PATH, approved_dataset.model_dump(mode="json"))
    review_payload = {
        "schema_version": "coursepilot.p12-cp-ds6-review-decisions.v1",
        "candidate_sha256": candidate_sha,
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at.isoformat(),
        "decisions": decision_items,
        "attestation": "Owner approved the exact Candidate SHA in conversation.",
    }
    atomic_write_json(root / REVIEW_PATH, cast(JsonValue, review_payload))
    approval_payload = {
        "schema_version": "coursepilot.p12-cp-ds6-approval.v1",
        "candidate_sha256": candidate_sha,
        "approved_sha256": sha256_file(root / APPROVED_PATH),
        "candidate_record_sha256": {
            item.record_id: record_digest(item) for item in candidate.cases
        },
        "approved_record_sha256": approved_hashes,
        "record_count": len(approved_cases),
        "reviewer_id": reviewer_id,
        "reviewed_at": reviewed_at.isoformat(),
        "review_id": review_id,
        "scope": "cp_ds6_pilot_input_only",
    }
    atomic_write_json(root / APPROVAL_PATH, cast(JsonValue, approval_payload))
    _append_log(dataset_root / "reviews/review_log.jsonl", logs)
    governance.setdefault("phase_input_status", {})["p12"] = "approved_for_implementation"
    governance.setdefault("phase_execution_status", {})["p12"] = "not_started"
    atomic_write_json(governance_path, governance)
    return {
        "candidate_sha256": candidate_sha,
        "approved_sha256": approval_payload["approved_sha256"],
        "approval_sha256": sha256_file(root / APPROVAL_PATH),
        "record_count": len(approved_cases),
        "formal_gold_promoted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", default="p12-cp-ds6-input-approval")
    args = parser.parse_args()
    print(
        approve_p12_cp_ds6(
            repository_root=args.repository_root,
            expected_candidate_sha256=args.candidate_sha256,
            reviewer_id=args.reviewer_id,
            reviewed_at=datetime.fromisoformat(args.reviewed_at),
            review_id=args.review_id,
        )
    )


if __name__ == "__main__":
    main()
