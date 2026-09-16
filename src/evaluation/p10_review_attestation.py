"""Record a course owner's explicit, hash-bound P10 conversation attestation."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from evaluation.contracts import TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_json
from evaluation.p10_input_data import bundle_identity_sha256
from evaluation.p10_schemas import (
    P10BundleManifest,
    P10ReviewDecision,
    P10ReviewDecisions,
)


def _attestation(
    manifest: P10BundleManifest,
    *,
    review_pass: Literal["first", "second"],
    statement: str,
    reviewer_id: str,
    reviewed_at: datetime,
) -> P10ReviewDecisions:
    ids = manifest.first_review_ids if review_pass == "first" else manifest.second_review_ids
    return P10ReviewDecisions(
        dataset_id="courserag-p10-review-attestation",
        dataset_version="r1",
        bundle_sha256=manifest.bundle_sha256,
        review_pass=review_pass,
        expected_record_ids=ids,
        decisions=[P10ReviewDecision(record_id=record_id, decision="pass") for record_id in ids],
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        attestation_source="course_owner_conversation_attestation",
        attestation_statement=statement,
        attestation_statement_sha256=hashlib.sha256(statement.encode("utf-8")).hexdigest(),
    )


def record_owner_attestation(
    *,
    dataset_root: Path,
    expected_bundle_sha256: str,
    statement: str,
    reviewer_id: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    """Materialize both required review passes from one explicit owner attestation."""
    dataset_root = dataset_root.resolve()
    repository_root = dataset_root.parent.parent.parent
    manifest_path = dataset_root / "provenance/p10_input_bundle_manifest.json"
    manifest = P10BundleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P10 Input Gold Bundle SHA-256 does not match")
    if bundle_identity_sha256(manifest) != manifest.bundle_sha256:
        raise ValueError("P10 Bundle identity fields do not match bundle_sha256")
    if not statement.strip():
        raise ValueError("course-owner attestation cannot be blank")

    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("P10 review attestation cannot be recorded after Test lock")
    review_dir = repository_root / manifest.review_pack_relative_path
    if (
        sha256_file(review_dir / "index.html") != manifest.review_pack_index_sha256
        or sha256_file(review_dir / "second_review.html") != manifest.second_review_index_sha256
    ):
        raise ValueError("P10 review pack changed")

    review_root = dataset_root / "reviews"
    first_path = review_root / "p10_first_review_attestation.json"
    second_path = review_root / "p10_second_review_attestation.json"
    first = _attestation(
        manifest,
        review_pass="first",
        statement=statement,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
    )
    second = _attestation(
        manifest,
        review_pass="second",
        statement=statement,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
    )
    atomic_write_json(first_path, first.model_dump(mode="json"))
    atomic_write_json(second_path, second.model_dump(mode="json"))
    return {
        "bundle_sha256": manifest.bundle_sha256,
        "attestation_statement_sha256": first.attestation_statement_sha256,
        "first_review_path": first_path.as_posix(),
        "first_review_sha256": sha256_file(first_path),
        "first_review_count": len(first.decisions),
        "second_review_path": second_path.as_posix(),
        "second_review_sha256": sha256_file(second_path),
        "second_review_count": len(second.decisions),
        "test_locked": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--statement", required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    args = parser.parse_args()
    result = record_owner_attestation(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.bundle_sha256,
        statement=args.statement,
        reviewer_id=args.reviewer_id,
        reviewed_at=datetime.fromisoformat(args.reviewed_at),
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
