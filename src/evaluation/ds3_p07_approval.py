"""Atomically promote one exact, twice-reviewed P07 Gold bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import (
    DS2EvidenceDataset,
    DS3KnowledgePointDataset,
    DS3ReviewDecisions,
    KnowledgePointRecord,
    P07GoldBundleApproval,
    P07GoldBundleManifest,
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


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError("P07 approval artifacts must stay under the repository")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _append_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with a newline")
    existing = {
        entry.review_id: entry
        for line in existing_text.splitlines()
        if line.strip()
        for entry in [ReviewLogEntry.model_validate_json(line)]
    }
    new_lines: list[str] = []
    for addition in additions:
        current = existing.get(addition.review_id)
        if current is not None and current != addition:
            raise ValueError("existing P07 review log entry differs")
        if current is None:
            new_lines.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(new_lines))


def approve_p07_bundle(
    *,
    dataset_root: Path,
    expected_bundle_sha256: str,
    first_review_path: Path,
    second_review_path: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, object]:
    dataset_root = dataset_root.resolve()
    repository_root = dataset_root.parent.parent.parent
    manifest_path = dataset_root / "provenance/p07_gold_bundle_manifest.json"
    bundle = P07GoldBundleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if bundle.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P07 Gold Bundle SHA-256 does not match")
    kp_path = repository_root / bundle.knowledge_point_candidate.path
    support_path = repository_root / bundle.support_candidate.path
    for expected, path in (
        (bundle.knowledge_point_candidate, kp_path),
        (bundle.support_candidate, support_path),
        (bundle.section_scopes, repository_root / bundle.section_scopes.path),
        (bundle.split_manifest, repository_root / bundle.split_manifest.path),
        (bundle.generation_policy, repository_root / bundle.generation_policy.path),
    ):
        if sha256_file(path) != expected.sha256:
            raise ValueError(f"P07 bundle artifact changed: {expected.path}")
    for artifact in bundle.source_artifacts:
        if sha256_file(repository_root / artifact.path) != artifact.sha256:
            raise ValueError(f"P07 source artifact changed: {artifact.path}")
    upstream_paths = {
        "ds1_p04": dataset_root / "approved/ds1/p04_native_docx.json",
        "ds1_p05": dataset_root / "approved/ds1/p05_ocr.json",
        "ds2_p06": dataset_root / "approved/ds2/p06_evidence.json",
    }
    for name, path in upstream_paths.items():
        if sha256_file(path) != bundle.upstream_approved_file_sha256[name]:
            raise ValueError(f"upstream Approved artifact changed: {name}")
    if (
        sha256_file(dataset_root / "approved/ds2/p06_evidence.json")
        != bundle.preserved_p06_artifact_sha256["approved_ds2"]
    ):
        raise ValueError("Approved P06 DS2 changed after P07 Candidate generation")
    if (
        sha256_file(dataset_root / "provenance/ds2_p06_approval.json")
        != bundle.preserved_p06_artifact_sha256["approval"]
    ):
        raise ValueError("P06 approval changed after P07 Candidate generation")
    if (
        sha256_file(repository_root / "storage_eval/p06_b1_b2/run-4/system_outputs.json")
        != bundle.preserved_p06_artifact_sha256["b1_b2_system_outputs"]
    ):
        raise ValueError("P06 B1/B2 system output changed after P07 Candidate generation")
    review_pack = repository_root / bundle.review_pack_relative_path
    if sha256_file(review_pack / "index.html") != bundle.review_pack_index_sha256:
        raise ValueError("P07 first-review package changed")
    if sha256_file(review_pack / "second_review.html") != bundle.second_review_index_sha256:
        raise ValueError("P07 second-review package changed")
    for kp_id, expected_hash in bundle.review_asset_sha256.items():
        if sha256_file(review_pack / "assets" / f"{kp_id}.png") != expected_hash:
            raise ValueError(f"P07 review asset changed: {kp_id}")

    candidate = DS3KnowledgePointDataset.model_validate_json(kp_path.read_text(encoding="utf-8"))
    support = DS2EvidenceDataset.model_validate_json(support_path.read_text(encoding="utf-8"))
    candidate_hashes = {item.gold_kp_id: record_digest(item) for item in candidate.knowledge_points}
    support_hashes = {item.evidence_id: record_digest(item) for item in support.evidence}
    if (
        candidate_hashes != bundle.candidate_record_sha256
        or support_hashes != bundle.support_record_sha256
    ):
        raise ValueError("P07 Candidate record hashes differ from the Bundle Manifest")
    if any(
        item.review_status is not ReviewStatus.CANDIDATE
        for item in candidate.knowledge_points + support.evidence
    ):
        raise ValueError("P07 approval accepts Candidate records only")

    first = DS3ReviewDecisions.model_validate_json(first_review_path.read_text(encoding="utf-8"))
    second = DS3ReviewDecisions.model_validate_json(second_review_path.read_text(encoding="utf-8"))
    for decision, pass_name, expected_ids in (
        (first, "first", bundle.first_review_ids),
        (second, "second", bundle.second_review_ids),
    ):
        if decision.bundle_sha256 != bundle.bundle_sha256 or decision.review_pass != pass_name:
            raise ValueError(f"{pass_name} P07 review targets a different bundle/pass")
        if decision.expected_record_ids != expected_ids:
            raise ValueError(f"{pass_name} P07 review expected IDs differ from Manifest")
        if decision.returned_record_ids or set(decision.reviewed_record_ids) != set(expected_ids):
            raise ValueError(f"{pass_name} P07 review is incomplete or contains returns")
        if decision.reviewer_id is not None and decision.reviewer_id != reviewer_id:
            raise ValueError(f"{pass_name} P07 reviewer differs from approval reviewer")
        if decision.reviewed_at is not None and decision.reviewed_at > reviewed_at:
            raise ValueError(f"{pass_name} P07 review timestamp is after batch approval")

    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("P07 approval cannot alter a locked Test dataset")
    for split_name in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split_name).read_text(encoding="utf-8").strip():
            raise ValueError("P07 approval requires empty global Dev/Test splits")

    approved_records: list[KnowledgePointRecord] = []
    approved_hashes: dict[str, str] = {}
    logs: list[ReviewLogEntry] = []
    for index, record in enumerate(candidate.knowledge_points, 1):
        item_review_id = f"{review_id}.kp.{index:03d}"
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_hash = record_digest(provisional)
        values = provisional.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=item_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_hashes[record.gold_kp_id],
            approved_record_sha256=approved_hash,
            notes=notes,
        )
        approved = KnowledgePointRecord.model_validate(values)
        approved_records.append(approved)
        approved_hashes[record.gold_kp_id] = approved_hash
        logs.append(
            ReviewLogEntry(
                review_id=item_review_id,
                record_id=record.gold_kp_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_hashes[record.gold_kp_id],
                resulting_record_sha256=approved_hash,
                notes=notes,
            )
        )
    approved_kp = DS3KnowledgePointDataset(
        dataset_id=candidate.dataset_id,
        dataset_version=candidate.dataset_version,
        knowledge_points=approved_records,
    )
    approved_support = DS2EvidenceDataset(
        dataset_id=support.dataset_id, dataset_version=support.dataset_version, evidence=[]
    )
    approved_kp_path = dataset_root / "approved/ds3/p07_knowledge_points.json"
    approved_support_path = dataset_root / "approved/ds2/p07_kp_support.json"
    for path, value in ((approved_kp_path, approved_kp), (approved_support_path, approved_support)):
        if path.exists():
            if json.loads(path.read_text(encoding="utf-8")) != value.model_dump(mode="json"):
                raise ValueError(f"existing Approved P07 artifact differs: {path}")
        else:
            atomic_write_json(path, value.model_dump(mode="json"))
    batch = P07GoldBundleApproval(
        dataset_id="courserag-p07-gold-bundle",
        dataset_version="p07-r1",
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        bundle_sha256=bundle.bundle_sha256,
        knowledge_point_candidate=bundle.knowledge_point_candidate,
        support_candidate=bundle.support_candidate,
        candidate_record_sha256=candidate_hashes,
        support_record_sha256=support_hashes,
        first_review_decisions=_artifact(repository_root, first_review_path),
        second_review_decisions=_artifact(repository_root, second_review_path),
        approved_knowledge_points=_artifact(repository_root, approved_kp_path),
        approved_support=_artifact(repository_root, approved_support_path),
        approved_record_sha256=approved_hashes,
        approved_support_record_sha256={},
        notes=notes,
    )
    approval_path = dataset_root / "provenance/p07_gold_bundle_approval.json"
    if approval_path.exists():
        if (
            P07GoldBundleApproval.model_validate_json(approval_path.read_text(encoding="utf-8"))
            != batch
        ):
            raise ValueError("existing P07 bundle approval differs")
    else:
        atomic_write_json(approval_path, batch.model_dump(mode="json"))
    _append_log(dataset_root / "reviews/review_log.jsonl", logs)
    history_path = dataset_root / "provenance/ds3_p07_candidate_revision_history.json"
    history = CandidateRevisionHistory.model_validate_json(history_path.read_text(encoding="utf-8"))
    current = [
        entry
        for entry in history.revisions
        if entry.candidate_file_sha256 == bundle.knowledge_point_candidate.sha256
    ]
    if len(current) != 1 or current[0].status not in {
        "pending_course_owner_review",
        "approved",
    }:
        raise ValueError("P07 Candidate revision history differs from approved Candidate")
    approved_history = history.model_copy(
        update={
            "revisions": [
                entry.model_copy(update={"status": "approved"}) if entry == current[0] else entry
                for entry in history.revisions
            ]
        }
    )
    atomic_write_json(history_path, approved_history.model_dump(mode="json"))
    project_manifest_path = dataset_root / "manifest.json"
    project_manifest = json.loads(project_manifest_path.read_text(encoding="utf-8"))
    project_manifest.setdefault("gold_components", {}).update(
        {"ds3": "approved", "ds2_p07_kp_support": "approved"}
    )
    project_manifest["gold_status"] = "ds3_p07_knowledge_points_approved"
    project_manifest.setdefault("phase_input_status", {})["p06"] = "completed_gate_passed"
    project_manifest["phase_input_status"]["p07"] = "formal_eval_ready"
    atomic_write_json(project_manifest_path, project_manifest)
    return {
        "bundle_sha256": bundle.bundle_sha256,
        "approved_record_count": len(approved_records),
        "approval_sha256": sha256_file(approval_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Approve an exact, twice-reviewed P07 Gold bundle."
    )
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-bundle-sha256", required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_p07_bundle(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.expected_bundle_sha256,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
