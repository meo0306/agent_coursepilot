from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.evals.schemas import DS1CandidateManifest, DS1ParsingDataset, DS1ReviewDecisions
from evaluation.contracts import ReviewStatus
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.ds1_p04_approval import approve_ds1_p04_candidate

CANDIDATE_SHA256 = "7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa"
CANDIDATE_PATH = Path("datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r6.json")
PREDECESSOR_SHA256 = "8fd5fbefbcbe40c90f65c35cd3e0166cb6d62800e4927e4ed7c6cb1c661973cb"
PREDECESSOR_PATH = Path("datasets/courserag_eval/v1/candidates/ds1/p04_native_docx_r4.json")
REVIEW_DECISIONS_PATH = Path("datasets/courserag_eval/v1/reviews/ds1_p04_review_decisions_r4.json")
REVIEW_SOURCE_SHA256 = "acaba867ed1377ce71eca915e713ecf97933b3768269194d85f008d7f26cf895"
PROVENANCE_PATH = Path("datasets/courserag_eval/v1/provenance/ds1_p04_candidate_manifest.json")


def test_tracked_p04_ds1_candidate_is_hash_bound_and_physically_separate_from_approved():
    candidate = DS1ParsingDataset.model_validate_json(CANDIDATE_PATH.read_text(encoding="utf-8"))
    manifest = DS1CandidateManifest.model_validate_json(PROVENANCE_PATH.read_text(encoding="utf-8"))

    counts = {
        record_type: sum(record.record_type == record_type for record in candidate.records)
        for record_type in ("page", "docx_pagination", "section", "table", "ocr")
    }
    assert counts == {"page": 15, "docx_pagination": 10, "section": 20, "table": 10, "ocr": 0}
    assert sha256_file(CANDIDATE_PATH) == CANDIDATE_SHA256
    assert manifest.candidate_file_sha256 == CANDIDATE_SHA256
    assert manifest.record_counts == counts
    assert manifest.semantic_source_count == 2
    assert len(manifest.second_review_record_ids) == 15
    assert manifest.predecessor_candidate_file_sha256 == PREDECESSOR_SHA256
    assert manifest.review_decisions_artifact is not None
    assert manifest.review_decisions_artifact.path == REVIEW_DECISIONS_PATH.as_posix()
    assert manifest.review_decisions_source_sha256 == REVIEW_SOURCE_SHA256
    assert manifest.required_rereview_record_ids == ["ds1-table-docx-020"]
    assert manifest.candidate_record_sha256 == {
        record.record_id: record_digest(record) for record in candidate.records
    }
    assert all(record.review_status is ReviewStatus.CANDIDATE for record in candidate.records)
    assert all(record.approval is None for record in candidate.records)
    approved_path = Path("datasets/courserag_eval/v1/approved/ds1/p04_native_docx.json")
    approved = DS1ParsingDataset.model_validate_json(approved_path.read_text(encoding="utf-8"))
    assert sha256_file(approved_path) == (
        "7e12edb2b66912d915b1d1ca3b7df873edb910cb7dcaf57d07872c83d84964ea"
    )
    assert len(approved.records) == 55
    assert all(record.review_status is ReviewStatus.APPROVED for record in approved.records)
    assert all(record.approval is not None for record in approved.records)


def test_r6_preserves_all_reviewed_records_and_changes_only_returned_table_020():
    predecessor = DS1ParsingDataset.model_validate_json(
        PREDECESSOR_PATH.read_text(encoding="utf-8")
    )
    candidate = DS1ParsingDataset.model_validate_json(CANDIDATE_PATH.read_text(encoding="utf-8"))
    decisions = DS1ReviewDecisions.model_validate_json(
        REVIEW_DECISIONS_PATH.read_text(encoding="utf-8")
    )
    predecessor_hashes = {record.record_id: record_digest(record) for record in predecessor.records}
    candidate_hashes = {record.record_id: record_digest(record) for record in candidate.records}

    assert sha256_file(PREDECESSOR_PATH) == PREDECESSOR_SHA256
    assert decisions.candidate_file_sha256 == PREDECESSOR_SHA256
    assert len(decisions.reviewed_record_ids) == 54
    assert decisions.returned_record_ids == ["ds1-table-docx-020"]
    assert set(decisions.reviewed_record_ids) == set(predecessor_hashes) - {"ds1-table-docx-020"}
    assert [
        record_id
        for record_id in predecessor_hashes
        if predecessor_hashes[record_id] != candidate_hashes[record_id]
    ] == ["ds1-table-docx-020"]


def test_tracked_page_and_table_annotations_obey_formal_ds1_geometry_contracts():
    candidate = DS1ParsingDataset.model_validate_json(CANDIDATE_PATH.read_text(encoding="utf-8"))

    pages = [record for record in candidate.records if record.record_type == "page"]
    assert {record.page_number for record in pages} == {
        5,
        10,
        11,
        12,
        15,
        18,
        20,
        21,
        23,
        24,
        26,
        27,
        30,
        31,
        32,
    }
    for page in pages:
        assert page.needs_ocr is False
        assert page.bbox_coordinate_space == "pdf_points_top_left"
        assert page.page_width is not None
        assert page.page_height is not None
        assert page.reading_order == [
            region.region_id
            for region in sorted(page.regions, key=lambda region: region.order_index or 0)
        ]
        for region in [*page.regions, *page.noise_regions]:
            assert region.bbox is not None
            x0, y0, x1, y1 = region.bbox
            assert 0 <= x0 < x1 <= page.page_width
            assert 0 <= y0 < y1 <= page.page_height

    tables = [record for record in candidate.records if record.record_type == "table"]
    for table in tables:
        assert len(table.cells) == table.row_count
        assert all(len(row) == table.column_count for row in table.cells)

    split_table = next(table for table in tables if table.record_id == "ds1-table-docx-020")
    assert split_table.source_span.page_start == 547
    assert split_table.source_span.page_end == 548
    assert split_table.row_count == 7
    assert split_table.column_count == 4
    assert split_table.cells[:2] == [
        ["种类", "中型卡车", "小轿车", "人员"],
        ["距离", "6.8m*2.7m", "4.3m*1.5m", "1.7m*0.5m"],
    ]
    assert [fragment.physical_page_index for fragment in split_table.rendered_page_fragments] == [
        547,
        548,
    ]
    assert split_table.rendered_page_fragments[0].continuation_to_next_page is True
    assert split_table.rendered_page_fragments[1].continuation_from_previous_page is True
    assert split_table.rendered_page_fragments[0].row_indices == [0]
    assert split_table.rendered_page_fragments[1].row_indices == [1, 2, 3, 4, 5, 6]


def test_tracked_docx_pagination_is_bound_to_reproducible_renderer_snapshots():
    candidate = DS1ParsingDataset.model_validate_json(CANDIDATE_PATH.read_text(encoding="utf-8"))
    manifest = DS1CandidateManifest.model_validate_json(PROVENANCE_PATH.read_text(encoding="utf-8"))
    pagination = {
        (record.document_id, record.paragraph_index): record
        for record in candidate.records
        if record.record_type == "docx_pagination"
    }

    assert {key: record.expected_physical_page_index for key, record in pagination.items()} == {
        ("doc_ai_algorithms_systems", 19): 6,
        ("doc_ai_algorithms_systems", 144): 44,
        ("doc_ai_algorithms_systems", 1034): 145,
        ("doc_ai_algorithms_systems", 1614): 251,
        ("doc_ai_algorithms_systems", 3782): 618,
        ("doc_ai_algorithms_systems_structure_stress", 19): 1,
        ("doc_ai_algorithms_systems_structure_stress", 144): 8,
        ("doc_ai_algorithms_systems_structure_stress", 1034): 33,
        ("doc_ai_algorithms_systems_structure_stress", 1614): 51,
        ("doc_ai_algorithms_systems_structure_stress", 3782): 124,
    }
    assert manifest.canonical_rendered_pdf_sha256 == {
        "doc_ai_algorithms_systems": (
            "4642e5c653b265b71bdbf9878218ca058188a9420b8b5930317cf4442c09fb95"
        ),
        "doc_ai_algorithms_systems_structure_stress": (
            "68c178e0ecb7ef615564bbef92c068037dba20ca600e418e53300b5a92cf570c"
        ),
    }
    for record in pagination.values():
        assert record.rendered_pdf_hash_basis == "canonical_pdf_without_volatile_metadata"
        assert record.source_text is not None
        assert (
            record.source_text_sha256
            == hashlib.sha256(record.source_text.encode("utf-8")).hexdigest()
        )


def _copy_approval_fixture(tmp_path: Path) -> Path:
    dataset_root = tmp_path / "v1"
    candidate_target = dataset_root / "candidates/ds1/p04_native_docx_r6.json"
    provenance_target = dataset_root / "provenance/ds1_p04_candidate_manifest.json"
    candidate_target.parent.mkdir(parents=True)
    provenance_target.parent.mkdir(parents=True)
    (dataset_root / "approved/ds1").mkdir(parents=True)
    (dataset_root / "reviews").mkdir(parents=True)
    (dataset_root / "splits").mkdir(parents=True)
    shutil.copyfile(CANDIDATE_PATH, candidate_target)
    shutil.copyfile(PROVENANCE_PATH, provenance_target)
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "courserag-eval",
                "dataset_version": "v1",
                "gold_status": "ds0_pilot_approved",
                "phase_input_status": {"p04": "approved_for_annotation"},
            }
        ),
        encoding="utf-8",
    )
    (dataset_root / "reviews/review_log.jsonl").write_text("", encoding="utf-8")
    (dataset_root / "splits/dev_ids.txt").write_text("\n", encoding="utf-8")
    (dataset_root / "splits/test_ids.txt").write_text("\n", encoding="utf-8")
    (dataset_root / "test.lock.json").write_text(
        json.dumps(
            {
                "schema_version": "course-eval.test-lock.v1",
                "dataset_id": "courserag-eval",
                "dataset_version": "v1",
                "locked": False,
                "test_ids_sha256": None,
                "approved_manifest_sha256": None,
                "locked_at": None,
                "locked_by": None,
            }
        ),
        encoding="utf-8",
    )
    return dataset_root


def test_ds1_approval_rejects_a_nonmatching_explicit_candidate_hash(tmp_path: Path):
    dataset_root = _copy_approval_fixture(tmp_path)

    with pytest.raises(ValueError, match="explicit course_owner approval"):
        approve_ds1_p04_candidate(
            dataset_root=dataset_root,
            expected_candidate_file_sha256="0" * 64,
            reviewer_id="course_owner",
            reviewed_at=datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
            review_id="review-ds1-p04-test",
            notes="test-only approval event",
        )

    assert not (dataset_root / "approved/ds1/p04_native_docx.json").exists()
    assert not (dataset_root / "provenance/ds1_p04_approval.json").exists()


def test_ds1_exact_hash_approval_is_complete_and_idempotent_in_an_isolated_copy(
    tmp_path: Path,
):
    dataset_root = _copy_approval_fixture(tmp_path)
    kwargs = {
        "dataset_root": dataset_root,
        "expected_candidate_file_sha256": CANDIDATE_SHA256,
        "reviewer_id": "course_owner",
        "reviewed_at": datetime(2026, 7, 30, 12, 0, tzinfo=UTC),
        "review_id": "review-ds1-p04-test",
        "notes": "test-only approval event",
    }

    first = approve_ds1_p04_candidate(**kwargs)
    second = approve_ds1_p04_candidate(**kwargs)

    assert first == second
    assert first["approved_record_count"] == 55
    approved = DS1ParsingDataset.model_validate_json(
        (dataset_root / "approved/ds1/p04_native_docx.json").read_text(encoding="utf-8")
    )
    assert len(approved.records) == 55
    assert all(record.review_status is ReviewStatus.APPROVED for record in approved.records)
    assert all(record.approval is not None for record in approved.records)
    review_lines = (
        (dataset_root / "reviews/review_log.jsonl").read_text(encoding="utf-8").splitlines()
    )
    assert len(review_lines) == 55
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["gold_status"] == "ds1_p04_native_docx_approved"
    assert manifest["phase_input_status"]["p04"] == "formal_eval_ready"
    assert not (dataset_root / "splits/dev_ids.txt").read_text(encoding="utf-8").strip()
    assert not (dataset_root / "splits/test_ids.txt").read_text(encoding="utf-8").strip()
