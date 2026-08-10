from __future__ import annotations

import json
import shutil
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.evals.schemas import (
    DS2BatchApproval,
    DS2CandidateManifest,
    DS2EvidenceDataset,
    DS2ReviewDecisions,
)
from evaluation.contracts import CandidateRevisionHistory, ReviewStatus
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import load_review_log, record_digest
from evaluation.ds2_p06_approval import approve_ds2_candidate

CANDIDATE_SHA256 = "ebc980a4f52a763001bd2169c1215aac81eac55f4f661f7320a0e600e0acdcad"
APPROVED_SHA256 = "f49d84027cde8341d906e270d29cc46e7b71eb6de4da5220188cb03894436b78"
APPROVAL_SHA256 = "e77d055da2ee173a2a931ef74d3b910a98679f83e3e5ec7d2340354d13869603"
CANDIDATE_PATH = Path("datasets/courserag_eval/v1/candidates/ds2/p06_evidence_r7.json")
APPROVED_PATH = Path("datasets/courserag_eval/v1/approved/ds2/p06_evidence.json")
APPROVAL_PATH = Path("datasets/courserag_eval/v1/provenance/ds2_p06_approval.json")
R6_PATH = Path("datasets/courserag_eval/v1/candidates/ds2/p06_evidence_r6.json")
MANIFEST_PATH = Path("datasets/courserag_eval/v1/provenance/ds2_p06_candidate_manifest.json")
HISTORY_PATH = Path("datasets/courserag_eval/v1/provenance/ds2_p06_candidate_revision_history.json")
NEIGHBOR_AUDIT_PATH = Path(
    "datasets/courserag_eval/v1/provenance/ds2_p06_necessary_neighbor_audit_r7.json"
)
OCR_PAGES = {11, 15, 18, 21, 22, 23, 24, 26, 27, 32}
DOCX_SECTIONS = {
    "1.1.1",
    "2.2",
    "2.2.2",
    "3.1.3",
    "3.5.3",
    "5.1.1",
    "5.2.1",
    "5.3",
    "5.3.4",
    "6.2.2",
    "6.2.3",
    "6.3",
    "9.1.2",
    "9.2.2",
    "9.5.1",
    "9.7",
}
PDF_SECTIONS = {"1.1.1", "1.1.2", "1.2.1", "1.2.2", "1.2.3", "1.3.1", "1.3.4", "1.3.7"}


def _candidate() -> DS2EvidenceDataset:
    return DS2EvidenceDataset.model_validate_json(CANDIDATE_PATH.read_text(encoding="utf-8"))


def test_formal_ds2_candidate_is_hash_bound_balanced_and_immutable_after_approval() -> None:
    candidate = _candidate()
    manifest = DS2CandidateManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    records = candidate.evidence

    assert sha256_file(CANDIDATE_PATH) == CANDIDATE_SHA256
    assert manifest.candidate_revision == 7
    assert manifest.candidate_file_sha256 == CANDIDATE_SHA256
    assert manifest.candidate_record_sha256 == {
        record.record_id: record_digest(record) for record in records
    }
    assert len(records) == len({record.record_id for record in records}) == 120
    assert Counter(record.course_id for record in records) == {
        "course_ai_algorithms_systems": 80,
        "course_ai_general_education": 40,
    }
    assert Counter(record.source_type for record in records) == {
        "native_text": 110,
        "ocr_derived": 10,
    }
    assert sum(record.semantic_unit_type == "table" for record in records) == 9
    assert manifest.record_counts["table_gold_derived"] == 10
    assert manifest.record_counts["procedure_from_table_gold"] == 1
    assert all(record.review_status is ReviewStatus.CANDIDATE for record in records)
    assert all(record.approval is None for record in records)
    assert all(record.evidence_id.startswith("gold-ev-") for record in records)
    assert APPROVED_PATH.exists()

    section_counts = Counter(
        (record.course_id, record.source_span.section_path[-1]) for record in records
    )
    assert (
        set(section for course, section in section_counts if course.endswith("systems"))
        == DOCX_SECTIONS
    )
    assert (
        set(section for course, section in section_counts if course.endswith("education"))
        == PDF_SECTIONS
    )
    assert set(section_counts.values()) == {5}

    assert [group.group_id for group in manifest.review_groups] == [
        "group-01",
        "group-02",
        "group-03",
        "group-04",
    ]
    assert [len(group.record_ids) for group in manifest.review_groups] == [30, 30, 30, 30]
    assert len(manifest.retained_reviewed_record_ids) == 120
    assert len(manifest.required_rereview_record_ids) == 0
    assert not (
        set(manifest.retained_reviewed_record_ids) & set(manifest.required_rereview_record_ids)
    )
    assert manifest.duplicate_review_record_ids == []


def test_formal_ds2_approved_dataset_is_exactly_bound_and_complete() -> None:
    candidate = _candidate()
    approved = DS2EvidenceDataset.model_validate_json(APPROVED_PATH.read_text(encoding="utf-8"))
    batch = DS2BatchApproval.model_validate_json(APPROVAL_PATH.read_text(encoding="utf-8"))

    assert sha256_file(APPROVED_PATH) == APPROVED_SHA256
    assert sha256_file(APPROVAL_PATH) == APPROVAL_SHA256
    assert batch.candidate_file_sha256 == CANDIDATE_SHA256
    assert batch.approved_file_sha256 == APPROVED_SHA256
    assert batch.reviewer_id == "course_owner"
    assert len(batch.candidate_record_sha256) == len(batch.approved_record_sha256) == 120
    assert [record.record_id for record in approved.evidence] == [
        record.record_id for record in candidate.evidence
    ]
    assert all(record.review_status is ReviewStatus.APPROVED for record in approved.evidence)
    assert all(record.approval is not None for record in approved.evidence)
    for candidate_record, approved_record in zip(
        candidate.evidence, approved.evidence, strict=True
    ):
        assert approved_record.approval is not None
        assert approved_record.approval.candidate_sha256 == record_digest(candidate_record)
        assert approved_record.approval.approved_record_sha256 == record_digest(approved_record)
        assert batch.candidate_record_sha256[candidate_record.record_id] == record_digest(
            candidate_record
        )
        assert batch.approved_record_sha256[approved_record.record_id] == record_digest(
            approved_record
        )

    review_log = load_review_log(Path("datasets/courserag_eval/v1/reviews/review_log.jsonl"))
    approval_entries = [
        entry
        for review_id, entry in review_log.items()
        if review_id.startswith(f"{batch.review_id}.")
    ]
    assert len(approval_entries) == 120
    assert {entry.record_id for entry in approval_entries} == {
        record.record_id for record in approved.evidence
    }
    governance = json.loads(Path("datasets/courserag_eval/v1/manifest.json").read_text("utf-8"))
    assert governance["gold_status"] in {
        "ds2_p06_evidence_approved",
        "ds3_p07_knowledge_points_approved",
        "ds5_p08_retrieval_approved",
        "ds5_p09_qa_context_approved",
        "p10_input_gold_approved",
    }
    assert governance["gold_components"]["ds2"] == "approved"
    assert governance["phase_input_status"]["p06"] in {
        "formal_eval_ready",
        "completed_gate_passed",
    }
    dev_ids = Path("datasets/courserag_eval/v1/splits/dev_ids.txt").read_text("utf-8").split()
    test_ids = Path("datasets/courserag_eval/v1/splits/test_ids.txt").read_text("utf-8").split()
    if governance["gold_components"].get("ds5_retrieval") == "approved":
        assert len(dev_ids) == 60 and len(test_ids) == 40
    else:
        assert not dev_ids and not test_ids
    test_lock = json.loads(Path("datasets/courserag_eval/v1/test.lock.json").read_text("utf-8"))
    assert test_lock["locked"] is False


def test_formal_ds2_r7_changes_context_only_and_audits_all_records() -> None:
    r6 = DS2EvidenceDataset.model_validate_json(R6_PATH.read_text(encoding="utf-8"))
    r7 = _candidate()
    before = {record.record_id: record for record in r6.evidence}
    after = {record.record_id: record for record in r7.evidence}
    assert list(before) == list(after)

    for record_id, prior in before.items():
        current = after[record_id]
        assert current.gold_text == prior.gold_text
        assert current.content_sha256 == prior.content_sha256
        assert current.normalized_content_sha256 == prior.normalized_content_sha256
        assert current.source_units == prior.source_units
        assert current.source_span == prior.source_span
        assert current.bboxes == prior.bboxes
        assert current.semantic_unit_type == prior.semantic_unit_type
        assert current.upstream_record_refs == prior.upstream_record_refs
        assert current.requires_parent is bool(current.necessary_neighbors)
        assert current.necessary_neighbor_text == [
            neighbor.text for neighbor in current.necessary_neighbors
        ]

    assert sum(bool(record.necessary_neighbors) for record in r7.evidence) == 55
    assert sum(not record.necessary_neighbors for record in r7.evidence) == 65
    assert sum(record_digest(before[item]) != record_digest(after[item]) for item in before) == 78
    parent_heading = [
        neighbor.text
        for record in r7.evidence
        for neighbor in record.necessary_neighbors
        if neighbor.relation == "parent_heading"
    ]
    assert parent_heading == ["（2）R3-LIVE[23]"]

    audit = json.loads(NEIGHBOR_AUDIT_PATH.read_text(encoding="utf-8"))
    assert audit["candidate_file_sha256"] == CANDIDATE_SHA256
    assert len(audit["entries"]) == 120
    assert audit["neighbors_required_record_count"] == 55
    assert audit["standalone_record_count"] == 65
    assert audit["stable_ids_unchanged"] is True
    assert audit["gold_content_hashes_unchanged"] is True
    assert audit["course_owner_item_rereview_waived"] is True
    assert audit["exact_batch_hash_approval_required"] is True

    corrected_algorithm = next(
        record
        for record in r7.evidence
        if record.source_units[0].source_unit_id == "table:0:rendered-visible-algorithm"
    )
    assert corrected_algorithm.semantic_unit_type == "procedure"
    assert "Y_{i(t)}(ω_t^T X_{i(t)})≤0" in corrected_algorithm.gold_text


def test_formal_ds2_ocr_and_geometry_provenance_obey_the_frozen_contract() -> None:
    records = _candidate().evidence
    ocr = [record for record in records if record.source_type == "ocr_derived"]

    assert {
        record.ocr_provenance.source_page_number for record in ocr if record.ocr_provenance
    } == OCR_PAGES
    assert all(record.ocr_provenance is not None for record in ocr)
    assert all(record.ocr_confidence is None for record in ocr)
    assert all(
        record.ocr_provenance is None for record in records if record.source_type != "ocr_derived"
    )
    assert {record.source_span.document_id for record in records} == {
        "doc_ai_algorithms_systems",
        "doc_ai_general_education_excerpt",
    }

    for record in records:
        assert record.bboxes
        for box in record.bboxes:
            x0, y0, x1, y1 = box.bbox
            assert 0 <= x0 < x1 <= box.page_width
            assert 0 <= y0 < y1 <= box.page_height

    split_table = next(
        record for record in records if record.source_units[0].source_unit_id == "table:20"
    )
    assert split_table.gold_text.splitlines() == [
        "种类\t中型卡车\t小轿车\t人员",
        "距离\t6.8m*2.7m\t4.3m*1.5m\t1.7m*0.5m",
        "5.5km\t27*11\t20*7\t",
        "3km\t50*21\t36*13\t",
        "1km\t150*63\t108*36\t",
        "800m\t\t\t48*14",
        "500m\t\t\t78*23",
    ]
    assert [box.page_number for box in split_table.bboxes] == [547, 548]
    assert all(box.bbox[0] < 91 and box.bbox[2] > 505 for box in split_table.bboxes)


def test_formal_ds2_pre_delivery_revisions_are_append_only() -> None:
    history = CandidateRevisionHistory.model_validate_json(HISTORY_PATH.read_text(encoding="utf-8"))

    assert [revision.revision for revision in history.revisions] == [1, 2, 3, 4, 5, 6, 7]
    assert [revision.status for revision in history.revisions] == [
        "superseded",
        "superseded",
        "superseded",
        "superseded",
        "rejected",
        "superseded",
        "approved",
    ]
    assert history.revisions[-1].candidate_file_sha256 == CANDIDATE_SHA256


def _copy_approval_fixture(tmp_path: Path) -> tuple[Path, Path]:
    repository_root = tmp_path
    dataset_root = repository_root / "datasets/courserag_eval/v1"
    candidate_target = dataset_root / "candidates/ds2/p06_evidence_r7.json"
    manifest_target = dataset_root / "provenance/ds2_p06_candidate_manifest.json"
    history_target = dataset_root / "provenance/ds2_p06_candidate_revision_history.json"
    decisions_target = dataset_root / "reviews/ds2_p06_review_decisions.json"
    candidate_target.parent.mkdir(parents=True)
    manifest_target.parent.mkdir(parents=True)
    decisions_target.parent.mkdir(parents=True)
    (dataset_root / "approved/ds2").mkdir(parents=True)
    (dataset_root / "splits").mkdir(parents=True)
    shutil.copyfile(CANDIDATE_PATH, candidate_target)
    shutil.copyfile(MANIFEST_PATH, manifest_target)
    shutil.copyfile(HISTORY_PATH, history_target)
    candidate = _candidate()
    decisions = DS2ReviewDecisions(
        candidate_file_sha256=CANDIDATE_SHA256,
        reviewed_record_ids=[record.record_id for record in candidate.evidence],
        completed_group_ids=["group-01", "group-02", "group-03", "group-04"],
        notes="test-only complete review decisions",
    )
    decisions_target.write_text(
        json.dumps(decisions.model_dump(mode="json"), ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    (dataset_root / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_id": "courserag-eval",
                "dataset_version": "v1",
                "gold_status": "ds1_p05_ocr_approved",
                "phase_input_status": {
                    "p05": "completed_gate_passed",
                    "p06": "candidate_pending_owner_review",
                },
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
    return dataset_root, decisions_target


def test_ds2_approval_rejects_the_wrong_literal_hash(tmp_path: Path) -> None:
    dataset_root, decisions = _copy_approval_fixture(tmp_path)

    with pytest.raises(ValueError, match="literal DS2 Candidate SHA-256"):
        approve_ds2_candidate(
            dataset_root=dataset_root,
            expected_candidate_file_sha256="0" * 64,
            review_decisions_path=decisions,
            reviewer_id="course_owner_test_double",
            reviewed_at=datetime(2026, 8, 3, tzinfo=UTC),
            review_id="review-ds2-p06-contract-test",
            notes="Contract test only; no repository approval is created.",
        )

    assert not (dataset_root / "approved/ds2/p06_evidence.json").exists()


def test_ds2_exact_hash_approval_is_complete_and_idempotent_in_isolation(
    tmp_path: Path,
) -> None:
    dataset_root, decisions = _copy_approval_fixture(tmp_path)
    kwargs = {
        "dataset_root": dataset_root,
        "expected_candidate_file_sha256": CANDIDATE_SHA256,
        "review_decisions_path": decisions,
        "reviewer_id": "course_owner_test_double",
        "reviewed_at": datetime(2026, 8, 3, tzinfo=UTC),
        "review_id": "review-ds2-p06-contract-test",
        "notes": "Contract test only; no repository approval is created.",
    }

    first = approve_ds2_candidate(**kwargs)
    second = approve_ds2_candidate(**kwargs)

    assert first == second
    assert first["approved_record_count"] == 120
    approved = DS2EvidenceDataset.model_validate_json(
        (dataset_root / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    assert all(record.review_status is ReviewStatus.APPROVED for record in approved.evidence)
    assert all(record.approval is not None for record in approved.evidence)
    assert (
        len((dataset_root / "reviews/review_log.jsonl").read_text(encoding="utf-8").splitlines())
        == 120
    )
    governance = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    assert governance["gold_status"] == "ds2_p06_evidence_approved"
    assert governance["phase_input_status"]["p06"] == "formal_eval_ready"
