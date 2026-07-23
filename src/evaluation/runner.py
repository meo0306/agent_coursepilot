from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, JsonValue

from evaluation.contracts import DatasetSplit, StrictModel
from evaluation.guard import validate_dataset_ref_files, validate_test_run_files
from evaluation.io import atomic_write_json
from evaluation.manifest import RunManifest


class RunConfigurationMismatch(ValueError):
    """Raised before mutation when a checkpoint identity differs from the requested run."""


class EvaluationCaseState(StrictModel):
    case_id: str
    case_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: str
    attempt: int = Field(ge=1)
    started_at: datetime
    finished_at: datetime | None = None
    latency_ms: int | None = Field(default=None, ge=0)
    result: JsonValue = None
    error_type: str | None = None
    error_message: str | None = None


class EvaluationCheckpoint(StrictModel):
    schema_version: str = "course-eval.checkpoint.v1"
    run_id: str
    run_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: str
    started_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None
    cases: dict[str, EvaluationCaseState] = Field(default_factory=dict)


def utc_now() -> datetime:
    return datetime.now(UTC)


class EvaluationRunner:
    def __init__(
        self,
        *,
        manifest: RunManifest,
        checkpoint_path: Path,
        partial_report_path: Path,
        final_report_path: Path,
        dataset_root: Path,
        resume: bool = False,
    ) -> None:
        self.manifest = manifest
        self.checkpoint_path = checkpoint_path.resolve()
        self.partial_report_path = partial_report_path.resolve()
        self.final_report_path = final_report_path.resolve()
        self.dataset_root = dataset_root.resolve()
        self.resume = resume
        self._validate_output_boundaries()
        validate_dataset_ref_files(manifest, self.dataset_root)
        if manifest.dataset.split is DatasetSplit.TEST:
            validate_test_run_files(manifest, self.dataset_root)
        if resume:
            state = self._load_checkpoint_without_mutation()
            if state.run_identity_sha256 != manifest.identity_sha256:
                raise RunConfigurationMismatch(
                    "checkpoint Run Manifest identity differs from the requested configuration"
                )
            if state.run_id != manifest.run_id:
                raise RunConfigurationMismatch("checkpoint run_id differs from Run Manifest")
            state.status = "running"
            state.completed_at = None
            self.state = state
        else:
            if self.checkpoint_path.exists():
                raise FileExistsError(
                    f"evaluation checkpoint already exists: {self.checkpoint_path}"
                )
            now = utc_now()
            self.state = EvaluationCheckpoint(
                run_id=manifest.run_id,
                run_identity_sha256=manifest.identity_sha256,
                status="running",
                started_at=now,
                updated_at=now,
            )
        self._persist()

    def run_case(
        self,
        case_id: str,
        case_sha256: str,
        fn: Callable[[], JsonValue],
    ) -> JsonValue:
        existing = self.state.cases.get(case_id)
        if existing is not None and existing.case_sha256 != case_sha256:
            raise RunConfigurationMismatch(f"case hash changed for {case_id!r}")
        if self.resume and existing is not None and existing.status == "succeeded":
            return existing.result

        attempt = 1 if existing is None else existing.attempt + 1
        case = EvaluationCaseState(
            case_id=case_id,
            case_sha256=case_sha256,
            status="running",
            attempt=attempt,
            started_at=utc_now(),
        )
        self.state.cases[case_id] = case
        self.state.status = "running"
        self._persist()
        started = time.perf_counter()
        try:
            result = fn()
        except Exception as exc:
            case.status = "failed"
            case.finished_at = utc_now()
            case.latency_ms = _elapsed_ms(started)
            case.error_type = type(exc).__name__
            case.error_message = (
                "case execution failed; details are omitted from persisted evaluation artifacts"
            )
            self.state.status = "failed"
            self._persist()
            raise
        case.status = "succeeded"
        case.finished_at = utc_now()
        case.latency_ms = _elapsed_ms(started)
        case.result = result
        case.error_type = None
        case.error_message = None
        self._persist()
        return result

    def complete(self, report: dict[str, JsonValue]) -> None:
        self.state.status = "completed"
        self.state.completed_at = utc_now()
        self._persist_checkpoint()
        payload: dict[str, JsonValue] = {
            "schema_version": "course-eval.report.v1",
            "manifest": self.manifest.model_dump(mode="json"),
            "run_identity_sha256": self.manifest.identity_sha256,
            "status": "completed",
            "cases": {
                case_id: state.model_dump(mode="json")
                for case_id, state in self.state.cases.items()
            },
            "report": report,
        }
        atomic_write_json(self.final_report_path, payload)

    def _validate_output_boundaries(self) -> None:
        outputs = (self.checkpoint_path, self.partial_report_path, self.final_report_path)
        if len(set(outputs)) != len(outputs):
            raise ValueError("checkpoint, partial report, and final report paths must differ")
        datasets_root = next(
            (
                candidate
                for candidate in (self.dataset_root, *self.dataset_root.parents)
                if candidate.name.casefold() == "datasets"
            ),
            None,
        )
        if datasets_root is None:
            raise ValueError("dataset_root must be located under a datasets directory")
        for output in outputs:
            if output == datasets_root or datasets_root in output.parents:
                raise ValueError("evaluation runtime outputs cannot be written inside datasets")

    def _load_checkpoint_without_mutation(self) -> EvaluationCheckpoint:
        if not self.checkpoint_path.is_file():
            raise FileNotFoundError(f"evaluation checkpoint not found: {self.checkpoint_path}")
        return EvaluationCheckpoint.model_validate_json(
            self.checkpoint_path.read_text(encoding="utf-8")
        )

    def _persist(self) -> None:
        self._persist_checkpoint()
        partial: dict[str, JsonValue] = {
            "schema_version": "course-eval.partial-report.v1",
            "manifest": self.manifest.model_dump(mode="json"),
            "run_identity_sha256": self.manifest.identity_sha256,
            "status": self.state.status,
            "cases": {
                case_id: state.model_dump(mode="json")
                for case_id, state in self.state.cases.items()
            },
        }
        atomic_write_json(self.partial_report_path, partial)

    def _persist_checkpoint(self) -> None:
        self.state.updated_at = utc_now()
        atomic_write_json(self.checkpoint_path, self.state.model_dump(mode="json"))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
