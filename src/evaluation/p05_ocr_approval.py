"""Hash-bound, idempotent human approval for the P05 OCR Candidate batch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import (
    DS1ParsingDataset,
    OCRGold,
    P05OCRBatchApproval,
    P05OCRCandidateManifest,
)
from evaluation.contracts import (
    ApprovalRecord,
    CandidateRevisionHistory,
    ReviewLogEntry,
    ReviewStatus,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text


def approve_p05_ocr_candidate(
    *,
    dataset_root: Path,
    expected_candidate_file_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, object]:
    dataset_root = dataset_root.resolve()
    manifest_path = dataset_root / "provenance/p05_ocr_candidate_manifest.json"
    candidate_manifest = P05OCRCandidateManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    candidate_path = _safe_path(dataset_root, candidate_manifest.candidate_relative_path)
    actual_hash = sha256_file(candidate_path)
    if actual_hash != expected_candidate_file_sha256:
        raise ValueError(
            f"Candidate file Hash differs from the explicit course_owner approval: {actual_hash}"
        )
    if candidate_manifest.candidate_file_sha256 != actual_hash:
        raise ValueError("P05 Candidate Manifest does not bind the current Candidate")
    candidate = DS1ParsingDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    records = [record for record in candidate.records if isinstance(record, OCRGold)]
    if len(records) != 15 or len(candidate.records) != 15:
        raise ValueError("P05 OCR approval requires exactly 15 OCR Candidate records")
    if any(
        record.review_status is not ReviewStatus.CANDIDATE or record.approval is not None
        for record in records
    ):
        raise ValueError("P05 OCR approval accepts unapproved Candidate records only")
    candidate_hashes = {record.record_id: record_digest(record) for record in records}
    if candidate_hashes != candidate_manifest.candidate_record_sha256:
        raise ValueError("P05 OCR Candidate records differ from the Candidate Manifest")

    approved_records: list[OCRGold] = []
    approved_hashes: dict[str, str] = {}
    log_entries: list[ReviewLogEntry] = []
    for index, record in enumerate(records, start=1):
        record_review_id = f"{review_id}.{index:03d}"
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_hash = record_digest(provisional)
        values = provisional.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=record_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_hashes[record.record_id],
            approved_record_sha256=approved_hash,
            notes=notes,
        )
        approved = OCRGold.model_validate(values)
        approved_records.append(approved)
        approved_hashes[record.record_id] = approved_hash
        log_entries.append(
            ReviewLogEntry(
                review_id=record_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_hashes[record.record_id],
                resulting_record_sha256=approved_hash,
                notes=notes,
            )
        )
    approved_dataset = DS1ParsingDataset(
        dataset_id=candidate.dataset_id,
        dataset_version=candidate.dataset_version,
        records=approved_records,
    )
    approved_path = dataset_root / "approved/ds1/p05_ocr.json"
    if approved_path.exists():
        existing = DS1ParsingDataset.model_validate_json(approved_path.read_text(encoding="utf-8"))
        if existing != approved_dataset:
            raise ValueError("existing Approved P05 OCR dataset differs from this approval")
    else:
        atomic_write_json(approved_path, approved_dataset.model_dump(mode="json"))
    approved_file_hash = sha256_file(approved_path)
    batch = P05OCRBatchApproval(
        dataset_id=candidate.dataset_id,
        dataset_version=candidate.dataset_version,
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_relative_path=candidate_manifest.candidate_relative_path,
        candidate_file_sha256=actual_hash,
        candidate_record_sha256=candidate_hashes,
        approved_relative_path="datasets/courserag_eval/v1/approved/ds1/p05_ocr.json",
        approved_file_sha256=approved_file_hash,
        approved_record_sha256=approved_hashes,
        notes=notes,
    )
    batch_path = dataset_root / "provenance/p05_ocr_approval.json"
    if batch_path.exists():
        existing_batch = P05OCRBatchApproval.model_validate_json(
            batch_path.read_text(encoding="utf-8")
        )
        if existing_batch != batch:
            raise ValueError("existing P05 OCR approval differs from this event")
    else:
        atomic_write_json(batch_path, batch.model_dump(mode="json"))
    _append_review_log(dataset_root / "reviews/review_log.jsonl", log_entries)
    history_path = dataset_root / "provenance/p05_ocr_candidate_revision_history.json"
    history = CandidateRevisionHistory.model_validate_json(history_path.read_text(encoding="utf-8"))
    current_revisions = [
        revision
        for revision in history.revisions
        if revision.candidate_file_sha256 == actual_hash
        and revision.candidate_relative_path == candidate_manifest.candidate_relative_path
    ]
    if len(current_revisions) != 1 or current_revisions[0].status not in {
        "pending_course_owner_review",
        "approved",
    }:
        raise ValueError("P05 OCR revision history differs from the approved Candidate")
    if any(
        revision.status != "superseded"
        for revision in history.revisions
        if revision is not current_revisions[0]
    ):
        raise ValueError("older P05 OCR Candidate revisions must remain superseded")
    approved_history = history.model_copy(
        update={
            "revisions": [
                revision.model_copy(update={"status": "approved"})
                if revision == current_revisions[0]
                else revision
                for revision in history.revisions
            ]
        }
    )
    atomic_write_json(history_path, approved_history.model_dump(mode="json"))
    return {
        "candidate_file_sha256": actual_hash,
        "approved_file_sha256": approved_file_hash,
        "approved_record_count": 15,
        "approval_sha256": sha256_file(batch_path),
        "review_id": review_id,
    }


def _safe_path(dataset_root: Path, relative_path: str) -> Path:
    marker = "datasets/courserag_eval/v1/"
    relative = relative_path.removeprefix(marker)
    path = (dataset_root / relative).resolve()
    if not path.is_relative_to(dataset_root):
        raise ValueError("P05 approval path escapes the dataset root")
    return path


def _append_review_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline")
    existing: dict[str, ReviewLogEntry] = {}
    for line in existing_text.splitlines():
        if line.strip():
            entry = ReviewLogEntry.model_validate_json(line)
            if entry.review_id in existing:
                raise ValueError("review log contains duplicate review IDs")
            existing[entry.review_id] = entry
    appended: list[str] = []
    for addition in additions:
        current = existing.get(addition.review_id)
        if current is not None:
            if current != addition:
                raise ValueError("existing review log entry differs from approval")
            continue
        existing[addition.review_id] = addition
        appended.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(appended))


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve an exact P05 OCR Candidate batch.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-candidate-file-sha256", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_p05_ocr_candidate(
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
