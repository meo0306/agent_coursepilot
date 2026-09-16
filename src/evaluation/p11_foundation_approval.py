"""Approve one exact P11 Foundation work package without promoting formal CP Gold."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from evaluation.contracts import HashedArtifact, ReviewLogEntry, TestLock
from evaluation.corpus_fixtures import sha256_file
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p11_foundation_data import (
    CANDIDATE_MANIFEST_PATH,
    CANDIDATE_PATH,
    P10_FROZEN_PATH,
    P10_PORT_PATH,
    bundle_identity_sha256,
)
from evaluation.p11_schemas import (
    P11CandidateBundleManifest,
    P11FoundationApproval,
    P11FoundationCandidateDataset,
    P11ReviewDecisions,
    identity_sha256,
)

APPROVED_PATH = Path(
    "datasets/coursepilot_eval/v1/approved/work_packages/p11_foundation_input.json"
)
APPROVAL_PATH = Path("datasets/coursepilot_eval/v1/provenance/p11_foundation_input_approval.json")


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = (repository_root / path).resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError(f"P11 approval artifact missing or outside repository: {path}")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _validate_artifact(repository_root: Path, artifact: HashedArtifact) -> Path:
    path = (repository_root / artifact.path).resolve()
    if not path.is_file() or not path.is_relative_to(repository_root.resolve()):
        raise ValueError(f"P11 artifact absent or outside repository: {artifact.path}")
    if sha256_file(path) != artifact.sha256 or path.stat().st_size != artifact.size_bytes:
        raise ValueError(f"P11 artifact changed: {artifact.path}")
    return path


def _review(
    path: Path, manifest: P11CandidateBundleManifest, pass_name: str, ids: list[str]
) -> P11ReviewDecisions:
    review = P11ReviewDecisions.model_validate_json(path.read_text(encoding="utf-8"))
    if review.bundle_sha256 != manifest.bundle_sha256 or review.review_pass != pass_name:
        raise ValueError(f"P11 {pass_name} review binds a different Bundle")
    if review.expected_record_ids != ids or any(
        item.decision != "pass" for item in review.decisions
    ):
        raise ValueError(f"P11 {pass_name} review is incomplete or contains a return")
    return review


def _existing_approval_result(
    *,
    repository_root: Path,
    manifest: P11CandidateBundleManifest,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
) -> dict[str, object] | None:
    approval_path = repository_root / APPROVAL_PATH
    if not approval_path.is_file():
        return None
    approval = P11FoundationApproval.model_validate_json(approval_path.read_text(encoding="utf-8"))
    if (
        approval.bundle_sha256 != expected_bundle_sha256
        or approval.bundle_sha256 != manifest.bundle_sha256
        or approval.reviewer_id != reviewer_id
        or approval.reviewed_at != reviewed_at
        or approval.review_id != review_id
    ):
        raise ValueError("existing P11 approval differs from requested approval")
    for artifact in (
        approval.candidate,
        approval.approved_work_package,
        approval.first_review_decisions,
        approval.second_review_decisions,
    ):
        _validate_artifact(repository_root, artifact)
    if approval.candidate != manifest.candidate:
        raise ValueError("existing P11 approval binds a different Candidate")
    return {
        "bundle_sha256": approval.bundle_sha256,
        "approval_sha256": sha256_file(approval_path),
        "approved_work_package_sha256": approval.approved_work_package.sha256,
        "formal_gold_promoted": approval.formal_gold_promoted,
        "p11_start_authorized": approval.p11_start_authorized,
    }


def approve_p11_foundation(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    first_review_path: Path,
    second_review_path: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
) -> dict[str, object]:
    repository_root = repository_root.resolve()
    manifest_path = repository_root / CANDIDATE_MANIFEST_PATH
    if not manifest_path.is_file() or not (repository_root / CANDIDATE_PATH).is_file():
        raise ValueError("P11 has only the 37-record Draft; no approvable Candidate exists")
    manifest = P11CandidateBundleManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P11 Foundation Bundle SHA-256 does not match")
    existing_result = _existing_approval_result(
        repository_root=repository_root,
        manifest=manifest,
        expected_bundle_sha256=expected_bundle_sha256,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
    )
    if existing_result is not None:
        return existing_result
    candidate_path = _validate_artifact(repository_root, manifest.candidate)
    candidate = P11FoundationCandidateDataset.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    hashes = {
        item.record_id: identity_sha256(item.model_dump(mode="json")) for item in candidate.records
    }
    if hashes != manifest.candidate_record_sha256:
        raise ValueError("P11 Candidate record hashes changed")
    expected_identity = bundle_identity_sha256(
        candidate_sha256=manifest.candidate.sha256,
        record_sha256=hashes,
        p10_frozen_sha256=manifest.p10_frozen_manifest.sha256,
        p10_contract_sha256=manifest.p10_contract.sha256,
        p10_d013_decision_sha256=manifest.p10_d013_decision_log.sha256,
        p10_d013_policy_sha256=manifest.p10_d013_quality_policy.sha256,
        p10_d013_status_sha256=manifest.p10_d013_execution_status.sha256,
        p10_3_report_sha256=manifest.p10_3_failed_profile_report.sha256,
        p10_3_blind_sha256=manifest.p10_3_blind_commitment.sha256,
    )
    if expected_identity != manifest.bundle_sha256:
        raise ValueError("P11 Bundle identity fields changed")
    _validate_artifact(repository_root, manifest.p10_frozen_manifest)
    _validate_artifact(repository_root, manifest.p10_contract)
    for artifact in (
        manifest.p10_d013_decision_log,
        manifest.p10_d013_quality_policy,
        manifest.p10_d013_execution_status,
        manifest.p10_3_failed_profile_report,
        manifest.p10_3_blind_commitment,
    ):
        _validate_artifact(repository_root, artifact)
    if (
        sha256_file(repository_root / P10_FROZEN_PATH) != manifest.p10_frozen_manifest.sha256
        or sha256_file(repository_root / P10_PORT_PATH) != manifest.p10_contract.sha256
    ):
        raise ValueError("P10 identities changed after P11 Candidate generation")
    first = _review(first_review_path, manifest, "first", manifest.first_review_ids)
    second = _review(second_review_path, manifest, "second", manifest.second_review_ids)

    dataset_root = repository_root / "datasets/coursepilot_eval/v1"
    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if governance.get("gold_status") != "skeleton_no_formal_gold" or lock.locked:
        raise ValueError("P11 work-package approval requires skeleton Gold and unlocked Test")
    for split in ("dev_ids.txt", "test_ids.txt"):
        if (dataset_root / "splits" / split).read_text(encoding="utf-8").strip():
            raise ValueError("P11 work-package approval requires empty Dev/Test")

    approved_path = repository_root / APPROVED_PATH
    atomic_write_json(approved_path, candidate.model_dump(mode="json"))
    first_out = dataset_root / "reviews/p11_foundation_first_review.json"
    second_out = dataset_root / "reviews/p11_foundation_second_review.json"
    atomic_write_json(first_out, first.model_dump(mode="json"))
    atomic_write_json(second_out, second.model_dump(mode="json"))
    approval = P11FoundationApproval(
        bundle_sha256=manifest.bundle_sha256,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
        candidate=manifest.candidate,
        approved_work_package=_artifact(repository_root, APPROVED_PATH),
        candidate_record_sha256=hashes,
        first_review_decisions=_artifact(repository_root, first_out.relative_to(repository_root)),
        second_review_decisions=_artifact(repository_root, second_out.relative_to(repository_root)),
    )
    approval_path = repository_root / APPROVAL_PATH
    atomic_write_json(approval_path, approval.model_dump(mode="json"))
    log_path = dataset_root / "reviews/review_log.jsonl"
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log = ReviewLogEntry(
        review_id=review_id,
        record_id="p11-foundation-input-work-package",
        action="approve",
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=manifest.candidate.sha256,
        resulting_record_sha256=sha256_file(approved_path),
        notes="P11 implementation input contract only; P10-D013 permits P11 start; no formal CP Gold.",
    )
    parsed = [ReviewLogEntry.model_validate_json(line) for line in existing.splitlines() if line]
    matching = [item for item in parsed if item.review_id == review_id]
    if matching and matching != [log]:
        raise ValueError("existing P11 review log entry differs")
    if not matching:
        atomic_write_text(
            log_path,
            existing
            + ("" if not existing or existing.endswith("\n") else "\n")
            + log.model_dump_json()
            + "\n",
        )
    governance.setdefault("phase_input_status", {})["p11"] = "approved_for_implementation"
    governance.setdefault("phase_execution_status", {})["p11"] = "not_started"
    atomic_write_json(governance_path, governance)
    return {
        "bundle_sha256": manifest.bundle_sha256,
        "approval_sha256": sha256_file(approval_path),
        "approved_work_package_sha256": sha256_file(approved_path),
        "formal_gold_promoted": False,
        "p11_start_authorized": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", required=True)
    args = parser.parse_args()
    result = approve_p11_foundation(
        repository_root=args.repository_root,
        expected_bundle_sha256=args.bundle_sha256,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        reviewer_id=args.reviewer_id,
        reviewed_at=datetime.fromisoformat(args.reviewed_at),
        review_id=args.review_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
