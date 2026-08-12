"""Recover P10.3 review decisions from an explicit Course Owner conversation attestation."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from evaluation.io import atomic_write_json
from evaluation.p10_3_security_data import (
    P103ReviewDecision,
    P103ReviewPass,
    P103SecurityDevCandidate,
    sha256_file,
)


def recover_all_pass_reviews(
    *,
    dataset_path: Path,
    first_review_path: Path,
    second_review_path: Path,
    expected_dataset_sha256: str,
    owner_attests_two_pass_all_pass: bool,
) -> tuple[Path, Path]:
    if not owner_attests_two_pass_all_pass:
        raise ValueError("P10.3 review recovery requires explicit owner attestation")
    dataset_sha256 = sha256_file(dataset_path)
    if dataset_sha256 != expected_dataset_sha256:
        raise ValueError("P10.3 attestation differs from the reviewed Candidate")
    dataset = P103SecurityDevCandidate.model_validate_json(dataset_path.read_text(encoding="utf-8"))
    decisions = tuple(
        P103ReviewDecision(
            record_id=case.record_id,
            decision="pass",
            note="Recovered from explicit Course Owner two-pass all-PASS conversation attestation",
        )
        for case in dataset.cases
    )
    outputs = (first_review_path, second_review_path)
    for pass_number, output in enumerate(outputs, start=1):
        atomic_write_json(
            output,
            P103ReviewPass(
                dataset_sha256=dataset_sha256,
                pass_number=pass_number,
                reviewer="course_owner",
                reviewed_at=datetime.now(UTC),
                decisions=decisions,
            ).model_dump(mode="json"),
        )
    return first_review_path.resolve(), second_review_path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--expected-dataset-sha256", required=True)
    parser.add_argument("--owner-attests-two-pass-all-pass", action="store_true")
    args = parser.parse_args()
    outputs = recover_all_pass_reviews(
        dataset_path=args.dataset,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        expected_dataset_sha256=args.expected_dataset_sha256,
        owner_attests_two_pass_all_pass=args.owner_attests_two_pass_all_pass,
    )
    print(
        json.dumps(
            {
                "reviews": [str(path) for path in outputs],
                "review_sha256": [sha256_file(path) for path in outputs],
                "source": "explicit_course_owner_conversation_attestation",
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
