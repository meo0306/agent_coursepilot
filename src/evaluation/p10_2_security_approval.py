"""Hash-bound Course Owner approval writer for the P10.2 Dev Candidate."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.io import atomic_write_json
from evaluation.p10_2_security_data import (
    P102DevApproval,
    P102SecurityDevCandidate,
    sha256_file,
)


def approve_dev_candidate(
    *,
    dataset_path: Path,
    approval_path: Path,
    expected_sha256: str,
    owner_approved: bool,
) -> Path:
    if not owner_approved:
        raise ValueError("P10.2 Dev Candidate requires explicit Course Owner approval")
    actual_sha256 = sha256_file(dataset_path)
    if actual_sha256 != expected_sha256:
        raise ValueError("P10.2 Dev Candidate Hash differs from the owner-approved identity")
    dataset = P102SecurityDevCandidate.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    approval = P102DevApproval(
        dataset_sha256=actual_sha256,
        status="approved",
        reviewer="course_owner",
        approved_at=datetime.now(UTC),
        approved_case_ids=tuple(case.record_id for case in dataset.cases),
    )
    atomic_write_json(approval_path, approval.model_dump(mode="json"))
    return approval_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--owner-approved", action="store_true")
    args = parser.parse_args()
    output = approve_dev_candidate(
        dataset_path=args.dataset,
        approval_path=args.output,
        expected_sha256=args.expected_sha256,
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
