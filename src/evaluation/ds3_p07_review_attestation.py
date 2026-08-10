"""Materialize explicit Course Owner all-passed P07 review attestations."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from courserag.evals.schemas import DS3ReviewDecisions, P07GoldBundleManifest
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
    manifest = P07GoldBundleManifest.model_validate_json(
        (dataset_root / "provenance/p07_gold_bundle_manifest.json").read_text(encoding="utf-8")
    )
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P07 Bundle SHA-256 does not match attestation target")
    paths = (
        dataset_root / "reviews/ds3_p07_first_review_decisions_r1.json",
        dataset_root / "reviews/ds3_p07_second_review_decisions_r1.json",
    )
    decisions = (
        DS3ReviewDecisions(
            bundle_sha256=manifest.bundle_sha256,
            review_pass="first",
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            attestation_source="course_owner_conversation_attestation",
            expected_record_ids=manifest.first_review_ids,
            reviewed_record_ids=manifest.first_review_ids,
            returned_record_ids=[],
            notes=notes,
        ),
        DS3ReviewDecisions(
            bundle_sha256=manifest.bundle_sha256,
            review_pass="second",
            reviewer_id=reviewer_id,
            reviewed_at=reviewed_at,
            attestation_source="course_owner_conversation_attestation",
            expected_record_ids=manifest.second_review_ids,
            reviewed_record_ids=manifest.second_review_ids,
            returned_record_ids=[],
            notes=notes,
        ),
    )
    for path, decision in zip(paths, decisions, strict=True):
        payload = decision.model_dump(mode="json")
        if path.exists():
            existing = DS3ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))
            if existing != decision:
                raise ValueError(f"existing P07 review attestation differs: {path}")
        else:
            atomic_write_json(path, payload)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Record explicit all-passed P07 owner review.")
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
