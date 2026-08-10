"""Approve one exact, twice-reviewed P10 input Gold bundle."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from evaluation.contracts import (
    ApprovalRecord,
    HashedArtifact,
    ReviewLogEntry,
    ReviewStatus,
    TestLock,
)
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text
from evaluation.p10_input_data import bundle_identity_sha256
from evaluation.p10_schemas import (
    P10BundleApproval,
    P10BundleManifest,
    P10DS6Dataset,
    P10DS7Dataset,
    P10DS8Dataset,
    P10FixtureManifest,
    P10ReviewDecisions,
    P10SecurityDataset,
)

MODEL_BY_COMPONENT = {
    "ds6": P10DS6Dataset,
    "ds7": P10DS7Dataset,
    "ds8": P10DS8Dataset,
    "security": P10SecurityDataset,
}
APPROVED_PATHS = {
    "ds6": Path("approved/ds6/p10_citation_migration.json"),
    "ds7": Path("approved/ds7/p10_incremental_writeback.json"),
    "ds8": Path("approved/ds8/p10_performance_workloads.json"),
    "security": Path("approved/security/p10_security_fault.json"),
}


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root.resolve()):
        raise ValueError("P10 approval artifact must stay inside repository")
    return HashedArtifact(
        path=resolved.relative_to(repository_root.resolve()).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _validate_artifact(repository_root: Path, artifact: HashedArtifact) -> Path:
    path = repository_root / artifact.path
    if not path.is_file() or sha256_file(path) != artifact.sha256:
        raise ValueError(f"P10 artifact changed: {artifact.path}")
    if path.stat().st_size != artifact.size_bytes:
        raise ValueError(f"P10 artifact size changed: {artifact.path}")
    return path


def _append_log(path: Path, entries: list[ReviewLogEntry]) -> None:
    existing_text = path.read_text(encoding="utf-8") if path.exists() else ""
    if existing_text and not existing_text.endswith("\n"):
        raise ValueError("review log must end with newline")
    existing = {
        item.review_id: item
        for line in existing_text.splitlines()
        if line.strip()
        for item in [ReviewLogEntry.model_validate_json(line)]
    }
    additions: list[str] = []
    for entry in entries:
        current = existing.get(entry.review_id)
        if current is not None and current != entry:
            raise ValueError("existing P10 review-log entry differs")
        if current is None:
            additions.append(entry.model_dump_json() + "\n")
    atomic_write_text(path, existing_text + "".join(additions))


def _approve_record(
    record: Any,
    *,
    candidate_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    record_review_id: str,
) -> tuple[Any, str]:
    provisional = record.model_copy(
        update={"review_status": ReviewStatus.APPROVED, "approval": None}
    )
    approved_sha256 = record_digest(provisional)
    values = provisional.model_dump(mode="json")
    values["approval"] = ApprovalRecord(
        review_id=record_review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_sha256=candidate_sha256,
        approved_record_sha256=approved_sha256,
        notes="P10 input Gold approval only; no Dev/Test execution or Test lock.",
    ).model_dump(mode="json")
    return type(record).model_validate(values), approved_sha256


def approve_p10_bundle(
    *,
    dataset_root: Path,
    expected_bundle_sha256: str,
    first_review_path: Path,
    second_review_path: Path,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> dict[str, Any]:
    dataset_root = dataset_root.resolve()
    repository_root = dataset_root.parent.parent.parent
    manifest_path = dataset_root / "provenance/p10_input_bundle_manifest.json"
    manifest = P10BundleManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal P10 Input Gold Bundle SHA-256 does not match")
    if bundle_identity_sha256(manifest) != manifest.bundle_sha256:
        raise ValueError("P10 Bundle identity fields do not match bundle_sha256")

    test_lock = TestLock.model_validate_json(
        (dataset_root / "test.lock.json").read_text(encoding="utf-8")
    )
    if test_lock.locked:
        raise ValueError("P10 input approval cannot run after Test lock")
    for artifact in (
        *manifest.candidates.values(),
        manifest.fixture_manifest,
        manifest.component_splits,
        manifest.test_freeze_protocol,
        *manifest.upstream_approved.values(),
        *manifest.preserved_p09.values(),
    ):
        _validate_artifact(repository_root, artifact)
    fixture_manifest_path = _validate_artifact(repository_root, manifest.fixture_manifest)
    fixture_manifest = P10FixtureManifest.model_validate_json(
        fixture_manifest_path.read_text(encoding="utf-8")
    )
    for fixture in fixture_manifest.fixtures:
        _validate_artifact(repository_root, fixture.artifact)
    review_dir = repository_root / manifest.review_pack_relative_path
    if (
        sha256_file(review_dir / "index.html") != manifest.review_pack_index_sha256
        or sha256_file(review_dir / "second_review.html") != manifest.second_review_index_sha256
    ):
        raise ValueError("P10 review pack changed")

    first = P10ReviewDecisions.model_validate_json(first_review_path.read_text(encoding="utf-8"))
    second = P10ReviewDecisions.model_validate_json(second_review_path.read_text(encoding="utf-8"))
    for decisions, pass_name, expected_ids in (
        (first, "first", manifest.first_review_ids),
        (second, "second", manifest.second_review_ids),
    ):
        if (
            decisions.bundle_sha256 != manifest.bundle_sha256
            or decisions.review_pass != pass_name
            or decisions.expected_record_ids != expected_ids
            or any(item.decision != "pass" for item in decisions.decisions)
            or decisions.reviewer_id is None
            or decisions.reviewed_at is None
        ):
            raise ValueError(f"P10 {pass_name} review is incomplete or contains a return")

    approved_datasets: dict[str, Any] = {}
    approved_hashes: dict[str, dict[str, str]] = {}
    log_entries: list[ReviewLogEntry] = []
    for component, artifact in manifest.candidates.items():
        model = MODEL_BY_COMPONENT[component]
        candidate_path = _validate_artifact(repository_root, artifact)
        candidate: Any = model.model_validate_json(candidate_path.read_text(encoding="utf-8"))
        expected_hashes = manifest.candidate_record_sha256[component]
        if {item.record_id: record_digest(item) for item in candidate.cases} != expected_hashes:
            raise ValueError(f"P10 {component} record hashes changed")
        approved_cases = []
        component_hashes: dict[str, str] = {}
        for index, record in enumerate(candidate.cases, start=1):
            record_review_id = f"{review_id}.{component}.{index:03d}"
            candidate_record_sha256 = expected_hashes[record.record_id]
            approved, approved_sha = _approve_record(
                record,
                candidate_sha256=candidate_record_sha256,
                reviewer_id=reviewer_id,
                reviewed_at=reviewed_at,
                record_review_id=record_review_id,
            )
            approved_cases.append(approved)
            component_hashes[record.record_id] = approved_sha
            log_entries.append(
                ReviewLogEntry(
                    review_id=record_review_id,
                    record_id=record.record_id,
                    action="approve",
                    reviewer_id=reviewer_id,
                    reviewed_at=reviewed_at,
                    candidate_sha256=candidate_record_sha256,
                    resulting_record_sha256=approved_sha,
                    notes="P10 input Gold record approved; Test remains unlocked.",
                )
            )
        approved_datasets[component] = candidate.model_copy(update={"cases": approved_cases})
        approved_hashes[component] = component_hashes

    for component, dataset in approved_datasets.items():
        atomic_write_json(dataset_root / APPROVED_PATHS[component], dataset.model_dump(mode="json"))
    review_root = dataset_root / "reviews"
    first_destination = review_root / "p10_first_review_decisions.json"
    second_destination = review_root / "p10_second_review_decisions.json"
    atomic_write_json(first_destination, first.model_dump(mode="json"))
    atomic_write_json(second_destination, second.model_dump(mode="json"))
    _append_log(review_root / "review_log.jsonl", log_entries)

    approved_artifacts = {
        component: _artifact(repository_root, dataset_root / path)
        for component, path in APPROVED_PATHS.items()
    }
    approval = P10BundleApproval(
        dataset_id="courserag-p10-input-bundle-approval",
        dataset_version="r1",
        bundle_sha256=manifest.bundle_sha256,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        review_id=review_id,
        candidates=manifest.candidates,
        approved=approved_artifacts,
        approved_record_sha256=approved_hashes,
        first_review_decisions=_artifact(repository_root, first_destination),
        second_review_decisions=_artifact(repository_root, second_destination),
        notes=notes,
    )
    approval_path = dataset_root / "provenance/p10_input_bundle_approval.json"
    atomic_write_json(approval_path, approval.model_dump(mode="json"))

    governance_path = dataset_root / "manifest.json"
    governance = json.loads(governance_path.read_text(encoding="utf-8"))
    governance.setdefault("gold_components", {}).update(
        {"ds6": "approved", "ds7": "approved", "ds8": "approved", "p10_security": "approved"}
    )
    governance["gold_status"] = "p10_input_gold_approved"
    governance.setdefault("phase_input_status", {})["p09"] = "completed_gate_passed"
    governance["phase_input_status"]["p10"] = "formal_dev_eval_ready"
    governance.setdefault("phase_execution_status", {})["p09"] = "completed_with_quality_debt"
    atomic_write_json(governance_path, governance)
    return {
        "bundle_sha256": manifest.bundle_sha256,
        "approval_sha256": sha256_file(approval_path),
        "approved_sha256": {key: value.sha256 for key, value in approved_artifacts.items()},
        "approved_records": sum(len(item.cases) for item in approved_datasets.values()),
        "test_locked": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--bundle-sha256", required=True)
    parser.add_argument("--first-review", type=Path, required=True)
    parser.add_argument("--second-review", type=Path, required=True)
    parser.add_argument("--reviewer-id", default="course_owner")
    parser.add_argument("--reviewed-at", required=True)
    parser.add_argument("--review-id", required=True)
    parser.add_argument("--notes", default="")
    args = parser.parse_args()
    result = approve_p10_bundle(
        dataset_root=args.dataset_root,
        expected_bundle_sha256=args.bundle_sha256,
        first_review_path=args.first_review,
        second_review_path=args.second_review,
        reviewer_id=args.reviewer_id,
        reviewed_at=datetime.fromisoformat(args.reviewed_at),
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
