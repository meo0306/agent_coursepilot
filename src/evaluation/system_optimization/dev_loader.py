"""Strict loader for the post-P18 development dataset.

The loader owns a narrow directory contract and rejects P18/Test/Blind paths
before reading bytes.  Candidate data can be checked, but only human-approved
records may be loaded as metric-eligible Dev data.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from evaluation.contracts import ReviewLogEntry, ReviewStatus
from evaluation.datasets import record_digest
from evaluation.system_optimization.schemas import DevCaseDataset, FailureReplayDataset

DEFAULT_ROOT = Path("datasets/system_optimization/v1")
_FORBIDDEN_PATH_PARTS = {"p18", "test", "blind", "formal_test"}
_FORBIDDEN_SOURCE_PREFIXES = ("p18-", "p18_", "p18:")


class SystemOptimizationBoundaryError(ValueError):
    """Raised before the new Dev workbench crosses its approved boundary."""


class SystemOptimizationApprovalPending(SystemOptimizationBoundaryError):
    """Raised when metric-eligible Dev data has not been human-approved."""


@dataclass(frozen=True)
class LoadedDevData:
    status: Literal["candidate", "approved"]
    cases: DevCaseDataset
    failures: FailureReplayDataset

    @property
    def metric_eligible(self) -> bool:
        return self.status == "approved"


def load_candidate(root: Path = DEFAULT_ROOT) -> LoadedDevData:
    return _load(root, status="candidate")


def load_approved(root: Path = DEFAULT_ROOT) -> LoadedDevData:
    return _load(root, status="approved")


def _load(root: Path, *, status: Literal["candidate", "approved"]) -> LoadedDevData:
    resolved_root = root.resolve()
    _guard_path(resolved_root)
    directory = "candidates" if status == "candidate" else "approved"
    case_path = resolved_root / directory / "dev_cases.json"
    failure_path = resolved_root / directory / "failure_replays.json"
    _guard_dataset_file(resolved_root, case_path)
    _guard_dataset_file(resolved_root, failure_path)
    if status == "approved" and (not case_path.is_file() or not failure_path.is_file()):
        raise SystemOptimizationApprovalPending(
            "approved EP-00 Dev data is absent; explicit human approval is still required"
        )
    cases = DevCaseDataset.model_validate(_read_json(case_path))
    failures = FailureReplayDataset.model_validate(_read_json(failure_path))
    _validate_status(cases, failures, status=status)
    _guard_record_provenance(cases, failures)
    if status == "approved":
        _validate_approval_bindings(resolved_root, cases, failures)
    return LoadedDevData(status=status, cases=cases, failures=failures)


def _guard_path(path: Path) -> None:
    parts = {part.casefold() for part in path.parts}
    blocked = parts & _FORBIDDEN_PATH_PARTS
    if blocked:
        raise SystemOptimizationBoundaryError(
            f"P18/Test/Blind path is forbidden: {sorted(blocked)}"
        )


def _guard_dataset_file(root: Path, path: Path) -> None:
    resolved = path.resolve()
    try:
        relative = resolved.relative_to(root)
    except ValueError as exc:
        raise SystemOptimizationBoundaryError("dataset path escapes the EP-00 root") from exc
    _guard_path(relative)
    if resolved.name not in {"dev_cases.json", "failure_replays.json"}:
        raise SystemOptimizationBoundaryError("unexpected EP-00 dataset filename")


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise SystemOptimizationBoundaryError(f"missing EP-00 dataset file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_status(
    cases: DevCaseDataset,
    failures: FailureReplayDataset,
    *,
    status: Literal["candidate", "approved"],
) -> None:
    expected = ReviewStatus.CANDIDATE if status == "candidate" else ReviewStatus.APPROVED
    records = [*cases.records, *failures.records]
    invalid = [item.record_id for item in records if item.review_status is not expected]
    if invalid:
        raise SystemOptimizationBoundaryError(
            f"{status} directory contains records with the wrong review status: {invalid}"
        )


def _guard_record_provenance(
    cases: DevCaseDataset,
    failures: FailureReplayDataset,
) -> None:
    identifiers: list[str] = []
    for case in cases.records:
        identifiers.extend(
            [
                case.record_id,
                *case.task_demand.knowledge_point_ids,
                *(item.evidence_id for item in case.evidence_package.items),
                *(item.source_record_id for item in case.evidence_package.items),
                *(
                    context_id
                    for item in case.evidence_package.items
                    for context_id in item.dev_context_ids
                ),
            ]
        )
    identifiers.extend(item.record_id for item in failures.records)
    forbidden = sorted(
        identifier
        for identifier in identifiers
        if identifier.casefold().startswith(_FORBIDDEN_SOURCE_PREFIXES)
    )
    if forbidden:
        raise SystemOptimizationBoundaryError(
            f"EP-00 data contains forbidden P18-derived identifiers: {forbidden}"
        )


def _validate_approval_bindings(
    root: Path,
    approved_cases: DevCaseDataset,
    approved_failures: FailureReplayDataset,
) -> None:
    candidate_cases = DevCaseDataset.model_validate(
        _read_json(root / "candidates" / "dev_cases.json")
    )
    candidate_failures = FailureReplayDataset.model_validate(
        _read_json(root / "candidates" / "failure_replays.json")
    )
    review_path = root / "approved" / "review_log.jsonl"
    _guard_path(review_path.resolve().relative_to(root))
    if not review_path.is_file():
        raise SystemOptimizationBoundaryError("approved EP-00 review log is missing")
    reviews: dict[str, ReviewLogEntry] = {}
    for line_number, line in enumerate(
        review_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        review = ReviewLogEntry.model_validate_json(line)
        if review.review_id in reviews:
            raise SystemOptimizationBoundaryError(
                f"duplicate approved review ID at line {line_number}: {review.review_id}"
            )
        reviews[review.review_id] = review

    candidate_records = {
        item.record_id: item for item in [*candidate_cases.records, *candidate_failures.records]
    }
    approved_records = [*approved_cases.records, *approved_failures.records]
    if {item.record_id for item in approved_records} != set(candidate_records):
        raise SystemOptimizationBoundaryError(
            "approved EP-00 record IDs differ from the Candidate dataset"
        )
    approval_review_ids: set[str] = set()
    for approved in approved_records:
        candidate = candidate_records[approved.record_id]
        approval = approved.approval
        if approval is None:
            raise SystemOptimizationBoundaryError(
                f"approved record has no approval metadata: {approved.record_id}"
            )
        bound_review = reviews.get(approval.review_id)
        if (
            record_digest(candidate) != approval.candidate_sha256
            or record_digest(approved) != approval.approved_record_sha256
            or bound_review is None
            or bound_review.record_id != approved.record_id
            or bound_review.action != "approve"
            or bound_review.reviewer_id != approval.reviewer_id
            or bound_review.reviewed_at != approval.reviewed_at
            or bound_review.candidate_sha256 != approval.candidate_sha256
            or bound_review.resulting_record_sha256 != approval.approved_record_sha256
        ):
            raise SystemOptimizationBoundaryError(
                f"approved record binding is invalid: {approved.record_id}"
            )
        approval_review_ids.add(approval.review_id)
    if approval_review_ids != set(reviews):
        raise SystemOptimizationBoundaryError(
            "approved EP-00 review log contains missing or unrelated entries"
        )


def check(
    root: Path = DEFAULT_ROOT, *, status: Literal["candidate", "approved"] = "candidate"
) -> dict[str, object]:
    loaded = load_candidate(root) if status == "candidate" else load_approved(root)
    return {
        "dataset_status": loaded.status,
        "quality_metrics_eligible": loaded.metric_eligible,
        "task_cases": len(loaded.cases.records),
        "failure_replays": len(loaded.failures.records),
        "p18_test_or_blind_loaded": False,
        "external_provider_calls": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--status", choices=("candidate", "approved"), default="candidate")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not args.check_only:
        parser.error("EP-00 Loader currently supports only --check-only")
    try:
        result = check(args.root, status=args.status)
    except SystemOptimizationApprovalPending as exc:
        result = {
            "dataset_status": "pending_human_approval",
            "quality_metrics_eligible": False,
            "error": str(exc),
            "p18_test_or_blind_loaded": False,
            "external_provider_calls": 0,
        }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
