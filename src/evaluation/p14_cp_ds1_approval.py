"""Promote one exact, owner-approved P14 CP-DS1 Lesson Pilot bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import (
    CPDS1P14PilotDataset,
    P14BundleApproval,
    P14FixtureBundle,
    P14ReviewDecision,
    P14ReviewDecisions,
)
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p14_cp_ds1_data import (
    FIXTURE_PATH,
    MANIFEST_PATH,
    PILOT_PATH,
    _digest,
)

DATASET_ROOT = Path("datasets/coursepilot_eval/v1")
APPROVED_PATH = DATASET_ROOT / "approved/cp_ds1/p14_lesson_pilot.json"
APPROVAL_PATH = DATASET_ROOT / "provenance/p14_cp_ds1_bundle_approval.json"
FIRST_REVIEW_PATH = DATASET_ROOT / "reviews/p14_first_review_decisions.json"
SECOND_REVIEW_PATH = DATASET_ROOT / "reviews/p14_second_review_decisions.json"


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
            raise ValueError(f"existing P14 review log entry differs: {addition.review_id}")
        if current is None:
            new_lines.append(addition.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(new_lines))


def _conversation_review(
    *,
    bundle_sha256: str,
    review_pass: Literal["first", "second"],
    record_ids: list[str],
    reviewer_id: str,
    reviewed_at: datetime,
) -> P14ReviewDecisions:
    return P14ReviewDecisions(
        bundle_sha256=bundle_sha256,
        review_pass=review_pass,
        expected_record_ids=record_ids,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        attestation_source="conversation_exact_bundle_approval",
        decisions=[
            P14ReviewDecision(
                record_id=record_id,
                decision="pass",
                notes=(
                    "Course owner approved the exact Bundle in conversation; "
                    "the original review page did not provide a JSON export channel."
                ),
            )
            for record_id in record_ids
        ],
    )


def _existing_result(
    root: Path,
    *,
    expected_bundle_sha256: str,
    reviewer_id: str,
    review_id: str,
) -> dict[str, object] | None:
    approval_path = root / APPROVAL_PATH
    if not approval_path.is_file():
        return None
    approval = P14BundleApproval.model_validate_json(approval_path.read_text(encoding="utf-8"))
    if (
        approval.bundle_sha256 != expected_bundle_sha256
        or approval.reviewer_id != reviewer_id
        or approval.review_id != review_id
    ):
        raise ValueError("existing P14 approval differs from the requested approval")
    artifacts = {
        approval.approved_dataset_sha256: root / APPROVED_PATH,
        approval.first_review_sha256: root / FIRST_REVIEW_PATH,
        approval.second_review_sha256: root / SECOND_REVIEW_PATH,
    }
    for expected_hash, path in artifacts.items():
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise ValueError(f"existing P14 approved artifact changed: {path}")
    return {
        "bundle_sha256": approval.bundle_sha256,
        "approval_sha256": sha256_file(approval_path),
        "approved_dataset_sha256": approval.approved_dataset_sha256,
        "record_count": approval.record_count,
        "p14_formal_eval_ready": True,
        "final_coursepilot_gold_promoted": False,
    }


def approve_p14_bundle(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
) -> dict[str, object]:
    root = repository_root.resolve()
    manifest_path = root / MANIFEST_PATH
    if not manifest_path.is_file():
        raise ValueError("P14 Bundle Manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("bundle_sha256") != expected_bundle_sha256:
        raise ValueError("literal P14 CP-DS1 Pilot Bundle SHA-256 does not match")
    candidate = CPDS1P14PilotDataset.model_validate_json(
        (root / PILOT_PATH).read_text(encoding="utf-8")
    )
    fixtures = P14FixtureBundle.model_validate_json(
        (root / FIXTURE_PATH).read_text(encoding="utf-8")
    )
    candidate_hashes = {
        "pilot": sha256_file(root / PILOT_PATH),
        "fixtures": sha256_file(root / FIXTURE_PATH),
    }
    canonical_hashes = {
        "pilot": hashlib.sha256(
            json.dumps(
                candidate.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "fixtures": hashlib.sha256(
            json.dumps(
                fixtures.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
    }
    if (
        candidate_hashes != manifest.get("candidate_hashes")
        or _digest(canonical_hashes) != expected_bundle_sha256
    ):
        raise ValueError("P14 Candidate, Fixture, Manifest, or Bundle identity changed")

    existing = _existing_result(
        root,
        expected_bundle_sha256=expected_bundle_sha256,
        reviewer_id=reviewer_id,
        review_id=review_id,
    )
    if existing is not None:
        return existing

    record_ids = [record.record_id for record in candidate.cases]
    if record_ids != manifest.get("record_ids"):
        raise ValueError("P14 Candidate record order changed")

    dataset_root = root / DATASET_ROOT
    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P14 Pilot approval cannot modify a locked Test set")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("P14 Pilot approval requires empty CoursePilot Dev/Test")

    first_review = _conversation_review(
        bundle_sha256=expected_bundle_sha256,
        review_pass="first",
        record_ids=record_ids,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
    )
    second_review = _conversation_review(
        bundle_sha256=expected_bundle_sha256,
        review_pass="second",
        record_ids=record_ids,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
    )
    atomic_write_json(root / FIRST_REVIEW_PATH, first_review.model_dump(mode="json"))
    atomic_write_json(root / SECOND_REVIEW_PATH, second_review.model_dump(mode="json"))

    approved_cases = []
    candidate_record_hashes: dict[str, str] = {}
    approved_record_hashes: dict[str, str] = {}
    log_entries: list[ReviewLogEntry] = []
    for index, record in enumerate(candidate.cases, 1):
        if record.review_status is not ReviewStatus.CANDIDATE or record.approval is not None:
            raise ValueError("P14 approval accepts Candidate records only")
        candidate_hash = record_digest(record)
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_hash = record_digest(provisional)
        item_review_id = f"{review_id}.record.{index:03d}"
        values = provisional.model_dump(mode="json")
        values["approval"] = ApprovalRecord(
            review_id=item_review_id,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            candidate_sha256=candidate_hash,
            approved_record_sha256=approved_hash,
            notes=(
                "P14 CP-DS1 Lesson Pilot input Gold approval; final CoursePilot CP-DS1 "
                "Gold remains P18 scope."
            ),
        ).model_dump(mode="json")
        approved_cases.append(type(record).model_validate(values))
        candidate_record_hashes[record.record_id] = candidate_hash
        approved_record_hashes[record.record_id] = approved_hash
        log_entries.append(
            ReviewLogEntry(
                review_id=item_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_hash,
                resulting_record_sha256=approved_hash,
                notes="P14 Pilot input Gold only; final CP-DS1 freeze remains P18 scope.",
            )
        )

    approved_dataset = candidate.model_copy(update={"cases": approved_cases})
    atomic_write_json(root / APPROVED_PATH, approved_dataset.model_dump(mode="json"))
    approval = P14BundleApproval(
        bundle_sha256=expected_bundle_sha256,
        candidate_hashes=candidate_hashes,
        candidate_record_sha256=candidate_record_hashes,
        approved_record_sha256=approved_record_hashes,
        approved_dataset_sha256=sha256_file(root / APPROVED_PATH),
        first_review_sha256=sha256_file(root / FIRST_REVIEW_PATH),
        second_review_sha256=sha256_file(root / SECOND_REVIEW_PATH),
        record_count=len(approved_cases),
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )
    atomic_write_json(root / APPROVAL_PATH, approval.model_dump(mode="json"))
    _append_log(dataset_root / "reviews/review_log.jsonl", log_entries)

    governance.setdefault("gold_components", {})["cp_ds1_p14_pilot"] = "approved"
    governance["gold_status"] = "p14_cp_ds1_pilot_approved"
    governance.setdefault("phase_input_status", {})["p14"] = "formal_eval_ready"
    governance.setdefault("phase_execution_status", {})["p14"] = "not_started"
    atomic_write_json(governance_path, cast(JsonValue, governance))
    return {
        "bundle_sha256": expected_bundle_sha256,
        "approval_sha256": sha256_file(root / APPROVAL_PATH),
        "approved_dataset_sha256": approval.approved_dataset_sha256,
        "record_count": approval.record_count,
        "p14_formal_eval_ready": True,
        "final_coursepilot_gold_promoted": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", default="p14-cp-ds1-pilot-bundle-approval")
    args = parser.parse_args()
    print(
        json.dumps(
            approve_p14_bundle(
                repository_root=args.repository_root,
                expected_bundle_sha256=args.bundle_sha256,
                reviewer_id=args.reviewer_id,
                reviewed_at=datetime.fromisoformat(args.reviewed_at),
                review_id=args.review_id,
            ),
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
