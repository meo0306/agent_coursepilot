from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS3SectionScopeDataset,
    DS3SplitManifest,
    P07GoldBundleApproval,
    P07GoldBundleManifest,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.ds3_p07_approval import approve_p07_bundle

ROOT = Path("datasets/courserag_eval/v1")


def test_p07_candidate_bundle_is_complete_and_hash_bound() -> None:
    candidate_path = ROOT / "candidates/ds3/p07_knowledge_points_r1.json"
    support_path = ROOT / "candidates/ds2/p07_kp_support_r1.json"
    scopes_path = ROOT / "provenance/ds3_p07_section_scopes.json"
    split_path = ROOT / "provenance/ds3_p07_split.json"
    manifest = P07GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p07_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    candidate = DS3KnowledgePointDataset.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    support = DS2EvidenceDataset.model_validate_json(support_path.read_text(encoding="utf-8"))
    scopes = DS3SectionScopeDataset.model_validate_json(scopes_path.read_text(encoding="utf-8"))
    split = DS3SplitManifest.model_validate_json(split_path.read_text(encoding="utf-8"))

    assert 80 <= len(candidate.knowledge_points) <= 120
    assert len(scopes.scopes) == 24
    assert Counter(scope.course_id for scope in scopes.scopes) == {
        "course_ai_algorithms_systems": 16,
        "course_ai_general_education": 8,
    }
    assert support.evidence == []
    assert manifest.knowledge_point_candidate.sha256 == sha256_file(candidate_path)
    assert manifest.support_candidate.sha256 == sha256_file(support_path)
    assert manifest.candidate_record_sha256 == {
        item.gold_kp_id: record_digest(item) for item in candidate.knowledge_points
    }
    assert set(split.calibration_ids) | set(split.holdout_ids) == {
        item.gold_kp_id for item in candidate.knowledge_points
    }
    family_side = {}
    for item in candidate.knowledge_points:
        side = "calibration" if item.gold_kp_id in split.calibration_ids else "holdout"
        assert family_side.setdefault(item.concept_family_id, side) == side


def test_p07_candidate_has_resolvable_primary_evidence_and_no_approved_leakage() -> None:
    candidate = DS3KnowledgePointDataset.model_validate_json(
        (ROOT / "candidates/ds3/p07_knowledge_points_r1.json").read_text(encoding="utf-8")
    )
    ds2 = DS2EvidenceDataset.model_validate_json(
        (ROOT / "approved/ds2/p06_evidence.json").read_text(encoding="utf-8")
    )
    evidence = {item.evidence_id: item for item in ds2.evidence}
    normalized_names: set[tuple[str, str]] = set()
    for item in candidate.knowledge_points:
        assert item.review_status.value == "candidate"
        assert item.approval is None
        assert item.evidence_ids[0] in evidence
        assert item.summary == evidence[item.evidence_ids[0]].gold_text
        assert item.evidence_links[0].evidence_record_sha256 == record_digest(
            evidence[item.evidence_ids[0]]
        )
        source_key = (item.course_id, evidence[item.evidence_ids[0]].source_span.section_path[-1])
        assert item.source_scope_ids == [
            (
                "ds3-scope-docx-"
                if item.course_id == "course_ai_algorithms_systems"
                else "ds3-scope-pdf-"
            )
            + source_key[1].replace(".", "-")
        ]
        name_key = (item.course_id, item.normalized_name or "")
        assert name_key not in normalized_names
        normalized_names.add(name_key)
        assert evidence[item.evidence_ids[0]].source_span.document_id in {
            "doc_ai_algorithms_systems",
            "doc_ai_general_education_excerpt",
        }


def test_p07_review_assets_are_complete_and_hash_bound() -> None:
    manifest = P07GoldBundleManifest.model_validate_json(
        (ROOT / "provenance/p07_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    pack = Path(manifest.review_pack_relative_path)
    assert sha256_file(pack / "index.html") == manifest.review_pack_index_sha256
    assert sha256_file(pack / "second_review.html") == manifest.second_review_index_sha256
    assert len(manifest.review_asset_sha256) == 107
    for kp_id, digest in manifest.review_asset_sha256.items():
        assert sha256_file(pack / "assets" / f"{kp_id}.png") == digest


def test_p07_global_dev_test_follow_later_governance_and_preserve_consumed_lock() -> None:
    governance = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    dev_ids = (ROOT / "splits/dev_ids.txt").read_text(encoding="utf-8").split()
    test_ids = (ROOT / "splits/test_ids.txt").read_text(encoding="utf-8").split()
    if governance["gold_components"].get("ds5_retrieval") == "approved":
        assert len(dev_ids) == 60 and len(test_ids) == 40
    else:
        assert not dev_ids and not test_ids
    lock = json.loads((ROOT / "test.lock.json").read_text(encoding="utf-8"))
    assert lock["locked"] is True
    assert lock["test_ids_sha256"]


def test_p07_approval_rejects_wrong_bundle_hash_before_writing(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    import pytest

    approved_path = ROOT / "approved/ds3/p07_knowledge_points.json"
    approved_before = sha256_file(approved_path)
    with pytest.raises(ValueError, match="literal P07 Gold Bundle"):
        approve_p07_bundle(
            dataset_root=ROOT,
            expected_bundle_sha256="0" * 64,
            first_review_path=tmp_path / "missing-first.json",
            second_review_path=tmp_path / "missing-second.json",
            reviewer_id="course_owner",
            reviewed_at=datetime.now(UTC),
            review_id="p07-test-rejected",
            notes="must not write",
        )
    assert sha256_file(approved_path) == approved_before


def test_p07_approved_bundle_is_fully_human_approved() -> None:
    approved = DS3KnowledgePointDataset.model_validate_json(
        (ROOT / "approved/ds3/p07_knowledge_points.json").read_text(encoding="utf-8")
    )
    batch = P07GoldBundleApproval.model_validate_json(
        (ROOT / "provenance/p07_gold_bundle_approval.json").read_text(encoding="utf-8")
    )
    assert len(approved.knowledge_points) == 107
    assert all(item.review_status.value == "approved" for item in approved.knowledge_points)
    assert all(item.approval is not None for item in approved.knowledge_points)
    assert batch.bundle_sha256 == (
        "2ebd8f96bb8bd6f0c178dce7545ef991cceb181c6cfe2a3554592bc3daf10400"
    )
    assert batch.approved_knowledge_points.sha256 == sha256_file(
        ROOT / "approved/ds3/p07_knowledge_points.json"
    )
    support = DS2EvidenceDataset.model_validate_json(
        (ROOT / "approved/ds2/p07_kp_support.json").read_text(encoding="utf-8")
    )
    assert support.evidence == []
