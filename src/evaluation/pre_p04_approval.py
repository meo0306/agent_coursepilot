"""Hash-bound approval for the non-Gold P04 input work package."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import P04InputWorkPackage
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text


def _append_review(path: Path, expected: ReviewLogEntry) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline before appending")
    entries: dict[str, ReviewLogEntry] = {}
    for line_number, line in enumerate(existing_text.splitlines(), start=1):
        if not line.strip():
            continue
        entry = ReviewLogEntry.model_validate_json(line)
        if entry.review_id in entries:
            raise ValueError(f"duplicate review_id in existing log at line {line_number}")
        entries[entry.review_id] = entry
    current = entries.get(expected.review_id)
    if current is not None:
        if current != expected:
            raise ValueError(f"existing review differs for {expected.review_id}")
        return
    atomic_write_text(path, existing_text + expected.model_dump_json() + "\n")


def approve_p04_input(
    *,
    dataset_root: Path,
    expected_candidate_file_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, object]:
    candidate_path = dataset_root / "candidates" / "work_packages" / "p04_input.json"
    approved_path = dataset_root / "approved" / "work_packages" / "p04_input.json"
    review_log_path = dataset_root / "reviews" / "review_log.jsonl"
    manifest_path = dataset_root / "manifest.json"
    actual_file_sha256 = sha256_file(candidate_path)
    if actual_file_sha256 != expected_candidate_file_sha256:
        raise ValueError(
            "candidate file hash differs from the explicitly approved P04 input batch: "
            f"{actual_file_sha256}"
        )
    candidate = P04InputWorkPackage.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    if candidate.review_status is not ReviewStatus.CANDIDATE or candidate.approval is not None:
        raise ValueError("P04 input is not an unapproved Candidate")
    provisional = candidate.model_copy(
        update={"review_status": ReviewStatus.APPROVED, "approval": None}
    )
    approved_record_sha256 = record_digest(provisional)
    values = provisional.model_dump(mode="json")
    values["approval"] = ApprovalRecord(
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=record_digest(candidate),
        approved_record_sha256=approved_record_sha256,
        notes=notes,
    )
    approved = P04InputWorkPackage.model_validate(values)
    if approved_path.exists():
        current = P04InputWorkPackage.model_validate_json(approved_path.read_text(encoding="utf-8"))
        if current != approved:
            raise ValueError("existing Approved P04 input differs from this approval event")
    else:
        atomic_write_json(approved_path, approved.model_dump(mode="json"))
    approval = approved.approval
    if approval is None:  # pragma: no cover - guarded by Pydantic
        raise AssertionError("Approved P04 input has no ApprovalRecord")
    _append_review(
        review_log_path,
        ReviewLogEntry(
            review_id=review_id,
            record_id=approved.record_id,
            action="approve",
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=approval.candidate_sha256,
            resulting_record_sha256=approval.approved_record_sha256,
            notes=notes,
        ),
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("gold_status") != "ds0_pilot_approved":
        raise ValueError("P04 input approval cannot change DS1 Gold status")
    phase_status = manifest.setdefault("phase_input_status", {})
    if phase_status.get("p04") not in {
        "candidate_pending_course_owner",
        "approved_for_annotation",
    }:
        raise ValueError("unexpected P04 input status")
    phase_status["p04"] = "approved_for_annotation"
    atomic_write_json(manifest_path, manifest)
    return {
        "approved_file_sha256": sha256_file(approved_path),
        "candidate_file_sha256": actual_file_sha256,
        "review_id": review_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve an exact non-Gold P04 input batch.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-candidate-file-sha256", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_p04_input(
        dataset_root=args.dataset_root,
        expected_candidate_file_sha256=args.expected_candidate_file_sha256,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
