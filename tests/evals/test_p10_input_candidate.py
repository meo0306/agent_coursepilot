from __future__ import annotations

import json
import shutil
import zipfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from evaluation.contracts import ReviewStatus
from evaluation.contracts import TestLock as EvalTestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json
from evaluation.p10_approval import approve_p10_bundle
from evaluation.p10_input_data import bundle_identity_sha256
from evaluation.p10_review_attestation import record_owner_attestation
from evaluation.p10_schemas import (
    P10BundleApproval,
    P10BundleManifest,
    P10DS6Dataset,
    P10DS7Dataset,
    P10DS8Dataset,
    P10FixtureManifest,
    P10ReviewDecision,
    P10ReviewDecisions,
    P10SecurityDataset,
)

ROOT = Path("datasets/courserag_eval/v1")


def _load() -> tuple[
    P10DS6Dataset,
    P10DS7Dataset,
    P10DS8Dataset,
    P10SecurityDataset,
    P10BundleManifest,
]:
    return (
        P10DS6Dataset.model_validate_json(
            (ROOT / "candidates/ds6/p10_citation_migration_r1.json").read_text(encoding="utf-8")
        ),
        P10DS7Dataset.model_validate_json(
            (ROOT / "candidates/ds7/p10_incremental_writeback_r1.json").read_text(encoding="utf-8")
        ),
        P10DS8Dataset.model_validate_json(
            (ROOT / "candidates/ds8/p10_performance_workloads_r1.json").read_text(encoding="utf-8")
        ),
        P10SecurityDataset.model_validate_json(
            (ROOT / "candidates/security/p10_security_fault_r1.json").read_text(encoding="utf-8")
        ),
        P10BundleManifest.model_validate_json(
            (ROOT / "provenance/p10_input_bundle_manifest.json").read_text(encoding="utf-8")
        ),
    )


def test_p10_exact_scope_statuses_and_test_boundary() -> None:
    ds6, ds7, ds8, security, manifest = _load()
    assert (len(ds6.cases), len(ds7.cases), len(ds8.cases), len(security.cases)) == (9, 12, 20, 16)
    assert sum(len(item.judgments) for item in ds6.cases) == 24
    assert Counter(
        judgment.expected_status for case in ds6.cases for judgment in case.judgments
    ) == {"valid": 5, "migrated": 11, "needs_review": 6, "invalid": 2}
    assert Counter(item.split for item in ds6.cases) == {"dev": 5, "test": 4}
    assert Counter(item.split for item in ds7.cases) == {"dev": 7, "test": 5}
    assert Counter(item.split for item in security.cases) == {"dev": 10, "test": 6}
    assert all(
        item.review_status is ReviewStatus.CANDIDATE and item.approval is None
        for dataset in (ds6, ds7, ds8, security)
        for item in dataset.cases
    )
    assert all(not item.searchable for item in ds6.cases)
    assert all(not item.semantic_content for item in security.cases)
    assert all(item.resolved_test_query_count == 0 for item in ds8.cases)
    assert all(item.test_id_resolution == "deferred_until_test_lock" for item in ds8.cases)
    assert {
        item.resolved_dev_query_count for item in ds8.cases if item.workload_domain == "online"
    } == {60}
    assert bundle_identity_sha256(manifest) == manifest.bundle_sha256
    assert manifest.review_ui_revision == 2
    assert len(manifest.first_review_ids) == 57
    assert len(manifest.second_review_ids) == 29
    assert (
        EvalTestLock.model_validate_json(
            (ROOT / "test.lock.json").read_text(encoding="utf-8")
        ).locked
        is False
    )
    review_html = (Path(manifest.review_pack_relative_path) / "index.html").read_text(
        encoding="utf-8"
    )
    for expected in (
        "审核页面版本：v2",
        "增量影响矩阵",
        "应复用产物",
        "应失效/重建产物",
        "富化触发探针",
        "工作负载配置",
        "当前解析 Test Query",
        "Test ID 解析",
        "安全控制预期",
        "通过条件",
        "退回条件",
    ):
        assert expected in review_html
    assert "p10-ds7-12-manual-enrichment" in review_html
    assert "所有自动阈值未达到时，人工触发仍必须生效" in review_html
    assert "p10-ds8-full-build-cold" in review_html
    assert "六个隔离的单文档 Build" in review_html


def test_p10_source_grounding_writeback_and_security_controls() -> None:
    ds6, ds7, _, security, manifest = _load()
    primary_document_ids = {
        "doc_ai_algorithms_systems",
        "doc_ai_general_education_excerpt",
    }
    for case in ds6.cases:
        for judgment in case.judgments:
            assert judgment.old_anchor.source_span.document_id in primary_document_ids
            assert (
                judgment.old_anchor.exact_text_sha256
                == __import__("hashlib")
                .sha256(judgment.old_anchor.exact_text.encode("utf-8"))
                .hexdigest()
            )
    lifecycle = next(item for item in ds7.cases if item.operation == "writeback_lifecycle")
    assert len(lifecycle.writeback_payloads) == 10
    assert Counter(item.content_type for item in lifecycle.writeback_payloads) == {
        "verified_question": 4,
        "verified_answer_explanation": 3,
        "verified_lesson_fragment": 3,
    }
    assert Counter(item.course_id for item in lifecycle.writeback_payloads) == {
        "course_ai_algorithms_systems": 7,
        "course_ai_general_education": 3,
    }
    assert len({item.idempotency_key for item in lifecycle.writeback_payloads}) == 10
    assert lifecycle.expected_duplicate_writes == lifecycle.expected_primary_overwrites == 0
    automatic = next(
        item for item in ds7.cases if item.operation == "automatic_enrichment_boundaries"
    )
    assert {
        item.trigger_reason for item in automatic.enrichment_probes if item.expected_trigger
    } == {
        "record_count",
        "token_count",
        "age",
    }
    assert any(
        item.token_count < 3000 and not item.expected_trigger
        for item in automatic.enrichment_probes
    )
    assert any(
        item.token_count >= 3000 and item.expected_trigger for item in automatic.enrichment_probes
    )
    assert all(
        item.expected_database_writes == 0 and item.expected_artifacts == 0
        for item in security.cases
    )
    assert len(manifest.upstream_approved) == 8
    assert len(manifest.preserved_p09) == 4


def test_p10_fixture_binaries_are_hash_bound_and_bounded() -> None:
    import fitz

    manifest = P10FixtureManifest.model_validate_json(
        (ROOT / "provenance/p10_fixture_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest.semantic_source_count == 2
    fixtures = {item.fixture_id: item for item in manifest.fixtures}
    assert len(fixtures) == 15
    for item in fixtures.values():
        path = Path(item.artifact.path)
        assert sha256_file(path) == item.artifact.sha256
        assert item.searchable is False
    blank = fitz.open(fixtures["p10-fixture-pdf-blank-insert"].artifact.path)
    replaced = fitz.open(fixtures["p10-fixture-pdf-ocr-replaced"].artifact.path)
    encrypted = fitz.open(fixtures["p10-security-encrypted"].artifact.path)
    assert blank.page_count == 33
    assert replaced.page_count == 32
    assert encrypted.needs_pass
    blank.close()
    replaced.close()
    encrypted.close()
    with zipfile.ZipFile(fixtures["p10-security-zip-traversal"].artifact.path) as archive:
        assert archive.namelist() == ["../p10-sentinel.txt"]
    assert fixtures["p10-security-compression"].artifact.size_bytes < 4096


def _copy_approval_repository(tmp_path: Path, manifest: P10BundleManifest) -> Path:
    repository = tmp_path / "repo"
    fixture_manifest = P10FixtureManifest.model_validate_json(
        Path(manifest.fixture_manifest.path).read_text(encoding="utf-8")
    )
    artifact_paths = [
        *(item.path for item in manifest.candidates.values()),
        manifest.fixture_manifest.path,
        manifest.component_splits.path,
        manifest.test_freeze_protocol.path,
        *(item.path for item in manifest.upstream_approved.values()),
        *(item.path for item in manifest.preserved_p09.values()),
        *(item.artifact.path for item in fixture_manifest.fixtures),
        f"{manifest.review_pack_relative_path}/index.html",
        f"{manifest.review_pack_relative_path}/second_review.html",
        "datasets/courserag_eval/v1/test.lock.json",
        "datasets/courserag_eval/v1/manifest.json",
        "datasets/courserag_eval/v1/provenance/p10_input_bundle_manifest.json",
        "datasets/courserag_eval/v1/reviews/review_log.jsonl",
    ]
    for relative in artifact_paths:
        source = Path(relative)
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return repository


def _decisions(manifest: P10BundleManifest, review_pass: str) -> P10ReviewDecisions:
    ids = manifest.first_review_ids if review_pass == "first" else manifest.second_review_ids
    return P10ReviewDecisions(
        dataset_id="courserag-p10-review",
        dataset_version="r1",
        bundle_sha256=manifest.bundle_sha256,
        review_pass=review_pass,
        expected_record_ids=ids,
        decisions=[P10ReviewDecision(record_id=item, decision="pass") for item in ids],
        reviewer_id="course_owner",
        reviewed_at=datetime(2026, 8, 10, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
    )


def test_p10_approval_is_hash_bound_complete_and_idempotent(tmp_path: Path) -> None:
    *_, manifest = _load()
    repository = _copy_approval_repository(tmp_path, manifest)
    dataset_root = repository / "datasets/courserag_eval/v1"
    first_path = repository / "first.json"
    second_path = repository / "second.json"
    atomic_write_json(first_path, _decisions(manifest, "first").model_dump(mode="json"))
    atomic_write_json(second_path, _decisions(manifest, "second").model_dump(mode="json"))
    reviewed_at = datetime(2026, 8, 10, 12, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
    with pytest.raises(ValueError, match="literal P10"):
        approve_p10_bundle(
            dataset_root=dataset_root,
            expected_bundle_sha256="0" * 64,
            first_review_path=first_path,
            second_review_path=second_path,
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
            review_id="p10-input-owner-approval-test.001",
            notes="test",
        )
    first = approve_p10_bundle(
        dataset_root=dataset_root,
        expected_bundle_sha256=manifest.bundle_sha256,
        first_review_path=first_path,
        second_review_path=second_path,
        reviewer_id="course_owner",
        reviewed_at=reviewed_at,
        review_id="p10-input-owner-approval-test.001",
        notes="test",
    )
    second = approve_p10_bundle(
        dataset_root=dataset_root,
        expected_bundle_sha256=manifest.bundle_sha256,
        first_review_path=first_path,
        second_review_path=second_path,
        reviewer_id="course_owner",
        reviewed_at=reviewed_at,
        review_id="p10-input-owner-approval-test.001",
        notes="test",
    )
    assert first == second
    assert first["approved_records"] == 57
    assert first["test_locked"] is False
    assert (
        EvalTestLock.model_validate_json(
            (dataset_root / "test.lock.json").read_text(encoding="utf-8")
        ).locked
        is False
    )
    governance = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    assert governance["phase_input_status"]["p10"] == "formal_dev_eval_ready"


def test_p10_review_decisions_reject_missing_or_unexplained_returns() -> None:
    *_, manifest = _load()
    first_id = manifest.first_review_ids[0]
    with pytest.raises(ValueError, match="require notes"):
        P10ReviewDecision(record_id=first_id, decision="return")
    with pytest.raises(ValueError, match="exactly cover"):
        P10ReviewDecisions(
            dataset_id="courserag-p10-review",
            dataset_version="r1",
            bundle_sha256=manifest.bundle_sha256,
            review_pass="first",
            expected_record_ids=[first_id],
            decisions=[],
        )


def test_p10_owner_conversation_attestation_is_exact_and_hash_bound(
    tmp_path: Path,
) -> None:
    *_, manifest = _load()
    repository = _copy_approval_repository(tmp_path, manifest)
    dataset_root = repository / "datasets/courserag_eval/v1"
    statement = "全部审核通过，没有需要修改的内容，就不导出JSON了"
    reviewed_at = datetime(2026, 8, 10, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
    with pytest.raises(ValueError, match="literal P10"):
        record_owner_attestation(
            dataset_root=dataset_root,
            expected_bundle_sha256="0" * 64,
            statement=statement,
            reviewer_id="course_owner",
            reviewed_at=reviewed_at,
        )
    result = record_owner_attestation(
        dataset_root=dataset_root,
        expected_bundle_sha256=manifest.bundle_sha256,
        statement=statement,
        reviewer_id="course_owner",
        reviewed_at=reviewed_at,
    )
    first = P10ReviewDecisions.model_validate_json(
        Path(result["first_review_path"]).read_text(encoding="utf-8")
    )
    second = P10ReviewDecisions.model_validate_json(
        Path(result["second_review_path"]).read_text(encoding="utf-8")
    )
    assert first.attestation_source == "course_owner_conversation_attestation"
    assert first.attestation_statement == statement
    assert first.attestation_statement_sha256 == result["attestation_statement_sha256"]
    assert len(first.decisions) == 57
    assert len(second.decisions) == 29
    assert all(item.decision == "pass" for item in (*first.decisions, *second.decisions))


def test_p10_repository_approval_preserves_candidates_and_unlocked_test() -> None:
    *_, manifest = _load()
    approval = P10BundleApproval.model_validate_json(
        (ROOT / "provenance/p10_input_bundle_approval.json").read_text(encoding="utf-8")
    )
    assert approval.bundle_sha256 == manifest.bundle_sha256
    assert approval.candidates == manifest.candidates
    approved_models = {
        "ds6": P10DS6Dataset,
        "ds7": P10DS7Dataset,
        "ds8": P10DS8Dataset,
        "security": P10SecurityDataset,
    }
    total = 0
    for component, model in approved_models.items():
        artifact = approval.approved[component]
        assert sha256_file(Path(artifact.path)) == artifact.sha256
        dataset = model.model_validate_json(Path(artifact.path).read_text(encoding="utf-8"))
        candidate = model.model_validate_json(
            Path(manifest.candidates[component].path).read_text(encoding="utf-8")
        )
        candidate_hashes = {item.record_id: record_digest(item) for item in candidate.cases}
        total += len(dataset.cases)
        assert all(
            item.review_status is ReviewStatus.APPROVED
            and item.approval is not None
            and item.approval.candidate_sha256 == candidate_hashes[item.record_id]
            for item in dataset.cases
        )
    assert total == 57
    for artifact in (approval.first_review_decisions, approval.second_review_decisions):
        decisions = P10ReviewDecisions.model_validate_json(
            Path(artifact.path).read_text(encoding="utf-8")
        )
        assert decisions.attestation_source == "course_owner_conversation_attestation"
        assert decisions.attestation_statement == "全部审核通过，没有需要修改的内容，就不导出JSON了"
    review_ids = [
        json.loads(line)["review_id"]
        for line in (ROOT / "reviews/review_log.jsonl").read_text(encoding="utf-8").splitlines()
        if line and json.loads(line)["review_id"].startswith(f"{approval.review_id}.")
    ]
    assert len(review_ids) == len(set(review_ids)) == 57
    governance = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    assert governance["gold_status"] == "p10_input_gold_approved"
    assert governance["phase_input_status"]["p09"] == "completed_gate_passed"
    assert governance["phase_input_status"]["p10"] == "formal_dev_eval_ready"
    assert not EvalTestLock.model_validate_json(
        (ROOT / "test.lock.json").read_text(encoding="utf-8")
    ).locked
