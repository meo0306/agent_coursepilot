import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.evals.schemas import CorpusDocument, DS0CorpusDataset
from evaluation.contracts import (
    ApprovalRecord,
    CandidateRevisionArtifact,
    CandidateRevisionHistory,
    ReviewLogEntry,
    ReviewStatus,
)
from evaluation.datasets import (
    COURSEPILOT_SPECS,
    COURSERAG_SPECS,
    DatasetValidationError,
    canonical_json_bytes,
    load_dataset_inventory,
    record_digest,
)

HASH_A = "a" * 64


def _write_layout(root: Path, candidate: CorpusDocument, approved: CorpusDocument | None = None):
    for status in ("candidates", "approved"):
        for spec in COURSERAG_SPECS:
            (root / status / spec.directory_name).mkdir(parents=True, exist_ok=True)
    (root / "reviews").mkdir()
    (root / "splits").mkdir()
    envelope = DS0CorpusDataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        documents=[candidate],
    )
    (root / "candidates" / "ds0" / "pilot.json").write_text(
        envelope.model_dump_json(indent=2),
        encoding="utf-8",
    )
    review_lines = ""
    if approved is not None:
        approved_envelope = DS0CorpusDataset(
            dataset_id="courserag-eval",
            dataset_version="v1",
            documents=[approved],
        )
        (root / "approved" / "ds0" / "approved.json").write_text(
            approved_envelope.model_dump_json(indent=2),
            encoding="utf-8",
        )
        approval = approved.approval
        assert approval is not None
        review_lines = (
            ReviewLogEntry(
                review_id=approval.review_id,
                record_id=approved.record_id,
                action="approve",
                reviewer_id=approval.reviewer_id,
                reviewed_at=approval.reviewed_at,
                candidate_sha256=approval.candidate_sha256,
                resulting_record_sha256=approval.approved_record_sha256,
            ).model_dump_json()
            + "\n"
        )
    (root / "reviews" / "review_log.jsonl").write_text(review_lines, encoding="utf-8")
    for split in ("pilot", "dev", "test"):
        (root / "splits" / f"{split}_ids.txt").write_text("", encoding="utf-8")


def _candidate() -> CorpusDocument:
    return CorpusDocument(
        record_id="doc-record-1",
        document_id="doc-1",
        filename="sample.pdf",
        mime_type="application/pdf",
        sha256=HASH_A,
        document_version="v1",
        review_status="candidate",
    )


def _approved(candidate: CorpusDocument) -> CorpusDocument:
    values = candidate.model_dump()
    values["review_status"] = ReviewStatus.APPROVED
    values.pop("approval", None)
    provisional = CorpusDocument.model_construct(**values, approval=None)
    approved_hash = record_digest(provisional)
    values["approval"] = ApprovalRecord(
        review_id="review-1",
        reviewer_id="human-1",
        reviewed_at=datetime(2026, 7, 23, tzinfo=UTC),
        candidate_sha256=record_digest(candidate),
        approved_record_sha256=approved_hash,
    )
    return CorpusDocument.model_validate(values)


def test_candidate_and_approved_are_hash_linked_and_dev_is_approved_only(tmp_path):
    candidate = _candidate()
    approved = _approved(candidate)
    _write_layout(tmp_path, candidate, approved)
    (tmp_path / "splits" / "dev_ids.txt").write_text("doc-record-1\n", encoding="utf-8")

    inventory = load_dataset_inventory(tmp_path, COURSERAG_SPECS)

    assert inventory.candidate_records["doc-record-1"].review_status.value == "candidate"
    assert inventory.approved_records["doc-record-1"].review_status.value == "approved"


def test_dev_rejects_candidate_and_split_ids_cannot_overlap(tmp_path):
    candidate = _candidate()
    _write_layout(tmp_path, candidate)
    (tmp_path / "splits" / "dev_ids.txt").write_text("doc-record-1\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="non-approved"):
        load_dataset_inventory(tmp_path, COURSERAG_SPECS)

    (tmp_path / "splits" / "dev_ids.txt").write_text("", encoding="utf-8")
    (tmp_path / "splits" / "pilot_ids.txt").write_text("doc-record-1\n", encoding="utf-8")
    (tmp_path / "splits" / "test_ids.txt").write_text("doc-record-1\n", encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="both pilot and test"):
        load_dataset_inventory(tmp_path, COURSERAG_SPECS)


def test_approved_record_requires_retained_candidate_and_matching_review(tmp_path):
    candidate = _candidate()
    approved = _approved(candidate)
    _write_layout(tmp_path, candidate, approved)
    (tmp_path / "candidates" / "ds0" / "pilot.json").unlink()

    with pytest.raises(DatasetValidationError, match="no retained candidate"):
        load_dataset_inventory(tmp_path, COURSERAG_SPECS)


def test_canonical_json_bytes_are_stable():
    left = canonical_json_bytes({"b": 2, "a": 1})
    right = canonical_json_bytes({"a": 1, "b": 2})

    assert left == right
    assert json.loads(left) == {"a": 1, "b": 2}


def test_superseded_candidate_revisions_are_hash_checked_and_excluded(tmp_path):
    candidate = _candidate()
    _write_layout(tmp_path, candidate)
    current_path = tmp_path / "candidates/ds0/pilot.json"
    superseded_path = tmp_path / "candidates/ds0/pilot_r1.json"
    superseded_path.write_bytes(current_path.read_bytes())
    (tmp_path / "provenance").mkdir()
    history = CandidateRevisionHistory(
        dataset_id="courserag-eval",
        dataset_version="v1",
        revisions=[
            CandidateRevisionArtifact(
                revision=1,
                candidate_relative_path="candidates/ds0/pilot_r1.json",
                candidate_file_sha256=hashlib.sha256(superseded_path.read_bytes()).hexdigest(),
                status="superseded",
                reason="test superseded revision",
            ),
            CandidateRevisionArtifact(
                revision=2,
                candidate_relative_path="candidates/ds0/pilot.json",
                candidate_file_sha256=hashlib.sha256(current_path.read_bytes()).hexdigest(),
                status="pending_course_owner_review",
                reason="test current revision",
            ),
        ],
    )
    history_path = tmp_path / "provenance/test_candidate_revision_history.json"
    history_path.write_text(history.model_dump_json(indent=2), encoding="utf-8")

    inventory = load_dataset_inventory(tmp_path, COURSERAG_SPECS)
    assert set(inventory.candidate_records) == {"doc-record-1"}

    tampered = history.model_copy(deep=True)
    tampered.revisions[0].candidate_file_sha256 = "b" * 64
    history_path.write_text(tampered.model_dump_json(indent=2), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="revision Hash mismatch"):
        load_dataset_inventory(tmp_path, COURSERAG_SPECS)


def test_repository_pilot_layouts_validate():
    courserag = load_dataset_inventory(
        Path("datasets/courserag_eval/v1"),
        COURSERAG_SPECS,
    )
    coursepilot = load_dataset_inventory(
        Path("datasets/coursepilot_eval/v1"),
        COURSEPILOT_SPECS,
    )

    assert set(courserag.split_ids[next(iter(courserag.split_ids))])
    assert "cp-ds1-synthetic-lesson" in coursepilot.candidate_records
    assert len(coursepilot.approved_records) == 24
    assert all(record_id.startswith("p12-") for record_id in coursepilot.approved_records)
