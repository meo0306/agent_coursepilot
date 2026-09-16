from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    P08DS5SplitManifest,
    P08GoldBundleManifest,
    P08ReviewDecisions,
    P08SourcePackageDataset,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.ds45_p08_approval import approve_p08_bundle
from evaluation.ds45_p08_r3_revision import build_r3
from evaluation.p08_dev_loader import load_p08_tuning_cases

ROOT = Path("datasets/courserag_eval/v1")
DOCX = "course_ai_algorithms_systems"
PDF = "course_ai_general_education"


def _load() -> tuple[
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    P08SourcePackageDataset,
    P08DS5SplitManifest,
    P08GoldBundleManifest,
]:
    ds4 = DS4QueryProcessingDataset.model_validate_json(
        (ROOT / "candidates/ds4/p08_query_processing_r3.json").read_text(encoding="utf-8")
    )
    ds5 = DS5RetrievalQADataset.model_validate_json(
        (ROOT / "candidates/ds5/p08_retrieval_r3.json").read_text(encoding="utf-8")
    )
    packages = P08SourcePackageDataset.model_validate_json(
        (ROOT / "provenance/p08_query_source_packages_r3.json").read_text(encoding="utf-8")
    )
    split = P08DS5SplitManifest.model_validate_json(
        (ROOT / "provenance/p08_ds5_split_r3.json").read_text(encoding="utf-8")
    )
    bundle = P08GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p08_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    return ds4, ds5, packages, split, bundle


def test_p08_candidate_exact_distributions_and_pending_qa() -> None:
    ds4, ds5, _, split, _ = _load()
    assert len(ds4.cases) == 60
    assert Counter(item.capability for item in ds4.cases) == Counter(
        {
            "query_normalization": 12,
            "knowledge_point_linking": 12,
            "filter_parsing": 12,
            "query_router": 12,
            "expansion_rewrite_constraints": 12,
        }
    )
    assert Counter(item.course_id for item in ds4.cases) == Counter({DOCX: 42, PDF: 18})
    assert len(ds5.cases) == 100
    assert Counter(item.query_type for item in ds5.cases) == Counter(
        {
            "exact_fact": 15,
            "definition": 15,
            "paraphrase": 15,
            "comparison": 10,
            "procedure": 10,
            "application": 10,
            "cross_section": 15,
            "unanswerable": 10,
        }
    )
    assert Counter((item.split, item.course_id) for item in ds5.cases) == Counter(
        {("dev", DOCX): 42, ("dev", PDF): 18, ("test", DOCX): 28, ("test", PDF): 12}
    )
    assert Counter((item.split, item.evaluation_stratum) for item in ds5.cases) == Counter(
        {
            ("dev", "retrieval_main"): 54,
            ("dev", "upstream_gap_diagnostic"): 6,
            ("test", "retrieval_main"): 36,
            ("test", "upstream_gap_diagnostic"): 4,
        }
    )
    assert len(split.p08_tuning_allowed_ids) == 54
    for item in ds5.cases:
        assert item.qa_gold_status == "pending_p09"
        assert item.gold_answer_type == "pending_p09"
        assert not item.gold_short_answers
        assert not item.gold_claims
        assert not item.forbidden_claims
        assert not item.allowed_answer_variants
        assert 3 <= len(item.hard_negative_evidence_ids) <= 5


def test_p08_source_packages_cover_24_sections_and_two_sources() -> None:
    _, _, packages, _, _ = _load()
    assert len(packages.packages) == 10
    assert len({item.course_id for item in packages.packages}) == 2
    assert sum(len(item.section_anchors) for item in packages.packages) == 24
    assert len({item.primary_document_id for item in packages.packages}) == 2
    assert sum(item.course_id == DOCX for item in packages.packages) == 7
    assert sum(item.course_id == PDF for item in packages.packages) == 3


def test_p08_judgments_are_same_course_and_source_grounded() -> None:
    _, ds5, packages, _, bundle = _load()
    ds2 = DS2EvidenceDataset.model_validate_json(
        (ROOT / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    evidence = {item.evidence_id: item for item in ds2.evidence}
    package_by_evidence = {
        evidence_id: package.package_id
        for package in packages.packages
        for evidence_id in package.evidence_ids
    }
    diagnostic_ids: set[str] = set()
    for case in ds5.cases:
        assert all(
            evidence[item.evidence_id].course_id == case.course_id
            for item in case.evidence_judgments
        )
        assert all(
            case.graded_relevance[item.evidence_id] == item.relevance
            for item in case.evidence_judgments
        )
        assert all(case.graded_relevance[item] == 0 for item in case.hard_negative_evidence_ids)
        assert all(
            evidence_id in package_by_evidence for evidence_id in case.hard_negative_evidence_ids
        )
        assert all(item.relevance in {0, 1, 2} for item in case.evidence_judgments)
        if case.evaluation_stratum == "upstream_gap_diagnostic":
            assert case.diagnostic_evidence_id is not None
            diagnostic_ids.add(case.diagnostic_evidence_id)
        if case.answerable:
            assert case.gold_evidence_groups
        else:
            assert case.unanswerable_audit is not None
            assert case.unanswerable_audit.audit_scope == "entire_course_approved_ds2"
    assert diagnostic_ids == set(bundle.diagnostic_evidence_ids)
    assert len(diagnostic_ids) == 10
    assert diagnostic_ids.issubset(bundle.p06_unmapped_evidence_ids)


def test_p08_families_do_not_cross_split_and_review_sets_are_exact() -> None:
    ds4, ds5, _, _, bundle = _load()
    family_sides: dict[str, set[str]] = {}
    for item in ds5.cases:
        family_sides.setdefault(str(item.query_family_id), set()).add(str(item.split))
    assert all(len(sides) == 1 for sides in family_sides.values())
    assert [len(group) for group in bundle.first_review_groups] == [20] * 8
    assert len(bundle.second_review_ids) == 132
    second_ds4 = set(bundle.second_review_ids) & {item.record_id for item in ds4.cases}
    assert len(second_ds4) == 32
    assert {item.record_id for item in ds5.cases}.issubset(bundle.second_review_ids)


def test_p08_review_assets_and_artifact_hashes_are_intact() -> None:
    _, _, _, _, bundle = _load()
    review = Path(bundle.review_pack_relative_path)
    assert sha256_file(review / "index.html") == bundle.review_pack_index_sha256
    assert sha256_file(review / "second_review.html") == bundle.second_review_index_sha256
    for evidence_id, expected in bundle.review_asset_sha256.items():
        assert sha256_file(review / "assets" / f"{evidence_id}.png") == expected
    for artifact in (
        bundle.ds4_candidate,
        bundle.ds5_candidate,
        bundle.source_packages,
        bundle.split_manifest,
    ):
        assert sha256_file(Path(artifact.path)) == artifact.sha256


def test_p08_generation_is_deterministic() -> None:
    before = {
        path: sha256_file(path)
        for path in (
            ROOT / "candidates/ds4/p08_query_processing_r3.json",
            ROOT / "candidates/ds5/p08_retrieval_r3.json",
            ROOT / "provenance/p08_query_source_packages_r3.json",
            ROOT / "provenance/p08_ds5_split_r3.json",
            ROOT / "provenance/p08_gold_bundle_manifest.json",
        )
    }
    first = build_r3(Path.cwd())
    second = build_r3(Path.cwd())
    assert first.bundle_sha256 == second.bundle_sha256
    assert before == {path: sha256_file(path) for path in before}


def test_p08_prior_revisions_are_preserved_and_r3_review_is_source_readable() -> None:
    r1 = P08GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p08_gold_bundle_manifest_r1.json").read_text(encoding="utf-8")
    )
    assert r1.revision == 1
    assert r1.bundle_sha256 == "329433b38981be2f5bb0608cc38146d6f4c29e902cf624065e6ef1e716e4354d"
    for artifact in (r1.ds4_candidate, r1.ds5_candidate):
        assert sha256_file(Path(artifact.path)) == artifact.sha256
    r2 = P08GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p08_gold_bundle_manifest_r2.json").read_text(encoding="utf-8")
    )
    assert r2.revision == 2
    _, _, _, _, r3 = _load()
    assert r3.revision == 3
    first_review = Path(r3.review_pack_relative_path, "index.html").read_text(encoding="utf-8")
    assert "linked_knowledge_points：ID → 名称 → Summary → 主证据原文" in first_review
    assert "必要邻接" in first_review
    assert "页码：" in first_review
    assert "BBox：" in first_review
    assert "record_notes" in first_review


def test_p08_r3_full_relevance_audit_and_review_note_contract() -> None:
    _, ds5, _, _, bundle = _load()
    ds3 = DS3KnowledgePointDataset.model_validate_json(
        (ROOT / "approved/ds3/p07_knowledge_points.json").read_text(encoding="utf-8")
    )
    evidence_kps: dict[str, set[str]] = {}
    for knowledge_point in ds3.knowledge_points:
        for link in knowledge_point.evidence_links:
            evidence_kps.setdefault(link.evidence_id, set()).add(knowledge_point.gold_kp_id)
    audit = __import__("json").loads(
        (ROOT / "provenance/p08_r3_relevance_audit.json").read_text(encoding="utf-8")
    )
    assert set(audit["cases"]) == {item.record_id for item in ds5.cases}
    for item in ds5.cases:
        assert len(item.hard_negative_evidence_ids) == 4
        positive_ids = {
            judgment.evidence_id for judgment in item.evidence_judgments if judgment.relevance > 0
        }
        assert not positive_ids & set(item.hard_negative_evidence_ids)
        assert all(
            not set(item.expected_knowledge_points) & evidence_kps.get(evidence_id, set())
            for evidence_id in item.hard_negative_evidence_ids
        )
        assert len(audit["cases"][item.record_id]["negative_ranking_top8"]) == 8
    assert all("联系" not in item.query for item in ds5.cases if item.query_type == "cross_section")

    review = P08ReviewDecisions(
        bundle_sha256=bundle.bundle_sha256,
        review_pass="first",
        expected_record_ids=["record-a"],
        reviewed_record_ids=["record-a"],
        returned_record_ids=["record-a"],
        record_notes={"record-a": "Evidence 相关性需修正"},
    )
    assert review.record_notes["record-a"] == "Evidence 相关性需修正"


def test_p08_r3_conversation_attestations_cover_both_review_passes() -> None:
    _, _, _, _, bundle = _load()
    first = P08ReviewDecisions.model_validate_json(
        (ROOT / "reviews/p08_r3_first_review_decisions.json").read_text(encoding="utf-8")
    )
    second = P08ReviewDecisions.model_validate_json(
        (ROOT / "reviews/p08_r3_second_review_decisions.json").read_text(encoding="utf-8")
    )
    expected_first = [item for group in bundle.first_review_groups for item in group]
    assert first.bundle_sha256 == second.bundle_sha256 == bundle.bundle_sha256
    assert first.expected_record_ids == first.reviewed_record_ids == expected_first
    assert second.expected_record_ids == second.reviewed_record_ids == bundle.second_review_ids
    assert not first.returned_record_ids and not second.returned_record_ids
    assert (
        first.attestation_source
        == second.attestation_source
        == ("course_owner_conversation_attestation")
    )


def test_p08_approved_retrieval_gold_preserves_pending_qa_and_split() -> None:
    ds4 = DS4QueryProcessingDataset.model_validate_json(
        (ROOT / "approved/ds4/p08_query_processing.json").read_text(encoding="utf-8")
    )
    ds5 = DS5RetrievalQADataset.model_validate_json(
        (ROOT / "approved/ds5/p08_retrieval.json").read_text(encoding="utf-8")
    )
    assert len(ds4.cases) == 60 and len(ds5.cases) == 100
    assert all(item.review_status == "approved" for item in [*ds4.cases, *ds5.cases])
    assert all(item.retrieval_gold_status == "approved" for item in ds5.cases)
    assert all(item.qa_gold_status == "pending_p09" for item in ds5.cases)
    assert all(
        not (
            item.gold_short_answers
            or item.gold_claims
            or item.forbidden_claims
            or item.allowed_answer_variants
        )
        for item in ds5.cases
    )
    assert len((ROOT / "splits/dev_ids.txt").read_text(encoding="utf-8").splitlines()) == 60
    assert len((ROOT / "splits/test_ids.txt").read_text(encoding="utf-8").splitlines()) == 40


def test_p08_approval_rejects_wrong_hash_and_dev_loader_is_test_closed(tmp_path: Path) -> None:
    _, _, _, split, bundle = _load()
    with pytest.raises(ValueError, match="literal P08"):
        approve_p08_bundle(
            dataset_root=ROOT,
            expected_bundle_sha256="0" * 64,
            first_review_path=tmp_path / "missing-first.json",
            second_review_path=tmp_path / "missing-second.json",
            reviewer_id="course_owner",
            reviewed_at=datetime.now(UTC),
            review_id="p08-test-wrong-hash",
            notes="test",
        )
    assert bundle.bundle_sha256 != "0" * 64
    selected = load_p08_tuning_cases(ROOT)
    assert len(selected) == 54
    assert {item.record_id for item in selected} == set(split.p08_tuning_allowed_ids)
    test_id = next(item.case_id for item in split.assignments if item.split == "test")
    with pytest.raises(ValueError, match="refuses Test IDs"):
        load_p08_tuning_cases(ROOT, requested_ids={test_id})


def test_old_ds4_ds5_pilots_still_validate() -> None:
    DS4QueryProcessingDataset.model_validate_json(
        (ROOT / "candidates/ds4/pilot.json").read_text(encoding="utf-8")
    )
    DS5RetrievalQADataset.model_validate_json(
        (ROOT / "candidates/ds5/pilot.json").read_text(encoding="utf-8")
    )
