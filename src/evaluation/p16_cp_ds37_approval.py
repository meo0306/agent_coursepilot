"""Promote one exact, fully reviewed P16 CP-DS3/CP-DS7 Pilot bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import (
    CPDS3P16PilotDataset,
    CPDS7P16PilotDataset,
    P16BundleApproval,
    P16BundleManifest,
    P16ReviewDecisions,
)
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import load_review_log, record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p16_cp_ds37_review_r2 import (
    R2_DS3,
    R2_DS7,
    R2_MANIFEST,
    REVISION_HISTORY,
    _digest,
    _record_hashes,
)

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
APPROVED_DS3 = DATASET_ROOT / "approved/cp_ds3/p16_ppt_pilot.json"
APPROVED_DS7 = DATASET_ROOT / "approved/cp_ds7/p16_template_export_pilot.json"
APPROVAL_PATH = DATASET_ROOT / "provenance/p16_cp_ds37_bundle_approval.json"
FIRST_REVIEW_PATH = DATASET_ROOT / "reviews/p16_first_review_decisions.json"
SECOND_REVIEW_PATH = DATASET_ROOT / "reviews/p16_second_review_decisions.json"


def _append_log(path: Path, additions: list[ReviewLogEntry]) -> None:
    old = path.read_text(encoding="utf-8") if path.exists() else ""
    if old and not old.endswith("\n"):
        raise ValueError("review log must end with newline")
    existing = {
        item.review_id: item
        for line in old.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    new_lines: list[str] = []
    for item in additions:
        previous = existing.get(item.review_id)
        if previous is not None and previous != item:
            raise ValueError(f"existing review log entry differs: {item.review_id}")
        if previous is None:
            new_lines.append(item.model_dump_json() + "\n")
    atomic_write_text(path, old + "".join(new_lines))


def _load_review(
    path: Path,
    *,
    bundle: str,
    review_pass: str,
    expected_ids: list[str],
) -> P16ReviewDecisions:
    if not path.is_file():
        raise ValueError(f"missing P16 {review_pass} review export: {path}")
    review = P16ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))
    if review.bundle_sha256 != bundle or review.review_pass != review_pass:
        raise ValueError(f"P16 {review_pass} review is bound to a different Bundle")
    if review.expected_record_ids != expected_ids:
        raise ValueError(f"P16 {review_pass} review record order differs from Manifest")
    if review.reviewer_id != "course_owner":
        raise ValueError(f"P16 {review_pass} review must be completed by course_owner")
    if any(item.decision != "pass" for item in review.decisions):
        raise ValueError(f"P16 {review_pass} review contains returned records")
    return review


def _verify_bundle(
    root: Path, expected_bundle_sha256: str
) -> tuple[P16BundleManifest, CPDS3P16PilotDataset, CPDS7P16PilotDataset]:
    manifest_path = root / R2_MANIFEST
    manifest = P16BundleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P16 Bundle SHA-256 does not match")
    manifest_body = manifest.model_dump(mode="json", exclude={"bundle_sha256"})
    if _digest(manifest_body) != expected_bundle_sha256:
        raise ValueError("P16 Bundle Manifest identity changed")
    ds3 = CPDS3P16PilotDataset.model_validate_json((root / R2_DS3).read_text(encoding="utf-8"))
    ds7 = CPDS7P16PilotDataset.model_validate_json((root / R2_DS7).read_text(encoding="utf-8"))
    candidate_hashes = {
        "cp_ds3": sha256_file(root / R2_DS3),
        "cp_ds7": sha256_file(root / R2_DS7),
    }
    if candidate_hashes != manifest.candidate_hashes:
        raise ValueError("P16 Candidate hash changed")
    if _record_hashes(ds3, ds7) != manifest.record_hashes:
        raise ValueError("P16 Candidate record hash changed")
    for relative_path, expected_hash in manifest.render_artifacts.items():
        artifact = root / relative_path
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            raise ValueError(f"P16 render artifact changed: {relative_path}")
    if manifest.record_counts.get("first_review_objects") != 55:
        raise ValueError("P16 first review must contain 55 objects")
    if manifest.record_counts.get("second_review_objects") != 23:
        raise ValueError("P16 second review must contain 23 objects")
    return manifest, ds3, ds7


def _existing(
    root: Path, *, bundle: str, reviewer_id: str, review_id: str
) -> dict[str, object] | None:
    path = root / APPROVAL_PATH
    if not path.is_file():
        return None
    approval = P16BundleApproval.model_validate_json(path.read_text(encoding="utf-8"))
    candidate_ds3 = CPDS3P16PilotDataset.model_validate_json(
        (root / R2_DS3).read_text(encoding="utf-8")
    )
    candidate_ds7 = CPDS7P16PilotDataset.model_validate_json(
        (root / R2_DS7).read_text(encoding="utf-8")
    )
    approved_ds3 = CPDS3P16PilotDataset.model_validate_json(
        (root / APPROVED_DS3).read_text(encoding="utf-8")
    )
    approved_ds7 = CPDS7P16PilotDataset.model_validate_json(
        (root / APPROVED_DS7).read_text(encoding="utf-8")
    )
    embedded_pairs = [
        *zip(candidate_ds3.cases, approved_ds3.cases, strict=True),
        *zip(candidate_ds7.cases, approved_ds7.cases, strict=True),
    ]
    if any(
        approved.approval is None
        or approved.approval.candidate_sha256 != record_digest(candidate)
        or approved.approval.approved_record_sha256 != record_digest(approved)
        for candidate, approved in embedded_pairs
    ):
        return None
    review_entries = load_review_log(root / DATASET_ROOT / "reviews/review_log.jsonl")
    if any(
        approved.approval is None
        or approved.approval.review_id not in review_entries
        or review_entries[approved.approval.review_id].record_id != approved.record_id
        for _, approved in embedded_pairs
    ):
        return None
    if (approval.bundle_sha256, approval.reviewer_id, approval.review_id) != (
        bundle,
        reviewer_id,
        review_id,
    ):
        raise ValueError("existing P16 approval differs from requested approval")
    bound_files = {
        root / APPROVED_DS3: approval.approved_dataset_hashes["cp_ds3"],
        root / APPROVED_DS7: approval.approved_dataset_hashes["cp_ds7"],
        root / FIRST_REVIEW_PATH: approval.first_review_sha256,
        root / SECOND_REVIEW_PATH: approval.second_review_sha256,
    }
    for artifact, expected_hash in bound_files.items():
        if not artifact.is_file() or sha256_file(artifact) != expected_hash:
            raise ValueError(f"approved P16 artifact changed: {artifact}")
    return {
        "bundle_sha256": bundle,
        "approval_sha256": sha256_file(path),
        "approved_dataset_hashes": approval.approved_dataset_hashes,
        "record_count": approval.record_count,
        "p16_formal_eval_ready": True,
    }


def approve_p16_bundle(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    first_review_path: Path,
    second_review_path: Path,
) -> dict[str, object]:
    root = repository_root.resolve()
    manifest, ds3, ds7 = _verify_bundle(root, expected_bundle_sha256)
    existing = _existing(
        root,
        bundle=expected_bundle_sha256,
        reviewer_id=reviewer_id,
        review_id=review_id,
    )
    if existing is not None:
        return existing

    first = _load_review(
        root / first_review_path,
        bundle=expected_bundle_sha256,
        review_pass="first",
        expected_ids=manifest.review_sets["first"],
    )
    second = _load_review(
        root / second_review_path,
        bundle=expected_bundle_sha256,
        review_pass="second",
        expected_ids=manifest.review_sets["second"],
    )
    if reviewer_id != first.reviewer_id or reviewer_id != second.reviewer_id:
        raise ValueError("P16 approval reviewer differs from review exports")
    if reviewed_at < max(first.reviewed_at, second.reviewed_at):
        raise ValueError("P16 approval time predates completed human review")

    lock = TestLock.model_validate_json(
        (root / DATASET_ROOT / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P16 Pilot approval cannot modify a locked Test set")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (root / DATASET_ROOT / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("P16 Pilot approval requires empty CoursePilot Dev/Test")

    record_approvals: dict[str, ApprovalRecord] = {}
    approved_record_hashes: dict[str, str] = {}
    provisional_hashes: dict[str, str] = {}
    candidate_record_digests: dict[str, str] = {}
    for deck in ds3.cases:
        record_id = f"arch::{deck.record_id}"
        candidate_record_digests[record_id] = record_digest(deck)
        provisional_deck = deck.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        provisional_hashes[record_id] = record_digest(provisional_deck)
    for template in ds7.cases:
        candidate_record_digests[template.record_id] = record_digest(template)
        provisional_template = template.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        provisional_hashes[template.record_id] = record_digest(provisional_template)
    for record_id in manifest.review_sets["first"]:
        approved_hash = provisional_hashes.get(record_id, manifest.record_hashes[record_id])
        record_approvals[record_id] = ApprovalRecord(
            review_id=f"{review_id}.record.{len(record_approvals) + 1:03d}",
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_record_digests.get(
                record_id, manifest.record_hashes[record_id]
            ),
            approved_record_sha256=approved_hash,
            notes=(
                "P16 CP-DS3/CP-DS7 Pilot input Gold only; generated slide wording, "
                "visual quality and P18 formal Gold remain out of scope."
            ),
        )
        approved_record_hashes[record_id] = approved_hash

    approved_decks = []
    for deck in ds3.cases:
        record_id = f"arch::{deck.record_id}"
        approved_decks.append(
            deck.model_copy(
                update={
                    "review_status": ReviewStatus.APPROVED,
                    "approval": record_approvals[record_id],
                }
            )
        )
    approved_templates = []
    for template in ds7.cases:
        approved_templates.append(
            template.model_copy(
                update={
                    "review_status": ReviewStatus.APPROVED,
                    "approval": record_approvals[template.record_id],
                }
            )
        )
    approved_ds3 = ds3.model_copy(update={"cases": approved_decks})
    approved_ds7 = ds7.model_copy(update={"cases": approved_templates})

    atomic_write_json(root / FIRST_REVIEW_PATH, cast(JsonValue, first.model_dump(mode="json")))
    atomic_write_json(root / SECOND_REVIEW_PATH, cast(JsonValue, second.model_dump(mode="json")))
    atomic_write_json(root / APPROVED_DS3, cast(JsonValue, approved_ds3.model_dump(mode="json")))
    atomic_write_json(root / APPROVED_DS7, cast(JsonValue, approved_ds7.model_dump(mode="json")))
    approved_dataset_hashes = {
        "cp_ds3": sha256_file(root / APPROVED_DS3),
        "cp_ds7": sha256_file(root / APPROVED_DS7),
    }
    approval = P16BundleApproval(
        bundle_sha256=expected_bundle_sha256,
        candidate_hashes=manifest.candidate_hashes,
        record_hashes=manifest.record_hashes,
        approved_dataset_hashes=approved_dataset_hashes,
        approved_record_hashes=approved_record_hashes,
        record_approvals=record_approvals,
        first_review_sha256=sha256_file(root / FIRST_REVIEW_PATH),
        second_review_sha256=sha256_file(root / SECOND_REVIEW_PATH),
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )
    atomic_write_json(root / APPROVAL_PATH, cast(JsonValue, approval.model_dump(mode="json")))

    logs = [
        ReviewLogEntry(
            review_id=item.review_id,
            record_id=record_id.removeprefix("arch::"),
            action="approve",
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=item.candidate_sha256,
            resulting_record_sha256=item.approved_record_sha256,
            notes="P16 Pilot input approved; P18 formal CP-DS3/CP-DS7 remains out of scope.",
        )
        for record_id, item in record_approvals.items()
    ]
    _append_log(root / DATASET_ROOT / "reviews/review_log.jsonl", logs)

    governance_path = root / DATASET_ROOT / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance.setdefault("gold_components", {})["cp_ds3_p16_pilot"] = "approved"
    governance["gold_components"]["cp_ds7_p16_pilot"] = "approved"
    governance["gold_status"] = "p16_cp_ds3_ds7_pilot_approved"
    governance.setdefault("phase_input_status", {})["p15"] = "completed_gate_passed"
    governance["phase_input_status"]["p16"] = "formal_eval_ready"
    governance.setdefault("phase_execution_status", {})["p15"] = "completed_with_quality_debt"
    governance["phase_execution_status"]["p16"] = "not_started"
    atomic_write_json(governance_path, cast(JsonValue, governance))

    revision_path = root / REVISION_HISTORY
    revision = json.loads(revision_path.read_text(encoding="utf-8"))
    for item in revision["revisions"]:
        if item["candidate_relative_path"] in {R2_DS3.as_posix(), R2_DS7.as_posix()}:
            item["status"] = "approved"
            item["reason"] = (
                "Exact renderer-backed P16 r2 Candidate approved by the Course Owner after "
                "complete first and blind second review."
            )
    atomic_write_json(revision_path, cast(JsonValue, revision))
    return {
        "bundle_sha256": expected_bundle_sha256,
        "approval_sha256": sha256_file(root / APPROVAL_PATH),
        "approved_dataset_hashes": approved_dataset_hashes,
        "record_count": 55,
        "p16_formal_eval_ready": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", default="p16-cp-ds37-pilot-bundle-approval")
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            approve_p16_bundle(
                repository_root=args.repository_root,
                expected_bundle_sha256=args.bundle_sha256,
                reviewer_id=args.reviewer_id,
                reviewed_at=datetime.fromisoformat(args.reviewed_at),
                review_id=args.review_id,
                first_review_path=args.first_review,
                second_review_path=args.second_review,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
