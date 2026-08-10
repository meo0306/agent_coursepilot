from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.evals.schemas import CorpusDocument, DS0CorpusDataset
from evaluation.ds0_approval import approve_ds0_batch, sha256_file


def _write_candidate_layout(root: Path) -> Path:
    candidate = CorpusDocument(
        record_id="ds0-doc-1",
        document_id="doc-1",
        filename="source.pdf",
        mime_type="application/pdf",
        sha256="a" * 64,
        document_version="eval-v1-aaaaaaaaaaaaaaaa",
    )
    envelope = DS0CorpusDataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        documents=[candidate],
    )
    candidate_path = root / "candidates" / "ds0" / "pilot.json"
    candidate_path.parent.mkdir(parents=True)
    candidate_path.write_text(
        json.dumps(envelope.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (root / "approved" / "ds0").mkdir(parents=True)
    (root / "reviews").mkdir()
    (root / "reviews" / "review_log.jsonl").write_text("", encoding="utf-8")
    (root / "manifest.json").write_text(
        json.dumps({"gold_status": "ds0_candidates_pending_owner_review"}) + "\n",
        encoding="utf-8",
    )
    return candidate_path


def test_ds0_batch_approval_is_hash_bound_and_idempotent(tmp_path: Path) -> None:
    candidate_path = _write_candidate_layout(tmp_path)
    arguments = {
        "dataset_root": tmp_path,
        "expected_candidate_file_sha256": sha256_file(candidate_path),
        "reviewer_id": "course_owner",
        "reviewed_at": datetime(2026, 7, 29, tzinfo=UTC),
        "batch_review_id": "review-pre-p03-ds0-20260729-01",
        "notes": "Explicit batch approval.",
    }

    first = approve_ds0_batch(**arguments)
    second = approve_ds0_batch(**arguments)

    assert first == second
    approved = DS0CorpusDataset.model_validate_json(
        (tmp_path / "approved" / "ds0" / "pilot.json").read_text(encoding="utf-8")
    )
    assert approved.documents[0].review_status.value == "approved"
    assert approved.documents[0].approval is not None
    review_lines = (
        (tmp_path / "reviews" / "review_log.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(review_lines) == 1
    assert (
        json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))["gold_status"]
        == "ds0_pilot_approved"
    )


def test_ds0_batch_approval_rejects_unapproved_hash(tmp_path: Path) -> None:
    _write_candidate_layout(tmp_path)
    with pytest.raises(ValueError, match="explicitly approved batch"):
        approve_ds0_batch(
            dataset_root=tmp_path,
            expected_candidate_file_sha256="b" * 64,
            reviewer_id="course_owner",
            reviewed_at=datetime(2026, 7, 29, tzinfo=UTC),
            batch_review_id="review-pre-p03-ds0-20260729-01",
            notes="Explicit batch approval.",
        )
