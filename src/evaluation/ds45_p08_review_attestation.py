"""Materialize explicit Course Owner all-passed P08 review attestations."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import P08GoldBundleManifest, P08ReviewDecisions
from evaluation.io import atomic_write_json


def record_owner_attestation(
    *,
    dataset_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    notes: str,
) -> tuple[Path, Path]:
    dataset_root = dataset_root.resolve()
    manifest = P08GoldBundleManifest.model_validate_json(
        (dataset_root / "provenance/p08_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P08 Bundle SHA-256 does not match attestation target")
    first_ids = [item for group in manifest.first_review_groups for item in group]
    paths = (
        dataset_root / "reviews/p08_r3_first_review_decisions.json",
        dataset_root / "reviews/p08_r3_second_review_decisions.json",
    )
    decisions = (
        P08ReviewDecisions(
            bundle_sha256=manifest.bundle_sha256,
            review_pass="first",
            expected_record_ids=first_ids,
            reviewed_record_ids=first_ids,
            returned_record_ids=[],
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            attestation_source="course_owner_conversation_attestation",
            notes=notes,
        ),
        P08ReviewDecisions(
            bundle_sha256=manifest.bundle_sha256,
            review_pass="second",
            expected_record_ids=manifest.second_review_ids,
            reviewed_record_ids=manifest.second_review_ids,
            returned_record_ids=[],
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            attestation_source="course_owner_conversation_attestation",
            notes=notes,
        ),
    )
    for path, decision in zip(paths, decisions, strict=True):
        if path.exists():
            existing = P08ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != decision:
                raise ValueError(f"existing P08 review attestation differs: {path}")
        else:
            atomic_write_json(path, decision.model_dump(mode="json"))
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Record explicit all-passed P08 owner review.")
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--expected-bundle-sha256", required=True)
    parser.add_argument("--reviewer-id", required=True)
    parser.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    parser.add_argument("--notes", required=True)
    args = parser.parse_args()
    for path in record_owner_attestation(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.expected_bundle_sha256,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        notes=args.notes,
    ):
        print(path)


if __name__ == "__main__":
    main()
