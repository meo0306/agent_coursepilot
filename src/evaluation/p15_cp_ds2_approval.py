"""Promote one exact, reviewed P15 CP-DS2 Exam Pilot bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Literal, cast

from pydantic import JsonValue

from coursepilot.evals.formal_schemas import (
    CPDS2P15PilotDataset,
    P15BundleApproval,
    P15ReviewDecision,
    P15ReviewDecisions,
)
from evaluation.contracts import ApprovalRecord, ReviewLogEntry, ReviewStatus, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p15_cp_ds2_data import (
    FIXTURE_PATH,
    MANIFEST_PATH,
    PILOT_PATH,
    _digest,
)

ROOT_DATASET = Path("datasets/coursepilot_eval/v1")
APPROVED_PATH = ROOT_DATASET / "approved/cp_ds2/p15_exam_pilot.json"
APPROVAL_PATH = ROOT_DATASET / "provenance/p15_cp_ds2_bundle_approval.json"
FIRST_REVIEW_PATH = ROOT_DATASET / "reviews/p15_first_review_decisions.json"
SECOND_REVIEW_PATH = ROOT_DATASET / "reviews/p15_second_review_decisions.json"


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
    lines: list[str] = []
    for item in additions:
        previous = existing.get(item.review_id)
        if previous is not None and previous != item:
            raise ValueError(f"existing review log entry differs: {item.review_id}")
        if previous is None:
            lines.append(item.model_dump_json() + "\n")
    atomic_write_text(path, old + "".join(lines))


def _load_review(
    root: Path, path: Path, bundle: str, expected: list[str], review_pass: str
) -> P15ReviewDecisions:
    if not path.is_file():
        raise ValueError(f"missing P15 {review_pass} review export: {path}")
    review = P15ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))
    if review.bundle_sha256 != bundle or review.review_pass != review_pass:
        raise ValueError(f"P15 {review_pass} review is bound to a different bundle")
    if review.expected_record_ids != expected:
        raise ValueError(f"P15 {review_pass} review record order differs from Candidate")
    if any(item.decision != "pass" for item in review.decisions):
        raise ValueError(f"P15 {review_pass} review contains returned records")
    return review


def _conversation_review(
    *,
    bundle: str,
    review_pass: Literal["first", "second"],
    record_ids: list[str],
    reviewer_id: str,
    reviewed_at: datetime,
) -> P15ReviewDecisions:
    return P15ReviewDecisions(
        bundle_sha256=bundle,
        review_pass=review_pass,
        expected_record_ids=record_ids,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        attestation_source="conversation_exact_bundle_approval",
        decisions=[
            P15ReviewDecision(
                record_id=record_id,
                decision="pass",
                notes=(
                    "Course owner approved the exact P15 Bundle in conversation; "
                    "the review page export was not supplied."
                ),
            )
            for record_id in record_ids
        ],
    )


def _existing(
    root: Path, bundle: str, reviewer_id: str, review_id: str
) -> dict[str, object] | None:
    path = root / APPROVAL_PATH
    if not path.is_file():
        return None
    approval = P15BundleApproval.model_validate_json(path.read_text(encoding="utf-8"))
    if (approval.bundle_sha256, approval.reviewer_id, approval.review_id) != (
        bundle,
        reviewer_id,
        review_id,
    ):
        raise ValueError("existing P15 approval differs from requested approval")
    for digest, artifact in (
        (approval.approved_dataset_sha256, root / APPROVED_PATH),
        (approval.first_review_sha256, root / FIRST_REVIEW_PATH),
        (approval.second_review_sha256, root / SECOND_REVIEW_PATH),
    ):
        if not artifact.is_file() or sha256_file(artifact) != digest:
            raise ValueError(f"approved P15 artifact changed: {artifact}")
    return {
        "bundle_sha256": bundle,
        "approval_sha256": sha256_file(path),
        "approved_dataset_sha256": approval.approved_dataset_sha256,
        "record_count": approval.record_count,
        "p15_formal_eval_ready": True,
    }


def approve_p15_bundle(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    first_review_path: Path | None = None,
    second_review_path: Path | None = None,
) -> dict[str, object]:
    root = repository_root.resolve()
    manifest_path = root / MANIFEST_PATH
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("bundle_sha256") != expected_bundle_sha256:
        raise ValueError("literal P15 Bundle SHA-256 does not match")
    candidate = CPDS2P15PilotDataset.model_validate_json(
        (root / PILOT_PATH).read_text(encoding="utf-8")
    )
    candidate_hashes = {
        "pilot": sha256_file(root / PILOT_PATH),
        "fixtures": sha256_file(root / FIXTURE_PATH),
    }
    if candidate_hashes != manifest.get("candidate_hashes"):
        raise ValueError("P15 Candidate or Fixture hash changed")
    bundle = _digest({"pilot": candidate_hashes["pilot"], "fixtures": candidate_hashes["fixtures"]})
    if bundle != expected_bundle_sha256:
        raise ValueError("P15 Bundle identity changed")
    existing = _existing(root, expected_bundle_sha256, reviewer_id, review_id)
    if existing is not None:
        return existing

    record_ids = [case.record_id for case in candidate.cases] + [
        target.target_id for target in candidate.targets
    ]
    expected_first = manifest.get("record_ids")
    if (
        record_ids + [item for item in expected_first or [] if item not in record_ids]
        != expected_first
    ):
        raise ValueError("P15 Candidate record order differs from manifest")
    first_path = root / (first_review_path or FIRST_REVIEW_PATH)
    second_path = root / (second_review_path or SECOND_REVIEW_PATH)
    if (
        first_review_path is None
        and second_review_path is None
        and not first_path.exists()
        and not second_path.exists()
    ):
        first_review = _conversation_review(
            bundle=expected_bundle_sha256,
            review_pass="first",
            record_ids=expected_first,
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
        )
        second_review = _conversation_review(
            bundle=expected_bundle_sha256,
            review_pass="second",
            record_ids=manifest.get("second_review_record_ids", []),
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
        )
    else:
        if first_review_path is None or second_review_path is None:
            raise ValueError("both P15 review exports are required when either export is supplied")
        first_review = _load_review(
            root, first_path, expected_bundle_sha256, expected_first, "first"
        )
        second_review = _load_review(
            root,
            second_path,
            expected_bundle_sha256,
            manifest.get("second_review_record_ids", []),
            "second",
        )

    governance_path = root / ROOT_DATASET / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    lock = TestLock.model_validate_json(
        (root / ROOT_DATASET / "test.lock.json").read_text(encoding="utf-8")
    )
    if lock.locked:
        raise ValueError("P15 Pilot approval cannot modify a locked Test set")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (root / ROOT_DATASET / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("P15 Pilot approval requires empty CoursePilot Dev/Test")

    atomic_write_json(root / FIRST_REVIEW_PATH, first_review.model_dump(mode="json"))
    atomic_write_json(root / SECOND_REVIEW_PATH, second_review.model_dump(mode="json"))
    candidate_hashes_by_record: dict[str, str] = {}
    approved_hashes: dict[str, str] = {}
    records = []
    logs: list[ReviewLogEntry] = []
    for index, record in enumerate([*candidate.cases, *candidate.targets], 1):
        if record.review_status is not ReviewStatus.CANDIDATE or record.approval is not None:
            raise ValueError("P15 approval accepts Candidate records only")
        candidate_digest = record_digest(record)
        provisional = record.model_copy(
            update={"review_status": ReviewStatus.APPROVED, "approval": None}
        )
        approved_digest = record_digest(provisional)
        item_review_id = f"{review_id}.record.{index:03d}"
        approved = provisional.model_copy(
            update={
                "approval": ApprovalRecord(
                    review_id=item_review_id,
                    reviewer_id=reviewer_id,
                    reviewed_at=reviewed_at,
                    candidate_sha256=candidate_digest,
                    approved_record_sha256=approved_digest,
                    notes="P15 CP-DS2 Exam Pilot input Gold only; no fixed question wording is approved.",
                )
            }
        )
        records.append(approved)
        candidate_hashes_by_record[record.record_id] = candidate_digest
        approved_hashes[record.record_id] = record_digest(approved)
        logs.append(
            ReviewLogEntry(
                review_id=item_review_id,
                record_id=record.record_id,
                action="approve",
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                candidate_sha256=candidate_digest,
                resulting_record_sha256=record_digest(approved),
                notes="P15 CP-DS2 Pilot input Gold approved; P18 formal CP-DS2 remains out of scope.",
            )
        )
    approved_dataset = candidate.model_copy(update={"cases": records[:3], "targets": records[3:]})
    atomic_write_json(root / APPROVED_PATH, approved_dataset.model_dump(mode="json"))
    approval = P15BundleApproval(
        bundle_sha256=expected_bundle_sha256,
        candidate_hashes=candidate_hashes,
        candidate_record_sha256=candidate_hashes_by_record,
        approved_record_sha256=approved_hashes,
        approved_dataset_sha256=sha256_file(root / APPROVED_PATH),
        first_review_sha256=sha256_file(root / FIRST_REVIEW_PATH),
        second_review_sha256=sha256_file(root / SECOND_REVIEW_PATH),
        record_count=len(records),
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )
    atomic_write_json(root / APPROVAL_PATH, approval.model_dump(mode="json"))
    _append_log(root / ROOT_DATASET / "reviews/review_log.jsonl", logs)
    governance.setdefault("gold_components", {})["cp_ds2_p15_pilot"] = "approved"
    governance["gold_status"] = "p15_cp_ds2_pilot_approved"
    governance.setdefault("phase_input_status", {})["p15"] = "formal_eval_ready"
    governance.setdefault("phase_input_status", {})["p14"] = "completed_gate_passed"
    governance.setdefault("phase_execution_status", {})["p14"] = "completed_with_quality_debt"
    atomic_write_json(governance_path, cast(JsonValue, governance))
    return {
        "bundle_sha256": expected_bundle_sha256,
        "approval_sha256": sha256_file(root / APPROVAL_PATH),
        "approved_dataset_sha256": approval.approved_dataset_sha256,
        "record_count": approval.record_count,
        "p15_formal_eval_ready": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", default="p15-cp-ds2-pilot-bundle-approval")
    parser.add_argument("--first-review", type=Path)
    parser.add_argument("--second-review", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            approve_p15_bundle(
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
