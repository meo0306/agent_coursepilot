from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import CorpusDocument, DS0CorpusDataset
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _approved_document(
    candidate: CorpusDocument,
    *,
    review_id: str,
    reviewer_id: str,
    reviewed_at: datetime,
    notes: str,
) -> CorpusDocument:
    values = candidate.model_dump(mode="json")
    values["review_status"] = ReviewStatus.APPROVED
    values.pop("approval", None)
    provisional = CorpusDocument.model_construct(**values, approval=None)
    approved_record_sha256 = record_digest(provisional)
    values["approval"] = ApprovalRecord(
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=record_digest(candidate),
        approved_record_sha256=approved_record_sha256,
        notes=notes,
    )
    return CorpusDocument.model_validate(values)


def _append_reviews_idempotently(path: Path, expected: list[ReviewLogEntry]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline before appending")
    existing: dict[str, ReviewLogEntry] = {}
    for line_number, line in enumerate(existing_text.splitlines(), start=1):
        if not line.strip():
            continue
        entry = ReviewLogEntry.model_validate_json(line)
        if entry.review_id in existing:
            raise ValueError(f"duplicate review_id in existing log at line {line_number}")
        existing[entry.review_id] = entry

    additions: list[str] = []
    for entry in expected:
        current = existing.get(entry.review_id)
        if current is not None:
            if current != entry:
                raise ValueError(f"existing review differs for {entry.review_id}")
            continue
        additions.append(entry.model_dump_json() + "\n")
    if additions:
        atomic_write_text(path, existing_text + "".join(additions))


def approve_ds0_batch(
    *,
    dataset_root: Path,
    expected_candidate_file_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    batch_review_id: str,
    notes: str,
) -> dict[str, object]:
    candidate_path = dataset_root / "candidates" / "ds0" / "pilot.json"
    approved_path = dataset_root / "approved" / "ds0" / "pilot.json"
    review_log_path = dataset_root / "reviews" / "review_log.jsonl"
    manifest_path = dataset_root / "manifest.json"

    actual_candidate_file_sha256 = sha256_file(candidate_path)
    if actual_candidate_file_sha256 != expected_candidate_file_sha256:
        raise ValueError(
            "candidate file hash differs from the explicitly approved batch: "
            f"{actual_candidate_file_sha256}"
        )
    candidates = DS0CorpusDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    if not candidates.documents:
        raise ValueError("DS0 approval batch cannot be empty")
    for candidate in candidates.documents:
        if candidate.review_status is not ReviewStatus.CANDIDATE or candidate.approval is not None:
            raise ValueError(f"record is not an unapproved candidate: {candidate.record_id}")

    approved_documents: list[CorpusDocument] = []
    reviews: list[ReviewLogEntry] = []
    for index, candidate in enumerate(candidates.documents, start=1):
        review_id = f"{batch_review_id}-{index:02d}"
        approved = _approved_document(
            candidate,
            review_id=review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            notes=notes,
        )
        approval = approved.approval
        if approval is None:  # pragma: no cover - guarded by CorpusDocument validation
            raise AssertionError("approved document is missing approval metadata")
        approved_documents.append(approved)
        reviews.append(
            ReviewLogEntry(
                review_id=review_id,
                record_id=approved.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=approval.candidate_sha256,
                resulting_record_sha256=approval.approved_record_sha256,
                notes=notes,
            )
        )

    approved_envelope = DS0CorpusDataset(
        dataset_id=candidates.dataset_id,
        dataset_version=candidates.dataset_version,
        documents=approved_documents,
    )
    expected_payload = approved_envelope.model_dump(mode="json")
    if approved_path.exists():
        current = DS0CorpusDataset.model_validate_json(approved_path.read_text(encoding="utf-8"))
        if current != approved_envelope:
            raise ValueError("existing Approved DS0 batch differs from this approval event")
    else:
        atomic_write_json(approved_path, expected_payload)

    _append_reviews_idempotently(review_log_path, reviews)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    current_status = manifest.get("gold_status")
    allowed_statuses = {"ds0_candidates_pending_owner_review", "ds0_pilot_approved"}
    if current_status not in allowed_statuses:
        raise ValueError(f"unexpected dataset gold_status: {current_status!r}")
    if current_status != "ds0_pilot_approved":
        manifest["gold_status"] = "ds0_pilot_approved"
        atomic_write_json(manifest_path, manifest)

    return {
        "approved_count": len(approved_documents),
        "approved_file_sha256": sha256_file(approved_path),
        "candidate_file_sha256": actual_candidate_file_sha256,
        "review_ids": [review.review_id for review in reviews],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve an exact DS0 candidate batch.")
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path("datasets/courserag_eval/v1"),
    )
    parser.add_argument("--expected-candidate-file-sha256", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--batch-review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_ds0_batch(
        dataset_root=args.dataset_root,
        expected_candidate_file_sha256=args.expected_candidate_file_sha256,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        batch_review_id=args.batch_review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
