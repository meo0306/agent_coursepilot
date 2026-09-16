"""Materialize the explicitly approved EP-00 r2 Dev dataset."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import TypeVar, cast

from evaluation.contracts import (
    ApprovalRecord,
    ReviewableRecord,
    ReviewLogEntry,
    ReviewStatus,
)
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.system_optimization.dev_loader import DEFAULT_ROOT, load_approved, load_candidate
from evaluation.system_optimization.schemas import (
    CaseApprovalBatch,
    DevCaseDataset,
    FailureReplayDataset,
)

DEFAULT_DECISIONS = (
    DEFAULT_ROOT / "candidates" / "review" / "case_review_decisions_r2_template.json"
)

RecordT = TypeVar("RecordT", bound=ReviewableRecord)


def approve_dev_data(
    *,
    root: Path = DEFAULT_ROOT,
    decisions_path: Path = DEFAULT_DECISIONS,
    failure_reviewer_id: str,
    failure_reviewed_at: datetime,
) -> dict[str, object]:
    candidate = load_candidate(root)
    decisions = CaseApprovalBatch.model_validate_json(decisions_path.read_text(encoding="utf-8"))
    decisions_by_id = {item.record_id: item for item in decisions.decisions}
    expected_case_ids = {item.record_id for item in candidate.cases.records}
    if set(decisions_by_id) != expected_case_ids:
        raise ValueError("r2 Case decisions do not exactly cover the Candidate records")
    if any(item.decision != "approve" for item in decisions.decisions):
        raise ValueError("every r2 Case must be explicitly approved before materialization")

    approved_cases = []
    approved_failures = []
    reviews: list[ReviewLogEntry] = []
    for index, case in enumerate(candidate.cases.records, start=1):
        decision = decisions_by_id[case.record_id]
        if decision.adequacy_decision != case.candidate_adequacy.status:
            raise ValueError(f"human Adequacy differs from r2 Candidate: {case.record_id}")
        approved_case, review = _approve_record(
            case,
            review_id=f"ep00-r2-case-{index:02d}",
            reviewer_id=decision.reviewer_id or "",
            reviewed_at=decision.reviewed_at,
            notes=(
                f"EP-00 r2 Task Case approved; human Adequacy="
                f"{decision.adequacy_decision.value}. {decision.notes}"
            ).strip(),
        )
        approved_cases.append(approved_case)
        reviews.append(review)
    for index, failure in enumerate(candidate.failures.records, start=1):
        approved_failure, review = _approve_record(
            failure,
            review_id=f"ep00-r2-failure-{index:02d}",
            reviewer_id=failure_reviewer_id,
            reviewed_at=failure_reviewed_at,
            notes=(
                "Course Owner explicitly approved all seven EP-00 Failure Replays and "
                "authorized approved Dev materialization on 2026-08-31."
            ),
        )
        approved_failures.append(approved_failure)
        reviews.append(review)

    cases = DevCaseDataset(records=approved_cases)
    failures = FailureReplayDataset(records=approved_failures)
    approved_dir = root / "approved"
    paths = {
        "dev_cases": approved_dir / "dev_cases.json",
        "failure_replays": approved_dir / "failure_replays.json",
        "review_log": approved_dir / "review_log.jsonl",
    }
    _write_json_idempotently(paths["dev_cases"], cases.model_dump(mode="json"))
    _write_json_idempotently(paths["failure_replays"], failures.model_dump(mode="json"))
    review_text = "".join(item.model_dump_json() + "\n" for item in reviews)
    _write_text_idempotently(paths["review_log"], review_text)

    loaded = load_approved(root)
    return {
        "dataset_status": loaded.status,
        "task_cases": len(loaded.cases.records),
        "failure_replays": len(loaded.failures.records),
        "review_entries": len(reviews),
        "quality_metrics_eligible": loaded.metric_eligible,
        "p18_test_or_blind_loaded": False,
        "external_provider_calls": 0,
        "paths": {name: str(path) for name, path in paths.items()},
    }


def _approve_record(
    candidate: RecordT,
    *,
    review_id: str,
    reviewer_id: str,
    reviewed_at: datetime | None,
    notes: str,
) -> tuple[RecordT, ReviewLogEntry]:
    if not reviewer_id or reviewed_at is None:
        raise ValueError(f"approval identity/time is missing for {candidate.record_id}")
    values = candidate.model_dump(mode="json")
    values["review_status"] = ReviewStatus.APPROVED
    values.pop("approval", None)
    model = type(candidate)
    provisional = candidate.model_copy(
        update={"review_status": ReviewStatus.APPROVED, "approval": None}
    )
    approval = ApprovalRecord(
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=record_digest(candidate),
        approved_record_sha256=record_digest(provisional),
        notes=notes,
    )
    values["approval"] = approval.model_dump(mode="json")
    approved = cast(RecordT, model.model_validate(values))
    review = ReviewLogEntry(
        review_id=review_id,
        record_id=candidate.record_id,
        action="approve",
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=approval.candidate_sha256,
        resulting_record_sha256=approval.approved_record_sha256,
        notes=notes,
    )
    return approved, review


def _write_json_idempotently(path: Path, payload: object) -> None:
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise ValueError(f"existing approved EP-00 artifact differs: {path}")
        return
    atomic_write_json(path, payload)  # type: ignore[arg-type]


def _write_text_idempotently(path: Path, text: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"existing approved EP-00 artifact differs: {path}")
        return
    atomic_write_text(path, text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--decisions", type=Path, default=DEFAULT_DECISIONS)
    parser.add_argument("--failure-reviewer-id", required=True)
    parser.add_argument("--failure-reviewed-at", type=datetime.fromisoformat, required=True)
    args = parser.parse_args()
    result = approve_dev_data(
        root=args.root,
        decisions_path=args.decisions,
        failure_reviewer_id=args.failure_reviewer_id,
        failure_reviewed_at=args.failure_reviewed_at,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
