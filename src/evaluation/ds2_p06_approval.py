"""Promote one exact, fully reviewed formal DS2 Candidate batch."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import (
    DS2BatchApproval,
    DS2CandidateManifest,
    DS2EvidenceDataset,
    DS2ReviewDecisions,
    EvidenceRecord,
)
from evaluation.contracts import (
    ApprovalRecord,
    CandidateRevisionHistory,
    HashedArtifact,
    ReviewLogEntry,
    ReviewStatus,
    TestLock,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text


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
                raise ValueError("existing review log entry differs from DS2 approval")
            continue
        existing[addition.review_id] = addition
        appended.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(appended))


def _artifact(dataset_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    root = dataset_root.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(root):
        raise ValueError("DS2 review decisions must stay under the dataset root")
    repository_root = root.parent.parent.parent
    return HashedArtifact(
        path=resolved.relative_to(repository_root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def approve_ds2_candidate(
    *,
    dataset_root: Path,
    expected_candidate_file_sha256: str,
    review_decisions_path: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, object]:
    dataset_root = dataset_root.resolve()
    candidate_manifest_path = dataset_root / "provenance/ds2_p06_candidate_manifest.json"
    candidate_manifest = DS2CandidateManifest.model_validate_json(
        candidate_manifest_path.read_text(encoding="utf-8")
    )
    candidate_path = dataset_root.parent.parent.parent / candidate_manifest.candidate_relative_path
    candidate_path = candidate_path.resolve()
    if not candidate_path.is_relative_to(dataset_root):
        raise ValueError("DS2 Candidate path escapes dataset root")
    actual_candidate_hash = sha256_file(candidate_path)
    if actual_candidate_hash != expected_candidate_file_sha256:
        raise ValueError("literal DS2 Candidate SHA-256 does not match")
    if actual_candidate_hash != candidate_manifest.candidate_file_sha256:
        raise ValueError("DS2 Candidate differs from its Manifest")
    candidate = DS2EvidenceDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    if len(candidate.evidence) != 120:
        raise ValueError("formal DS2 approval requires exactly 120 Candidate records")
    if any(record.review_status is not ReviewStatus.CANDIDATE for record in candidate.evidence):
        raise ValueError("formal DS2 approval accepts Candidate records only")
    candidate_hashes = {record.record_id: record_digest(record) for record in candidate.evidence}
    if candidate_hashes != candidate_manifest.candidate_record_sha256:
        raise ValueError("DS2 Candidate record Hashes differ from its Manifest")

    decisions_path = review_decisions_path.resolve()
    decisions = DS2ReviewDecisions.model_validate_json(decisions_path.read_text(encoding="utf-8"))
    record_ids = set(candidate_hashes)
    if decisions.candidate_file_sha256 != actual_candidate_hash:
        raise ValueError("DS2 review decisions target a different Candidate")
    if decisions.returned_record_ids:
        raise ValueError("returned DS2 records require a new Candidate revision")
    if set(decisions.reviewed_record_ids) != record_ids:
        raise ValueError("all 120 DS2 records must be reviewed before approval")
    if set(decisions.completed_group_ids) != {"group-01", "group-02", "group-03", "group-04"}:
        raise ValueError("all four DS2 review groups must be complete")

    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("formal DS2 Pilot approval cannot alter a locked Test dataset")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("formal DS2 Pilot approval requires empty Dev/Test splits")

    approved_records: list[EvidenceRecord] = []
    approved_hashes: dict[str, str] = {}
    log_entries: list[ReviewLogEntry] = []
    for index, record in enumerate(candidate.evidence, start=1):
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
        approved = EvidenceRecord.model_validate(values)
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
    approved_dataset = DS2EvidenceDataset(
        dataset_id=candidate.dataset_id,
        dataset_version=candidate.dataset_version,
        evidence=approved_records,
    )
    approved_path = dataset_root / "approved/ds2/p06_evidence.json"
    if approved_path.exists():
        existing = DS2EvidenceDataset.model_validate_json(approved_path.read_text(encoding="utf-8"))
        if existing != approved_dataset:
            raise ValueError("existing Approved DS2 differs from this approval")
    else:
        atomic_write_json(approved_path, approved_dataset.model_dump(mode="json"))
    approved_hash = sha256_file(approved_path)
    decisions_artifact = _artifact(dataset_root, decisions_path)
    batch = DS2BatchApproval(
        dataset_id=candidate.dataset_id,
        dataset_version=candidate.dataset_version,
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_relative_path=candidate_manifest.candidate_relative_path,
        candidate_file_sha256=actual_candidate_hash,
        candidate_record_sha256=candidate_hashes,
        review_decisions_artifact=decisions_artifact,
        approved_relative_path=approved_path.relative_to(
            dataset_root.parent.parent.parent
        ).as_posix(),
        approved_file_sha256=approved_hash,
        approved_record_sha256=approved_hashes,
        notes=notes,
    )
    batch_path = dataset_root / "provenance/ds2_p06_approval.json"
    if batch_path.exists():
        existing_batch = DS2BatchApproval.model_validate_json(
            batch_path.read_text(encoding="utf-8")
        )
        if existing_batch != batch:
            raise ValueError("existing DS2 batch approval differs from this event")
    else:
        atomic_write_json(batch_path, batch.model_dump(mode="json"))
    _append_review_log(dataset_root / "reviews/review_log.jsonl", log_entries)

    history_path = dataset_root / "provenance/ds2_p06_candidate_revision_history.json"
    history = CandidateRevisionHistory.model_validate_json(history_path.read_text(encoding="utf-8"))
    current = [
        entry for entry in history.revisions if entry.candidate_file_sha256 == actual_candidate_hash
    ]
    if len(current) != 1 or current[0].status not in {"pending_course_owner_review", "approved"}:
        raise ValueError("DS2 Candidate revision history differs from the approved Candidate")
    approved_history = history.model_copy(
        update={
            "revisions": [
                entry.model_copy(update={"status": "approved"}) if entry == current[0] else entry
                for entry in history.revisions
            ]
        }
    )
    atomic_write_json(history_path, approved_history.model_dump(mode="json"))

    manifest_path = dataset_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    components = manifest.setdefault("gold_components", {})
    components.update(
        {
            "ds0": "approved",
            "ds1_native_docx": "approved",
            "ds1_ocr": "approved",
            "ds2": "approved",
        }
    )
    manifest["gold_status"] = "ds2_p06_evidence_approved"
    manifest.setdefault("phase_input_status", {})["p05"] = "completed_gate_passed"
    manifest["phase_input_status"]["p06"] = "formal_eval_ready"
    atomic_write_json(manifest_path, manifest)
    return {
        "candidate_file_sha256": actual_candidate_hash,
        "approved_file_sha256": approved_hash,
        "approved_record_count": 120,
        "approval_sha256": sha256_file(batch_path),
        "review_id": review_id,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Approve an exact, fully reviewed DS2 Candidate.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-candidate-file-sha256", required=True)
    parser.add_argument("--review-decisions", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_ds2_candidate(
        dataset_root=args.dataset_root,
        expected_candidate_file_sha256=args.expected_candidate_file_sha256,
        review_decisions_path=args.review_decisions,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
