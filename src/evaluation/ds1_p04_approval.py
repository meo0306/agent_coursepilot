"""Hash-bound human approval for the formal P04 DS1 Candidate batch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import (
    DS1BatchApproval,
    DS1CandidateManifest,
    DS1ParsingDataset,
    ParsingGoldRecord,
)
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text


def _safe_dataset_path(dataset_root: Path, relative_path: str) -> Path:
    root = dataset_root.resolve()
    path = (root / relative_path).resolve()
    if not path.is_relative_to(root):
        raise ValueError("DS1 approval path escapes the dataset root")
    return path


def _updated_review_log(path: Path, additions: list[ReviewLogEntry]) -> str:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline")
    entries: dict[str, ReviewLogEntry] = {}
    for line_number, line in enumerate(existing_text.splitlines(), start=1):
        if not line.strip():
            continue
        entry = ReviewLogEntry.model_validate_json(line)
        if entry.review_id in entries:
            raise ValueError(f"duplicate review_id in existing log at line {line_number}")
        entries[entry.review_id] = entry
    appended: list[str] = []
    for addition in additions:
        current = entries.get(addition.review_id)
        if current is not None:
            if current != addition:
                raise ValueError(f"existing review differs for {addition.review_id}")
            continue
        entries[addition.review_id] = addition
        appended.append(addition.model_dump_json())
    return existing_text + "".join(line + "\n" for line in appended)


def approve_ds1_p04_candidate(
    *,
    dataset_root: Path,
    expected_candidate_file_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, object]:
    dataset_root = dataset_root.resolve()
    provenance_path = dataset_root / "provenance/ds1_p04_candidate_manifest.json"
    manifest_path = dataset_root / "manifest.json"
    review_log_path = dataset_root / "reviews/review_log.jsonl"
    test_lock_path = dataset_root / "test.lock.json"
    candidate_manifest = DS1CandidateManifest.model_validate_json(
        provenance_path.read_text(encoding="utf-8")
    )
    marker = "datasets/courserag_eval/v1/"
    relative = candidate_manifest.candidate_relative_path
    relative = relative.removeprefix(marker)
    candidate_path = _safe_dataset_path(dataset_root, relative)
    actual_candidate_sha256 = sha256_file(candidate_path)
    if actual_candidate_sha256 != expected_candidate_file_sha256:
        raise ValueError(
            "Candidate file Hash differs from the explicit course_owner approval: "
            f"{actual_candidate_sha256}"
        )
    if candidate_manifest.candidate_file_sha256 != actual_candidate_sha256:
        raise ValueError("Candidate provenance Manifest does not bind the current Candidate")
    candidate = DS1ParsingDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    expected_counts = {
        "page": 15,
        "docx_pagination": 10,
        "section": 20,
        "table": 10,
        "ocr": 0,
    }
    actual_counts = {
        name: sum(record.record_type == name for record in candidate.records)
        for name in expected_counts
    }
    if actual_counts != expected_counts:
        raise ValueError(f"formal P04 DS1 Candidate has unexpected counts: {actual_counts}")
    if any(
        record.review_status is not ReviewStatus.CANDIDATE or record.approval is not None
        for record in candidate.records
    ):
        raise ValueError("DS1 batch approval accepts unapproved Candidate records only")
    current_record_hashes = {
        record.record_id: record_digest(record) for record in candidate.records
    }
    if current_record_hashes != candidate_manifest.candidate_record_sha256:
        raise ValueError("DS1 Candidate record Hashes differ from the provenance Manifest")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("gold_status") not in {
        "ds0_pilot_approved",
        "ds1_p04_native_docx_approved",
    }:
        raise ValueError("unexpected Gold status before P04 DS1 approval")
    phase_status = manifest.setdefault("phase_input_status", {})
    if phase_status.get("p04") not in {
        "approved_for_annotation",
        "formal_eval_ready",
    }:
        raise ValueError("unexpected P04 input status before DS1 approval")
    for split_name in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split_name).read_text(encoding="utf-8").strip():
            raise ValueError("P04 DS1 approval must not populate Dev/Test")
    lock = TestLock.model_validate_json(test_lock_path.read_text(encoding="utf-8"))
    if lock.locked:
        raise ValueError("P04 DS1 approval must not lock Test")

    approved_records: list[ParsingGoldRecord] = []
    review_entries: list[ReviewLogEntry] = []
    approved_record_hashes: dict[str, str] = {}
    for index, record in enumerate(candidate.records, start=1):
        record_review_id = f"{review_id}.{index:03d}"
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_record_sha256 = record_digest(provisional)
        values = provisional.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=record_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=current_record_hashes[record.record_id],
            approved_record_sha256=approved_record_sha256,
            notes=notes,
        )
        approved_record = type(record).model_validate(values)
        approved_records.append(approved_record)
        approved_record_hashes[record.record_id] = approved_record_sha256
        review_entries.append(
            ReviewLogEntry(
                review_id=record_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=current_record_hashes[record.record_id],
                resulting_record_sha256=approved_record_sha256,
                notes=notes,
            )
        )
    approved = DS1ParsingDataset(
        dataset_id=candidate.dataset_id,
        dataset_version=candidate.dataset_version,
        records=approved_records,
    )
    approved_path = dataset_root / "approved/ds1/p04_native_docx.json"
    if approved_path.exists():
        current = DS1ParsingDataset.model_validate_json(approved_path.read_text(encoding="utf-8"))
        if current != approved:
            raise ValueError("existing Approved P04 DS1 differs from this approval event")
    else:
        atomic_write_json(approved_path, approved.model_dump(mode="json"))
    approved_file_sha256 = sha256_file(approved_path)
    batch = DS1BatchApproval(
        dataset_id="courserag-eval",
        dataset_version="v1",
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_relative_path=candidate_manifest.candidate_relative_path,
        candidate_file_sha256=actual_candidate_sha256,
        candidate_record_sha256=current_record_hashes,
        approved_relative_path="datasets/courserag_eval/v1/approved/ds1/p04_native_docx.json",
        approved_file_sha256=approved_file_sha256,
        approved_record_sha256=approved_record_hashes,
        notes=notes,
    )
    batch_path = dataset_root / "provenance/ds1_p04_approval.json"
    if batch_path.exists():
        current_batch = DS1BatchApproval.model_validate_json(batch_path.read_text(encoding="utf-8"))
        if current_batch != batch:
            raise ValueError("existing DS1 batch approval differs from this event")
    else:
        atomic_write_json(batch_path, batch.model_dump(mode="json"))
    updated_log = _updated_review_log(review_log_path, review_entries)
    atomic_write_text(review_log_path, updated_log)

    manifest["gold_status"] = "ds1_p04_native_docx_approved"
    phase_status["p04"] = "formal_eval_ready"
    atomic_write_json(manifest_path, manifest)
    return {
        "candidate_file_sha256": actual_candidate_sha256,
        "approved_file_sha256": approved_file_sha256,
        "approved_record_count": len(approved.records),
        "batch_approval_sha256": sha256_file(batch_path),
        "review_id": review_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve an exact formal P04 DS1 Candidate batch.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-candidate-file-sha256", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_ds1_p04_candidate(
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
