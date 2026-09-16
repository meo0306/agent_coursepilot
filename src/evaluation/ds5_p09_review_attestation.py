"""Record a Course Owner's explicit all-passed P09 review attestation."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Literal

from courserag.evals.schemas import P09GoldBundleManifest, P09ReviewDecision, P09ReviewDecisions
from evaluation.io import atomic_write_json


def record_owner_attestation(
    *,
    dataset_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    notes: str,
    revision: Literal[1, 2] = 1,
) -> tuple[Path, Path]:
    dataset_root = dataset_root.resolve()
    manifest = P09GoldBundleManifest.model_validate_json(
        (dataset_root / "provenance/p09_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    if manifest.revision != revision:
        raise ValueError(f"P09 r{revision} attestation requires the r{revision} canonical manifest")
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError(
            f"literal P09 r{revision} Bundle SHA-256 does not match attestation target"
        )
    first_ids = [item for group in manifest.first_review_groups for item in group]
    paths = (
        dataset_root / f"reviews/p09_r{revision}_first_review_attestation.json",
        dataset_root / f"reviews/p09_r{revision}_second_review_attestation.json",
    )
    reviews = (
        P09ReviewDecisions(
            dataset_id=f"courserag-p09-r{revision}-owner-attestation-first",
            dataset_version=f"r{revision}",
            bundle_sha256=manifest.bundle_sha256,
            review_pass="first",
            expected_record_ids=first_ids,
            decisions=[P09ReviewDecision(record_id=item, decision="pass") for item in first_ids],
            reviewer_id=reviewer_id,
            reviewed_at=None,
            attestation_source="course_owner_conversation_attestation",
            notes=notes,
        ),
        P09ReviewDecisions(
            dataset_id=f"courserag-p09-r{revision}-owner-attestation-second",
            dataset_version=f"r{revision}",
            bundle_sha256=manifest.bundle_sha256,
            review_pass="second",
            expected_record_ids=manifest.second_review_ids,
            decisions=[
                P09ReviewDecision(record_id=item, decision="pass")
                for item in manifest.second_review_ids
            ],
            reviewer_id=reviewer_id,
            reviewed_at=None,
            attestation_source="course_owner_conversation_attestation",
            notes=notes,
        ),
    )
    for path, review in zip(paths, reviews, strict=True):
        if path.exists():
            existing = P09ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != review:
                raise ValueError(f"existing P09 r{revision} review attestation differs: {path}")
        else:
            atomic_write_json(path, review.model_dump(mode="json"))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an explicit all-passed P09 review.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-bundle-sha256", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--notes", required=True)
    parser.add_argument("--revision", type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    for path in record_owner_attestation(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.expected_bundle_sha256,
        reviewer_id=args.reviewer_id,
        notes=args.notes,
        revision=args.revision,
    ):
        print(path)


if __name__ == "__main__":
    main()
