import json
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import coursepilot.models  # noqa: F401
import courserag.persistence.models  # noqa: F401
from coursepilot.db.base import Base
from courserag.evals.schemas import (
    CorpusDocument,
    CorpusFixtureArtifact,
    CorpusFixtureManifest,
    DS0CorpusDataset,
    P04InputWorkPackage,
)
from courserag.persistence.base import CourseRAGBase
from courserag.persistence.models import (
    ArtifactRecord,
    BuildJobDocumentVersionRecord,
    BuildJobRecord,
    BuildStageRunRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    SourceDocumentRecord,
)
from evaluation.corpus_fixtures import sha256_file, sha256_text
from evaluation.datasets import record_digest
from evaluation.pre_p04_approval import approve_p04_input
from evaluation.pre_p04_data import deterministic_id, seed_p03_eval_identities


@pytest.fixture
def pre_p04_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    CourseRAGBase.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        yield session


def _synthetic_inputs(
    tmp_path: Path,
) -> tuple[DS0CorpusDataset, CorpusFixtureManifest, dict[str, Path]]:
    specs = [
        ("course-a", "doc-a", "primary", None, True, "application/pdf"),
        ("course-a", "doc-a-scan", "derived_fixture", "doc-a", False, "application/pdf"),
        ("course-a", "doc-a-mixed", "derived_fixture", "doc-a", False, "application/pdf"),
        (
            "course-b",
            "doc-b",
            "primary",
            None,
            True,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "course-b",
            "doc-b-stress",
            "derived_fixture",
            "doc-b",
            False,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        (
            "course-b",
            "doc-b-copy",
            "derived_fixture",
            "doc-b",
            False,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
    ]
    paths: dict[str, Path] = {}
    documents: list[CorpusDocument] = []
    artifacts: list[CorpusFixtureArtifact] = []
    for index, (course_id, document_id, role, parent, retrievable, mime_type) in enumerate(specs):
        path = tmp_path / f"{document_id}.bin"
        path.write_bytes(f"document-{index}".encode())
        paths[document_id] = path
        digest = sha256_file(path)
        group = f"{course_id}:variants"
        page_count_basis = (
            "derived_manifest"
            if role == "derived_fixture"
            else "verified_pdf_page_tree"
            if mime_type == "application/pdf"
            else "pending_fixed_renderer"
        )
        documents.append(
            CorpusDocument(
                record_id=f"ds0-{document_id}",
                course_id=course_id,
                document_id=document_id,
                filename=path.name,
                repository_relative_path=f"storage_eval/{path.name}",
                document_role=role,
                parent_document_id=parent,
                mime_type=mime_type,
                sha256=digest,
                document_version=f"eval-v1-{digest[:16]}",
                page_count=1 if mime_type == "application/pdf" else None,
                page_count_basis=page_count_basis,
                derivation_manifest_sha256="a" * 64 if role == "derived_fixture" else None,
                mutually_exclusive_variant_group=group,
            )
        )
        artifacts.append(
            CorpusFixtureArtifact(
                course_id=course_id,
                document_id=document_id,
                document_role=role,
                parent_document_id=parent,
                repository_relative_path=f"storage_eval/{path.name}",
                mime_type=mime_type,
                sha256=digest,
                size_bytes=path.stat().st_size,
                page_count=1 if mime_type == "application/pdf" else None,
                page_count_basis=page_count_basis,
                transform_type=(
                    "identity"
                    if role == "primary"
                    else "raster_subset_lossless"
                    if mime_type == "application/pdf"
                    else "docx_structure_stress"
                ),
                mutually_exclusive_variant_group=group,
                retrieval_eligible=retrievable,
            )
        )
    return (
        DS0CorpusDataset(dataset_id="courserag-eval", dataset_version="v1", documents=documents),
        CorpusFixtureManifest(
            generator="test",
            generator_version="1.0",
            artifacts=artifacts,
        ),
        paths,
    )


def test_p03_eval_identity_seed_is_deterministic_and_idempotent(
    pre_p04_session: Session, tmp_path: Path
) -> None:
    approved, fixture_manifest, paths = _synthetic_inputs(tmp_path)
    artifact_root = tmp_path / "artifacts"
    first = seed_p03_eval_identities(
        pre_p04_session,
        approved=approved,
        fixture_manifest=fixture_manifest,
        paths=paths,
        artifact_root=artifact_root,
    )
    second = seed_p03_eval_identities(
        pre_p04_session,
        approved=approved,
        fixture_manifest=fixture_manifest,
        paths=paths,
        artifact_root=artifact_root,
    )

    assert first == second
    assert pre_p04_session.query(KnowledgeBaseRecord).count() == 2
    assert pre_p04_session.query(SourceDocumentRecord).count() == 6
    assert pre_p04_session.query(DocumentVersionRecord).count() == 6
    assert pre_p04_session.query(BuildJobRecord).count() == 6
    assert pre_p04_session.query(BuildJobDocumentVersionRecord).count() == 6
    assert pre_p04_session.query(BuildStageRunRecord).count() == 6
    assert pre_p04_session.query(ArtifactRecord).count() == 6
    assert first.bindings[0].knowledge_base_id == deterministic_id(
        "knowledge-base", first.bindings[0].course_id
    )
    assert all(binding.build_status == "succeeded" for binding in first.bindings)
    assert all(binding.artifact_uri.startswith("artifact://sha256/") for binding in first.bindings)
    assert all("\\" not in binding.artifact_uri for binding in first.bindings)


def test_tracked_p04_input_preserves_candidate_approved_boundary() -> None:
    root = Path("datasets/courserag_eval/v1")
    candidate_path = root / "candidates" / "work_packages" / "p04_input.json"
    candidate = P04InputWorkPackage.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    assert sha256_file(candidate_path) == (
        "b305f328a8e76555e661e048f34c7ea7c89ed82c9fb9982f4877e1b6a80df582"
    )
    assert candidate.review_status == "candidate"
    assert candidate.approval is None
    assert candidate.gold_status == "no_ds1_gold"
    assert len(candidate.identities) == 6
    assert len(candidate.native_pdf_pages) == 15
    assert len(candidate.docx_pagination_anchors) == 10
    assert len(candidate.sections) == 20
    assert len(candidate.tables) == 10
    assert len(candidate.ocr_route_only_pages) == 15
    assert {page.page_number for page in candidate.native_pdf_pages} == {
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
    assert {
        section.section_anchor
        for section in candidate.sections
        if section.document_id == "doc_ai_general_education_excerpt"
    } == {"1.1.1", "1.1.2", "1.2.1", "1.2.2", "1.2.3", "1.3.1", "1.3.4", "1.4.1"}
    assert {
        section.section_anchor
        for section in candidate.sections
        if section.document_id == "doc_ai_algorithms_systems"
    } == {
        "1.1.1",
        "2.2",
        "2.2.2",
        "3.1.3",
        "3.5.3",
        "5.1.1",
        "5.2.1",
        "5.3",
        "6.2.2",
        "6.2.3",
        "9.1.2",
        "9.7",
    }
    assert {
        table.source_table_index
        for table in candidate.tables
        if table.document_id == "doc_ai_algorithms_systems"
    } == {0, 1, 6, 8, 10, 12, 18, 20, 21}
    assert {
        route.document_id: {
            item.source_page_number
            for item in candidate.ocr_route_only_pages
            if item.document_id == route.document_id
        }
        for route in candidate.ocr_route_only_pages
    } == {
        "doc_ai_general_education_scan_clean": {21, 23, 24, 26, 30},
        "doc_ai_general_education_scan_compressed": {11, 15, 18, 27, 31},
        "doc_ai_general_education_mixed": {9, 22, 25, 29, 32},
    }
    assert all(
        anchor.source_text_sha256 == sha256_text(anchor.source_text)
        for anchor in candidate.docx_pagination_anchors
    )
    assert all(
        section.source_title_sha256 == sha256_text(section.source_title)
        for section in candidate.sections
    )
    assert all(anchor.physical_page_index is None for anchor in candidate.docx_pagination_anchors)
    approved_path = root / "approved" / "work_packages" / "p04_input.json"
    approved = P04InputWorkPackage.model_validate_json(approved_path.read_text(encoding="utf-8"))
    assert approved.review_status == "approved"
    assert approved.approval is not None
    assert approved.approval.review_id == "review-pre-p04-input-20260729-01"
    assert approved.approval.reviewer_id == "course_owner"
    assert approved.approval.candidate_sha256 == record_digest(candidate)
    assert approved.approval.approved_record_sha256 == record_digest(approved)
    assert approved.gold_status == "no_ds1_gold"
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["gold_components"]["ds1_native_docx"] == "approved"
    assert manifest["phase_input_status"]["p04"] == "formal_eval_ready"
    dev_ids = (root / "splits" / "dev_ids.txt").read_text(encoding="utf-8").split()
    test_ids = (root / "splits" / "test_ids.txt").read_text(encoding="utf-8").split()
    if manifest["gold_components"].get("ds5_retrieval") == "approved":
        assert len(dev_ids) == 60 and len(test_ids) == 40
    else:
        assert not dev_ids and not test_ids
    test_lock = json.loads((root / "test.lock.json").read_text(encoding="utf-8"))
    assert test_lock["locked"] is False


def test_p04_input_approval_is_hash_bound_and_does_not_promote_gold(tmp_path: Path) -> None:
    source_root = Path("datasets/courserag_eval/v1")
    dataset_root = tmp_path / "v1"
    candidate_source = source_root / "candidates" / "work_packages" / "p04_input.json"
    candidate_target = dataset_root / "candidates" / "work_packages" / "p04_input.json"
    candidate_target.parent.mkdir(parents=True)
    candidate_target.write_bytes(candidate_source.read_bytes())
    review_log = dataset_root / "reviews" / "review_log.jsonl"
    review_log.parent.mkdir(parents=True)
    review_log.write_text("", encoding="utf-8")
    manifest = {
        "gold_status": "ds0_pilot_approved",
        "phase_input_status": {"p04": "candidate_pending_course_owner"},
    }
    manifest_path = dataset_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = approve_p04_input(
        dataset_root=dataset_root,
        expected_candidate_file_sha256=sha256_file(candidate_target),
        reviewer_id="course_owner",
        reviewed_at=datetime.fromisoformat("2026-07-29T12:00:00+00:00"),
        review_id="review-pre-p04-input-test",
        notes="Test approval of input selection only.",
    )

    approved = P04InputWorkPackage.model_validate_json(
        (dataset_root / "approved" / "work_packages" / "p04_input.json").read_text(encoding="utf-8")
    )
    assert approved.review_status == "approved"
    assert approved.approval is not None
    assert result["candidate_file_sha256"] == sha256_file(candidate_target)
    updated_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert updated_manifest["gold_status"] == "ds0_pilot_approved"
    assert updated_manifest["phase_input_status"]["p04"] == "approved_for_annotation"
