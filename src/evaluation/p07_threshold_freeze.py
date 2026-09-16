"""Generate and approve the P07 threshold freeze after Calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator

from evaluation.contracts import HashedArtifact, Sha256, StrictModel
from evaluation.datasets import canonical_json_bytes
from evaluation.io import atomic_write_json
from evaluation.manifest import sha256_file

CALIBRATION_DIR = Path("storage_eval/p07_kp_calibration/run-4")
CALIBRATION_REPORT = CALIBRATION_DIR / "report.json"
CALIBRATION_OUTPUT = CALIBRATION_DIR / "system_outputs.json"
THRESHOLD_CANDIDATE = CALIBRATION_DIR / "threshold_freeze_candidate.json"
THRESHOLD_APPROVAL = CALIBRATION_DIR / "threshold_freeze_approval.json"
APPROVED_DS3 = Path("datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json")
PROTOCOL_BUNDLE_SHA256 = "7261cb63b81f5b2e260a6a578383bd41df55c690aae999891d479146395b215b"


class ThresholdMetricRow(StrictModel):
    threshold: float = Field(ge=0, le=1)
    published_count: int = Field(ge=0)
    true_positive_count: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)


class P07ThresholdFreezeCandidate(StrictModel):
    schema_version: Literal["courserag.p07-threshold-freeze.v1"] = (
        "courserag.p07-threshold-freeze.v1"
    )
    candidate_bundle_sha256: Sha256
    evaluation_protocol_bundle_sha256: Sha256
    calibration_run_identity_sha256: Sha256
    calibration_report: HashedArtifact
    calibration_system_outputs: HashedArtifact
    approved_knowledge_points: HashedArtifact
    current_threshold: float = Field(ge=0, le=1)
    recommended_threshold: float = Field(ge=0, le=1)
    threshold_change_required: bool
    selection_rule: str = Field(min_length=1, max_length=1000)
    recommended_metric: ThresholdMetricRow
    evaluated_thresholds: list[float] = Field(min_length=2)
    holdout_constraints: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> P07ThresholdFreezeCandidate:
        if self.candidate_bundle_sha256 != _candidate_digest(self):
            raise ValueError("P07 threshold Candidate SHA-256 differs from its identity")
        if self.recommended_metric.threshold != self.recommended_threshold:
            raise ValueError("recommended threshold differs from its metric row")
        if self.threshold_change_required != (self.current_threshold != self.recommended_threshold):
            raise ValueError("threshold change flag differs from the selected threshold")
        return self


class P07ThresholdFreezeApproval(StrictModel):
    schema_version: Literal["courserag.p07-threshold-freeze-approval.v1"] = (
        "courserag.p07-threshold-freeze-approval.v1"
    )
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    candidate_bundle_sha256: Sha256
    threshold_candidate: HashedArtifact
    approved_threshold: float = Field(ge=0, le=1)
    notes: str = Field(min_length=1, max_length=4000)


def generate_threshold_candidate(repository_root: Path) -> P07ThresholdFreezeCandidate:
    root = repository_root.resolve()
    report_path = root / CALIBRATION_REPORT
    output_path = root / CALIBRATION_OUTPUT
    gold_path = root / APPROVED_DS3
    envelope = json.loads(report_path.read_text(encoding="utf-8"))
    report = envelope["report"]
    if envelope.get("status") != "completed" or report.get("evaluation_partition") != "calibration":
        raise ValueError("P07 threshold freeze requires a completed Calibration report")
    if report.get("evaluation_protocol_bundle_sha256") != PROTOCOL_BUNDLE_SHA256:
        raise ValueError("Calibration report uses a different P07 evaluation Protocol")
    if any(
        report.get(key)
        for key in ("fallback_used", "llm_as_judge_used", "gold_used_as_provider_input")
    ):
        raise ValueError("unsafe Calibration output cannot freeze a threshold")
    if report.get("split_isolation", {}).get("status") != "passed":
        raise ValueError("Calibration split isolation did not pass")
    recommended = ThresholdMetricRow.model_validate(report["recommended_threshold_candidate"])
    rows = [ThresholdMetricRow.model_validate(item) for item in report["threshold_report"]]
    current_threshold = float(envelope["manifest"]["configuration"]["fixed_publish_threshold"])
    provisional = P07ThresholdFreezeCandidate.model_construct(
        candidate_bundle_sha256="0" * 64,
        evaluation_protocol_bundle_sha256=PROTOCOL_BUNDLE_SHA256,
        calibration_run_identity_sha256=envelope["run_identity_sha256"],
        calibration_report=_artifact(root, report_path),
        calibration_system_outputs=_artifact(root, output_path),
        approved_knowledge_points=_artifact(root, gold_path),
        current_threshold=current_threshold,
        recommended_threshold=recommended.threshold,
        threshold_change_required=current_threshold != recommended.threshold,
        selection_rule=(
            "Maximize F1, then precision, then recall, then proximity to the frozen 0.75 default, "
            "then the higher threshold; model confidence is excluded."
        ),
        recommended_metric=recommended,
        evaluated_thresholds=[row.threshold for row in rows],
        holdout_constraints=[
            "Run Holdout exactly once after exact Candidate approval.",
            "Do not tune the threshold, Prompt, model, Window Profile, or matcher on Holdout.",
            "Do not use Provider output to revise or approve Gold.",
            "Fail closed without Provider fallback or LLM-as-a-Judge.",
        ],
    )
    candidate = P07ThresholdFreezeCandidate(
        **{
            **provisional.model_dump(),
            "candidate_bundle_sha256": _candidate_digest(provisional),
        }
    )
    path = root / THRESHOLD_CANDIDATE
    atomic_write_json(path, candidate.model_dump(mode="json"))
    return candidate


def approve_threshold_candidate(
    *,
    repository_root: Path,
    expected_bundle_sha256: str,
    reviewer_id: str,
    reviewed_at: datetime,
    review_id: str,
    notes: str,
) -> P07ThresholdFreezeApproval:
    root = repository_root.resolve()
    candidate_path = root / THRESHOLD_CANDIDATE
    candidate = P07ThresholdFreezeCandidate.model_validate_json(
        candidate_path.read_text(encoding="utf-8")
    )
    if candidate.candidate_bundle_sha256 != expected_bundle_sha256:
        raise ValueError("literal threshold Candidate SHA-256 differs")
    for artifact in (
        candidate.calibration_report,
        candidate.calibration_system_outputs,
        candidate.approved_knowledge_points,
    ):
        _validate_artifact(root, artifact)
    approval = P07ThresholdFreezeApproval(
        review_id=review_id,
        reviewer_id=reviewer_id,
        reviewed_at=reviewed_at,
        candidate_bundle_sha256=candidate.candidate_bundle_sha256,
        threshold_candidate=_artifact(root, candidate_path),
        approved_threshold=candidate.recommended_threshold,
        notes=notes,
    )
    approval_path = root / THRESHOLD_APPROVAL
    if approval_path.exists():
        existing = P07ThresholdFreezeApproval.model_validate_json(
            approval_path.read_text(encoding="utf-8")
        )
        if existing != approval:
            raise ValueError("existing P07 threshold approval differs")
    else:
        atomic_write_json(approval_path, approval.model_dump(mode="json"))
    return approval


def _candidate_digest(candidate: P07ThresholdFreezeCandidate) -> str:
    payload = candidate.model_dump(mode="json")
    payload.pop("candidate_bundle_sha256", None)
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _artifact(root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    return HashedArtifact(
        path=resolved.relative_to(root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/json",
    )


def _validate_artifact(root: Path, artifact: HashedArtifact) -> None:
    path = (root / artifact.path).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("threshold artifact is missing or outside repository")
    if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
        raise ValueError("threshold artifact identity changed")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate")
    generate.add_argument("--repository-root", type=Path, default=Path.cwd())
    approve = subparsers.add_parser("approve")
    approve.add_argument("--repository-root", type=Path, default=Path.cwd())
    approve.add_argument("--expected-bundle-sha256", required=True)
    approve.add_argument("--reviewer-id", required=True)
    approve.add_argument("--reviewed-at", type=datetime.fromisoformat, required=True)
    approve.add_argument("--review-id", required=True)
    approve.add_argument("--notes", required=True)
    args = parser.parse_args()
    if args.command == "generate":
        candidate = generate_threshold_candidate(args.repository_root)
        print(json.dumps(candidate.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))
        return
    approval = approve_threshold_candidate(
        repository_root=args.repository_root,
        expected_bundle_sha256=args.expected_bundle_sha256,
        reviewer_id=args.reviewer_id,
        reviewed_at=args.reviewed_at,
        review_id=args.review_id,
        notes=args.notes,
    )
    print(json.dumps(approval.model_dump(mode="json"), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
