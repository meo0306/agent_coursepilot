"""Two-pass, Hash-bound owner approval for P10.3 Qualification Dev."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.io import atomic_write_json
from evaluation.p10_3_security_data import (
    P103DevApproval,
    P103ReviewPass,
    P103SecurityDevCandidate,
    sha256_file,
)


def approve_dev_candidate(
    *,
    dataset_path: Path,
    first_review_path: Path,
    second_review_path: Path,
    approval_path: Path,
    expected_dataset_sha256: str,
    owner_approved: bool,
) -> Path:
    if not owner_approved:
        raise ValueError("P10.3 Qualification Dev requires explicit owner approval")
    dataset_sha = sha256_file(dataset_path)
    if dataset_sha != expected_dataset_sha256:
        raise ValueError("P10.3 dataset differs from owner-approved identity")
    dataset = P103SecurityDevCandidate.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    reviews = tuple(
        P103ReviewPass.model_validate_json(path.read_text(encoding="utf-8"))
        for path in (first_review_path, second_review_path)
    )
    if tuple(review.pass_number for review in reviews) != (1, 2):
        raise ValueError("P10.3 requires ordered first and second review passes")
    expected_ids = tuple(case.record_id for case in dataset.cases)
    for review in reviews:
        if review.dataset_sha256 != dataset_sha:
            raise ValueError("P10.3 review does not bind exact dataset")
        if tuple(decision.record_id for decision in review.decisions) != expected_ids:
            raise ValueError("P10.3 review decisions do not cover ordered dataset IDs")
        if any(decision.decision != "pass" for decision in review.decisions):
            raise ValueError("P10.3 returned cases must be revised before approval")
    approval = P103DevApproval(
        dataset_sha256=dataset_sha,
        first_review_sha256=sha256_file(first_review_path),
        second_review_sha256=sha256_file(second_review_path),
        status="approved",
        reviewer="course_owner",
        approved_at=datetime.now(UTC),
        approved_case_ids=expected_ids,
    )
    atomic_write_json(approval_path, approval.model_dump(mode="json"))
    return approval_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-dataset-sha256", required=True)
    parser.add_argument("--owner-approved", action="store_true")
    args = parser.parse_args()
    output = approve_dev_candidate(
        dataset_path=args.dataset,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        approval_path=args.output,
        expected_dataset_sha256=args.expected_dataset_sha256,
        owner_approved=args.owner_approved,
    )
    print(
        json.dumps(
            {"approval": str(output), "approval_sha256": sha256_file(output)},
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
