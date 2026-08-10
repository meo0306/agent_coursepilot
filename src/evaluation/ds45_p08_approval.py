"""Approve one exact, twice-reviewed P08 DS4/DS5 retrieval-only Gold bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import (
    DS4QueryProcessingDataset,
    DS5RetrievalQADataset,
    P08GoldBundleApproval,
    P08GoldBundleManifest,
    P08ReviewDecisions,
)
from evaluation.contracts import (
    ApprovalRecord,
    HashedArtifact,
    ReviewLogEntry,
    ReviewStatus,
    TestLock,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.ds45_p08_data import bundle_identity_sha256
from evaluation.io import atomic_write_json, atomic_write_text


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError("P08 approval artifacts must stay under the repository")
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
        item.review_id: item
        for line in existing_text.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    new_lines: list[str] = []
    for addition in additions:
        current = existing.get(addition.review_id)
        if current is not None and current != addition:
            raise ValueError("existing P08 review log entry differs")
        if current is None:
            new_lines.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(new_lines))


def _validate_artifact(repository_root: Path, artifact: HashedArtifact) -> Path:
    path = repository_root / artifact.path
    if sha256_file(path) != artifact.sha256 or path.stat().st_size != artifact.size_bytes:
        raise ValueError(f"P08 bundle artifact changed: {artifact.path}")
    return path


def approve_p08_bundle(
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
    manifest_path = dataset_root / "provenance/p08_gold_bundle_manifest.json"
    bundle = P08GoldBundleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if bundle.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P08 Gold Bundle SHA-256 does not match")
    recomputed = bundle_identity_sha256(
        revision=bundle.revision,
        ds4_sha256=bundle.ds4_candidate.sha256,
        ds5_sha256=bundle.ds5_candidate.sha256,
        source_packages_sha256=bundle.source_packages.sha256,
        split_sha256=bundle.split_manifest.sha256,
        candidate_record_sha256=bundle.candidate_record_sha256,
        upstream_approved_sha256=bundle.upstream_approved_sha256,
        preserved_upstream_sha256=bundle.preserved_upstream_sha256,
        p06_unmapped_evidence_ids=bundle.p06_unmapped_evidence_ids,
        diagnostic_evidence_ids=bundle.diagnostic_evidence_ids,
        first_review_groups=bundle.first_review_groups,
        second_review_ids=bundle.second_review_ids,
    )
    if recomputed != bundle.bundle_sha256:
        raise ValueError("P08 Bundle identity fields do not match bundle_sha256")
    ds4_path = _validate_artifact(repository_root, bundle.ds4_candidate)
    ds5_path = _validate_artifact(repository_root, bundle.ds5_candidate)
    _validate_artifact(repository_root, bundle.source_packages)
    split_path = _validate_artifact(repository_root, bundle.split_manifest)

    upstream_paths = {
        "approved_ds2_p06": dataset_root / "approved/ds2/p06_evidence.json",
        "approved_ds3_p07": dataset_root / "approved/ds3/p07_knowledge_points.json",
        "ds2_p06_approval": dataset_root / "provenance/ds2_p06_approval.json",
        "p07_gold_bundle_approval": dataset_root / "provenance/p07_gold_bundle_approval.json",
    }
    for name, path in upstream_paths.items():
        if sha256_file(path) != bundle.upstream_approved_sha256[name]:
            raise ValueError(f"upstream Approved artifact changed: {name}")
    preserved_paths = {
        "p06_system_outputs": repository_root / "storage_eval/p06_b1_b2/run-4/system_outputs.json",
        "p06_report": repository_root / "storage_eval/p06_b1_b2/run-4/report.json",
        "p07_protocol": dataset_root / "provenance/p07_evaluation_protocol_r2.json",
        "p07_protocol_approval": dataset_root
        / "provenance/p07_evaluation_protocol_r2_approval.json",
        "p07_calibration_report": repository_root
        / "storage_eval/p07_kp_calibration/run-4/report.json",
        "p07_holdout_report": repository_root / "storage_eval/p07_kp_holdout/run-1/report.json",
    }
    for name, path in preserved_paths.items():
        if sha256_file(path) != bundle.preserved_upstream_sha256[name]:
            raise ValueError(f"preserved P06/P07 artifact changed: {name}")

    review_dir = repository_root / bundle.review_pack_relative_path
    if sha256_file(review_dir / "index.html") != bundle.review_pack_index_sha256:
        raise ValueError("P08 first-review HTML changed")
    if sha256_file(review_dir / "second_review.html") != bundle.second_review_index_sha256:
        raise ValueError("P08 second-review HTML changed")
    for evidence_id, expected_hash in bundle.review_asset_sha256.items():
        if sha256_file(review_dir / "assets" / f"{evidence_id}.png") != expected_hash:
            raise ValueError(f"P08 review asset changed: {evidence_id}")

    ds4 = DS4QueryProcessingDataset.model_validate_json(ds4_path.read_text(encoding="utf-8"))
    ds5 = DS5RetrievalQADataset.model_validate_json(ds5_path.read_text(encoding="utf-8"))
    records = [*ds4.cases, *ds5.cases]
    candidate_hashes = {item.record_id: record_digest(item) for item in records}
    if candidate_hashes != bundle.candidate_record_sha256:
        raise ValueError("P08 Candidate record hashes differ from Bundle Manifest")
    if any(item.review_status != "candidate" or item.approval is not None for item in records):
        raise ValueError("P08 approval accepts Candidate records only")

    first = P08ReviewDecisions.model_validate_json(first_review_path.read_text(encoding="utf-8"))
    second = P08ReviewDecisions.model_validate_json(second_review_path.read_text(encoding="utf-8"))
    first_ids = [item for group in bundle.first_review_groups for item in group]
    for decision, pass_name, expected_ids in (
        (first, "first", first_ids),
        (second, "second", bundle.second_review_ids),
    ):
        if decision.bundle_sha256 != bundle.bundle_sha256 or decision.review_pass != pass_name:
            raise ValueError(f"{pass_name} P08 review targets another bundle/pass")
        if decision.expected_record_ids != expected_ids:
            raise ValueError(f"{pass_name} P08 review expected IDs differ from Manifest")
        if decision.returned_record_ids or set(decision.reviewed_record_ids) != set(expected_ids):
            raise ValueError(f"{pass_name} P08 review is incomplete or contains returns")
        if decision.reviewer_id is not None and decision.reviewer_id != reviewer_id:
            raise ValueError(f"{pass_name} P08 reviewer differs from approval reviewer")
        if decision.reviewed_at is not None and decision.reviewed_at > reviewed_at:
            raise ValueError(f"{pass_name} P08 review timestamp is after approval")

    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("P08 retrieval approval cannot modify a locked Test set")

    approved_records = []
    approved_hashes: dict[str, str] = {}
    log_entries: list[ReviewLogEntry] = []
    for index, record in enumerate(records, 1):
        item_review_id = f"{review_id}.record.{index:03d}"
        updates: dict[str, object] = {
            "review_status": ReviewStatus.APPROVED,
            "approval": None,
        }
        if isinstance(record, type(ds5.cases[0])):
            updates["retrieval_gold_status"] = "approved"
        provisional = record.model_copy(update=updates)
        approved_hash = record_digest(provisional)
        values = provisional.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=item_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_hashes[record.record_id],
            approved_record_sha256=approved_hash,
            notes="Retrieval-only approval; QA Gold remains pending_p09.",
        ).model_dump(mode="json")
        approved = type(record).model_validate(values)
        approved_records.append(approved)
        approved_hashes[record.record_id] = approved_hash
        log_entries.append(
            ReviewLogEntry(
                review_id=item_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_hashes[record.record_id],
                resulting_record_sha256=approved_hash,
                notes="P08 DS4/DS5 Retrieval Gold only; QA pending P09.",
            )
        )

    approved_ds4 = ds4.model_copy(update={"cases": approved_records[: len(ds4.cases)]})
    approved_ds5 = ds5.model_copy(update={"cases": approved_records[len(ds4.cases) :]})
    approved_ds4_path = dataset_root / "approved/ds4/p08_query_processing.json"
    approved_ds5_path = dataset_root / "approved/ds5/p08_retrieval.json"
    atomic_write_json(approved_ds4_path, approved_ds4.model_dump(mode="json"))
    atomic_write_json(approved_ds5_path, approved_ds5.model_dump(mode="json"))

    review_dir_out = dataset_root / "reviews"
    first_out = review_dir_out / "ds45_p08_first_review_decisions.json"
    second_out = review_dir_out / "ds45_p08_second_review_decisions.json"
    atomic_write_json(first_out, first.model_dump(mode="json"))
    atomic_write_json(second_out, second.model_dump(mode="json"))
    split = json.loads(split_path.read_text(encoding="utf-8"))
    dev_ids = [item["case_id"] for item in split["assignments"] if item["split"] == "dev"]
    test_ids = [item["case_id"] for item in split["assignments"] if item["split"] == "test"]
    atomic_write_text(dataset_root / "splits/dev_ids.txt", "\n".join(dev_ids) + "\n")
    atomic_write_text(dataset_root / "splits/test_ids.txt", "\n".join(test_ids) + "\n")

    dataset_manifest_path = dataset_root / "manifest.json"
    dataset_manifest = json.loads(dataset_manifest_path.read_text(encoding="utf-8"))
    dataset_manifest.setdefault("gold_components", {}).update(
        {"ds4": "approved", "ds5_retrieval": "approved", "ds5_qa": "pending_p09"}
    )
    dataset_manifest["gold_status"] = "ds5_p08_retrieval_approved"
    dataset_manifest.setdefault("phase_input_status", {})["p07"] = "completed_gate_passed"
    dataset_manifest["phase_input_status"]["p08"] = "formal_dev_eval_ready"
    atomic_write_json(dataset_manifest_path, dataset_manifest)

    approval = P08GoldBundleApproval(
        dataset_id="courserag-p08-ds4-ds5-gold-bundle",
        dataset_version=bundle.dataset_version,
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        bundle_sha256=bundle.bundle_sha256,
        ds4_candidate=bundle.ds4_candidate,
        ds5_candidate=bundle.ds5_candidate,
        first_review_decisions=_artifact(repository_root, first_out),
        second_review_decisions=_artifact(repository_root, second_out),
        approved_ds4=_artifact(repository_root, approved_ds4_path),
        approved_ds5=_artifact(repository_root, approved_ds5_path),
        candidate_record_sha256=candidate_hashes,
        approved_record_sha256=approved_hashes,
        notes=notes,
    )
    atomic_write_json(
        dataset_root / "provenance/p08_gold_bundle_approval.json", approval.model_dump(mode="json")
    )
    _append_log(dataset_root / "reviews/review_log.jsonl", log_entries)
    return {
        "bundle_sha256": bundle.bundle_sha256,
        "approved_ds4_sha256": sha256_file(approved_ds4_path),
        "approved_ds5_sha256": sha256_file(approved_ds5_path),
        "record_count": len(records),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    result = approve_p08_bundle(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.bundle_sha256,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
