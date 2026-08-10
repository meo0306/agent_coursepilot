from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS5RetrievalQADataset,
    P09ContextGoldDataset,
    P09CoverageAuditDataset,
    P09GoldBundleManifest,
    P09QAGoldDataset,
    P09ReviewDecision,
    P09ReviewDecisions,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.ds5_p09_approval import approve_p09_bundle
from evaluation.ds5_p09_data import generate_p09_candidates
from evaluation.ds5_p09_r2_revision import build_r2
from evaluation.ds5_p09_review_attestation import record_owner_attestation
from evaluation.io import atomic_write_json
from evaluation.p09_dev_loader import load_p09_dev_bundle

ROOT = Path("datasets/courserag_eval/v1")


def _load_current() -> tuple[
    DS5RetrievalQADataset,
    DS2EvidenceDataset,
    P09QAGoldDataset,
    P09ContextGoldDataset,
    P09GoldBundleManifest,
]:
    retrieval = DS5RetrievalQADataset.model_validate_json(
        (ROOT / "approved/ds5/p08_retrieval.json").read_text(encoding="utf-8")
    )
    evidence = DS2EvidenceDataset.model_validate_json(
        (ROOT / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    qa = P09QAGoldDataset.model_validate_json(
        (ROOT / "candidates/ds5/p09_qa_r1.json").read_text(encoding="utf-8")
    )
    context = P09ContextGoldDataset.model_validate_json(
        (ROOT / "candidates/ds5/p09_context_r1.json").read_text(encoding="utf-8")
    )
    manifest = P09GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p09_gold_bundle_manifest_r1.json").read_text(encoding="utf-8")
    )
    return retrieval, evidence, qa, context, manifest


def test_p09_candidate_exact_scope_and_source_grounding() -> None:
    retrieval, evidence_dataset, qa, context, manifest = _load_current()
    evidence = {item.evidence_id: item for item in evidence_dataset.evidence}
    retrieval_by_id = {item.record_id: item for item in retrieval.cases}
    assert len(qa.cases) == len(context.cases) == 100
    assert sum(item.answerable for item in qa.cases) == 90
    assert sum(not item.answerable for item in qa.cases) == 10
    assert sum(item.split == "dev" for item in qa.cases) == 60
    assert sum(item.split == "test" for item in qa.cases) == 40
    assert sum(item.evaluation_stratum == "retrieval_main" for item in qa.cases) == 90
    assert sum(item.evaluation_stratum == "upstream_gap_diagnostic" for item in qa.cases) == 10
    assert {item.retrieval_case_id for item in qa.cases} == set(retrieval_by_id)
    assert {item.retrieval_case_id for item in context.cases} == set(retrieval_by_id)
    for item in qa.cases:
        source_case = retrieval_by_id[item.retrieval_case_id]
        assert item.query == source_case.query
        assert item.query_sha256 == source_case.query_sha256
        assert item.course_id == source_case.course_id
        assert item.split == source_case.split
        if item.answerable:
            assert item.gold_claims
            assert any(claim.importance == "required" for claim in item.gold_claims)
            for claim in item.gold_claims:
                for support in claim.evidence_supports:
                    assert support.evidence_id in evidence
                    assert support.exact_support_excerpt in evidence[support.evidence_id].gold_text
        else:
            assert item.gold_answer_type == "unanswerable"
            assert item.expected_behavior == "abstained_insufficient_evidence"
            assert not item.gold_claims
            assert not item.gold_short_answers
    assert sha256_file(ROOT / "approved/ds5/p08_retrieval.json") == (
        manifest.approved_p08_retrieval.sha256
    )


def test_p09_context_constraints_and_review_sets() -> None:
    retrieval, _, qa, context, manifest = _load_current()
    retrieval_by_id = {item.record_id: item for item in retrieval.cases}
    qa_by_id = {item.record_id: item for item in qa.cases}
    for item in context.cases:
        source_case = retrieval_by_id[item.retrieval_case_id]
        assert item.qa_case_id in qa_by_id
        assert item.max_items == 8
        assert item.max_tokens == 4000
        assert item.preserve_evidence_boundaries
        assert item.context_order_policy == "not_fixed_equivalent_orders_allowed"
        if item.answerable:
            assert item.complete_evidence_groups == source_case.gold_evidence_groups
            assert set(item.hard_negative_evidence_ids).isdisjoint(item.relevant_evidence_ids)
        else:
            assert not item.complete_evidence_groups
            assert not item.relevant_evidence_ids
            assert not item.necessary_neighbors
    first = [item for group in manifest.first_review_groups for item in group]
    assert len(first) == len(set(first)) == 100
    assert all(len(group) == 20 for group in manifest.first_review_groups)
    assert set(manifest.second_review_ids).issubset(first)
    assert len(manifest.second_review_ids) == 67
    review_dir = Path(manifest.review_pack_relative_path)
    assert sha256_file(review_dir / "index.html") == manifest.review_pack_index_sha256
    assert sha256_file(review_dir / "second_review.html") == manifest.second_review_index_sha256
    html = (review_dir / "index.html").read_text(encoding="utf-8")
    assert "Evidence 原文、页码与 BBox" in html
    assert "知识点（ID 与名称）" in html
    assert "最小必要邻接" in html


def _copy_pre_p09_repo(tmp_path: Path) -> Path:
    repository = tmp_path / "repo"
    files = (
        "datasets/courserag_eval/v1/approved/ds5/p08_retrieval.json",
        "datasets/courserag_eval/v1/approved/ds2/p06_evidence.json",
        "datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json",
        "datasets/courserag_eval/v1/approved/ds1/p05_ocr.json",
        "datasets/courserag_eval/v1/provenance/p08_gold_bundle_approval.json",
        "datasets/courserag_eval/v1/manifest.json",
        "datasets/courserag_eval/v1/test.lock.json",
        "datasets/courserag_eval/v1/splits/dev_ids.txt",
        "datasets/courserag_eval/v1/splits/test_ids.txt",
        "datasets/courserag_eval/v1/candidates/ds5/p09_qa_r1.json",
        "datasets/courserag_eval/v1/candidates/ds5/p09_context_r1.json",
        "datasets/courserag_eval/v1/provenance/p09_gold_bundle_manifest_r1.json",
        "storage_eval/p08_hybrid_retrieval/run-1/report.json",
        "storage_eval/p08_hybrid_retrieval/run-2/report.json",
        "resources/retrieval_profiles/default_v1.json",
        "data/sample_files/教材-人工智能：从算法到系统.docx",
    )
    for relative in files:
        source = Path(relative)
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    governance_path = repository / "datasets/courserag_eval/v1/manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance["gold_components"]["ds5_qa"] = "pending_p09"
    governance["gold_components"].pop("ds5_context", None)
    governance["gold_status"] = "ds5_p08_retrieval_approved"
    governance["phase_input_status"]["p09"] = "candidate_review_pending"
    atomic_write_json(governance_path, governance)
    return repository


def test_generation_is_deterministic_and_approval_is_hash_bound(tmp_path: Path) -> None:
    repository = _copy_pre_p09_repo(tmp_path)
    first_result = generate_p09_candidates(repository_root=repository)
    first_bytes = {
        relative: (repository / relative).read_bytes()
        for relative in (
            "datasets/courserag_eval/v1/candidates/ds5/p09_qa_r1.json",
            "datasets/courserag_eval/v1/candidates/ds5/p09_context_r1.json",
            "datasets/courserag_eval/v1/provenance/p09_gold_bundle_manifest.json",
        )
    }
    second_result = generate_p09_candidates(repository_root=repository)
    assert first_result == second_result
    assert all((repository / path).read_bytes() == content for path, content in first_bytes.items())
    dataset_root = repository / "datasets/courserag_eval/v1"
    manifest = P09GoldBundleManifest.model_validate_json(
        (dataset_root / "provenance/p09_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    first_ids = [item for group in manifest.first_review_groups for item in group]
    first = P09ReviewDecisions(
        dataset_id="courserag-p09-review",
        dataset_version="r1",
        bundle_sha256=manifest.bundle_sha256,
        review_pass="first",
        expected_record_ids=first_ids,
        decisions=[P09ReviewDecision(record_id=item, decision="pass") for item in first_ids],
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 20, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    second = P09ReviewDecisions(
        dataset_id="courserag-p09-review",
        dataset_version="r1",
        bundle_sha256=manifest.bundle_sha256,
        review_pass="second",
        expected_record_ids=manifest.second_review_ids,
        decisions=[
            P09ReviewDecision(record_id=item, decision="pass")
            for item in manifest.second_review_ids
        ],
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 20, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    first_path = repository / "first.json"
    second_path = repository / "second.json"
    atomic_write_json(first_path, first.model_dump(mode="json"))
    atomic_write_json(second_path, second.model_dump(mode="json"))
    with pytest.raises(ValueError, match="literal P09"):
        approve_p09_bundle(
            dataset_root=dataset_root,
            expected_bundle_sha256="0" * 64,
            first_review_path=first_path,
            second_review_path=second_path,
            reviewer_id="course_owner",
            reviewed_at=datetime(2026, 8, 7, 20, 20, tzinfo=ZoneInfo("Asia/Shanghai")),
            review_id="p09-approval-test",
            notes="test approval",
        )
    result = approve_p09_bundle(
        dataset_root=dataset_root,
        expected_bundle_sha256=manifest.bundle_sha256,
        first_review_path=first_path,
        second_review_path=second_path,
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 20, 20, tzinfo=ZoneInfo("Asia/Shanghai")),
        review_id="p09-approval-test",
        notes="test approval",
    )
    replay = approve_p09_bundle(
        dataset_root=dataset_root,
        expected_bundle_sha256=manifest.bundle_sha256,
        first_review_path=first_path,
        second_review_path=second_path,
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 20, 20, tzinfo=ZoneInfo("Asia/Shanghai")),
        review_id="p09-approval-test",
        notes="test approval",
    )
    assert result == replay
    assert result["record_count"] == 200
    dev = load_p09_dev_bundle(dataset_root)
    assert len(dev.cases) == 60
    assert dev.retrieval_main_count == 54
    assert dev.upstream_gap_diagnostic_count == 6
    governance = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    assert governance["phase_input_status"]["p09"] == "formal_dev_eval_ready"
    assert (
        json.loads((dataset_root / "test.lock.json").read_text(encoding="utf-8"))["locked"] is False
    )


def test_p09_r2_atomic_claims_and_complete_obligation_coverage() -> None:
    r1_qa = P09QAGoldDataset.model_validate_json(
        (ROOT / "candidates/ds5/p09_qa_r1.json").read_text(encoding="utf-8")
    )
    r1_context = P09ContextGoldDataset.model_validate_json(
        (ROOT / "candidates/ds5/p09_context_r1.json").read_text(encoding="utf-8")
    )
    qa = P09QAGoldDataset.model_validate_json(
        (ROOT / "candidates/ds5/p09_qa_r2.json").read_text(encoding="utf-8")
    )
    context = P09ContextGoldDataset.model_validate_json(
        (ROOT / "candidates/ds5/p09_context_r2.json").read_text(encoding="utf-8")
    )
    coverage = P09CoverageAuditDataset.model_validate_json(
        (ROOT / "provenance/p09_answer_obligation_coverage_r2.json").read_text(encoding="utf-8")
    )
    manifest = P09GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p09_gold_bundle_manifest_r2.json").read_text(encoding="utf-8")
    )
    assert manifest.revision == 2
    assert len(manifest.semantic_changed_record_ids) == 18
    assert manifest.context_changed_record_ids == ["gold-qa-18b8640afc285e8d4ecebec3db23684f"]
    assert sum(item.audit_status == "complete" for item in coverage.cases) == 90
    assert sum(item.audit_status == "not_applicable_unanswerable" for item in coverage.cases) == 10
    assert all(not item.uncovered_obligation_ids for item in coverage.cases)
    r1_qa_hashes = {item.record_id: record_digest(item) for item in r1_qa.cases}
    r2_qa_hashes = {item.record_id: record_digest(item) for item in qa.cases}
    assert sum(r1_qa_hashes[item] == r2_qa_hashes[item] for item in r1_qa_hashes) == 82
    r1_context_hashes = {item.qa_case_id: record_digest(item) for item in r1_context.cases}
    r2_context_hashes = {item.qa_case_id: record_digest(item) for item in context.cases}
    assert (
        sum(r1_context_hashes[item] == r2_context_hashes[item] for item in r1_context_hashes) == 99
    )
    qa_by_id = {item.record_id: item for item in qa.cases}
    context_by_id = {item.qa_case_id: item for item in context.cases}
    for item in coverage.cases:
        if not item.answerable:
            continue
        claims = {claim.claim_id for claim in qa_by_id[item.qa_case_id].gold_claims}
        assert {
            claim for obligation in item.obligations for claim in obligation.claim_ids
        } == claims
    neighbor_supported = [
        support
        for item in qa.cases
        for claim in item.gold_claims
        for support in claim.evidence_supports
        if support.support_source == "necessary_neighbor"
    ]
    assert neighbor_supported
    for item in qa.cases:
        neighbors = {
            neighbor.neighbor_id: neighbor
            for neighbor in context_by_id[item.record_id].necessary_neighbors
        }
        for claim in item.gold_claims:
            for support in claim.evidence_supports:
                if support.support_source == "necessary_neighbor":
                    assert support.necessary_neighbor_id in neighbors
                    assert (
                        support.exact_support_excerpt
                        in neighbors[support.necessary_neighbor_id].text
                    )
    review_dir = Path(manifest.review_pack_relative_path)
    html = (review_dir / "index.html").read_text(encoding="utf-8")
    assert "r2 回答义务覆盖" in html
    assert "按 Required Claims 评分，并非 Gold 缺失" in html


def test_p09_r2_generation_and_approval_are_hash_bound(tmp_path: Path) -> None:
    repository = _copy_pre_p09_repo(tmp_path)
    dataset_root = repository / "datasets/courserag_eval/v1"
    shutil.copy2(
        dataset_root / "provenance/p09_gold_bundle_manifest_r1.json",
        dataset_root / "provenance/p09_gold_bundle_manifest.json",
    )
    r1_manifest = P09GoldBundleManifest.model_validate_json(
        (dataset_root / "provenance/p09_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    record_owner_attestation(
        dataset_root=dataset_root,
        expected_bundle_sha256=r1_manifest.bundle_sha256,
        reviewer_id="course_owner",
        notes="Course Owner explicitly attested that both r1 review passes were complete.",
    )
    first_build = build_r2(repository_root=repository)
    first_bytes = {
        relative: (repository / relative).read_bytes()
        for relative in (
            "datasets/courserag_eval/v1/candidates/ds5/p09_qa_r2.json",
            "datasets/courserag_eval/v1/candidates/ds5/p09_context_r2.json",
            "datasets/courserag_eval/v1/provenance/p09_answer_obligation_coverage_r2.json",
            "datasets/courserag_eval/v1/provenance/p09_gold_bundle_manifest_r2.json",
        )
    }
    second_build = build_r2(repository_root=repository)
    assert first_build == second_build
    assert all((repository / path).read_bytes() == content for path, content in first_bytes.items())
    manifest = P09GoldBundleManifest.model_validate_json(
        (dataset_root / "provenance/p09_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    first_ids = [item for group in manifest.first_review_groups for item in group]
    first = P09ReviewDecisions(
        dataset_id="courserag-p09-r2-review-first",
        dataset_version="r2",
        bundle_sha256=manifest.bundle_sha256,
        review_pass="first",
        expected_record_ids=first_ids,
        decisions=[P09ReviewDecision(record_id=item, decision="pass") for item in first_ids],
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 21, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    second = P09ReviewDecisions(
        dataset_id="courserag-p09-r2-review-second",
        dataset_version="r2",
        bundle_sha256=manifest.bundle_sha256,
        review_pass="second",
        expected_record_ids=manifest.second_review_ids,
        decisions=[
            P09ReviewDecision(record_id=item, decision="pass")
            for item in manifest.second_review_ids
        ],
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 21, 10, tzinfo=ZoneInfo("Asia/Shanghai")),
    )
    first_path = repository / "p09-r2-first.json"
    second_path = repository / "p09-r2-second.json"
    atomic_write_json(first_path, first.model_dump(mode="json"))
    atomic_write_json(second_path, second.model_dump(mode="json"))
    result = approve_p09_bundle(
        dataset_root=dataset_root,
        expected_bundle_sha256=manifest.bundle_sha256,
        first_review_path=first_path,
        second_review_path=second_path,
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 7, 21, 20, tzinfo=ZoneInfo("Asia/Shanghai")),
        review_id="p09-r2-approval-test",
        notes="test P09 r2 approval",
    )
    assert result["record_count"] == 200
