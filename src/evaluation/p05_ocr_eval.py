"""Approved-Gold-only P05 OCR provider Runner with checkpoint/resume."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from pydantic import JsonValue

from courserag.evals.ocr_metrics import evaluate_ocr_results
from courserag.evals.schemas import (
    DS1ParsingDataset,
    OCRGold,
    P05OCRBatchApproval,
    P05OCRCandidateManifest,
)
from courserag.parsers.ocr import (
    OCRImageInput,
    OCRPageResult,
    OCRProvider,
    OCRProviderProfile,
    OCRWarning,
    PaddleOCRAdapter,
    RapidOCRAdapter,
    TesseractAdapter,
)
from courserag.parsers.ocr.resource import (
    OCRIdentityError,
    OCRProviderError,
    OCRProviderUnavailable,
    OCRResourceLimitError,
)
from evaluation.contracts import DatasetSplit, FallbackPolicy, HashedArtifact, RunIntent
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.runner import EvaluationRunner

_EVALUATION_SOURCE_PATHS = (
    "src/evaluation/p05_ocr_eval.py",
    "src/evaluation/runner.py",
    "src/evaluation/manifest.py",
    "src/evaluation/datasets.py",
    "src/evaluation/contracts.py",
    "src/evaluation/io.py",
    "src/courserag/evals/ocr_metrics.py",
    "src/courserag/evals/schemas.py",
    "src/courserag/parsers/ocr/providers.py",
    "src/courserag/parsers/ocr/resource.py",
    "src/courserag/parsers/ocr/worker.py",
    "src/courserag/parsers/ocr/types.py",
    "src/courserag/domain/document.py",
)


def run_p05_provider(
    *,
    repository_root: Path,
    dataset_root: Path,
    profile_path: Path,
    output_dir: Path,
    run_id: str,
    image_id: str,
    resume: bool = False,
    git_commit: str | None = None,
    git_dirty: bool | None = None,
) -> dict[str, JsonValue]:
    repository_root = repository_root.resolve()
    dataset_root = dataset_root.resolve()
    output_dir = output_dir.resolve()
    gold_path = dataset_root / "approved/ds1/p05_ocr.json"
    approval_path = dataset_root / "provenance/p05_ocr_approval.json"
    candidate_manifest_path = dataset_root / "provenance/p05_ocr_candidate_manifest.json"
    if not gold_path.is_file() or not approval_path.is_file():
        raise ValueError("P05 OCR Runner requires the exact human-approved OCR Gold batch")
    approval = P05OCRBatchApproval.model_validate_json(approval_path.read_text(encoding="utf-8"))
    candidate_manifest = P05OCRCandidateManifest.model_validate_json(
        candidate_manifest_path.read_text(encoding="utf-8")
    )
    if approval.approved_file_sha256 != sha256_file(gold_path):
        raise ValueError("Approved P05 OCR file differs from its batch approval")
    if (
        approval.candidate_file_sha256 != candidate_manifest.candidate_file_sha256
        or approval.candidate_relative_path != candidate_manifest.candidate_relative_path
    ):
        raise ValueError("Approved P05 OCR batch differs from the active Candidate Manifest")
    dataset = DS1ParsingDataset.model_validate_json(gold_path.read_text(encoding="utf-8"))
    gold = [record for record in dataset.records if isinstance(record, OCRGold)]
    if len(gold) != 15 or any(record.review_status.value != "approved" for record in gold):
        raise ValueError("P05 OCR Runner requires 15 Approved OCR records")
    profile = OCRProviderProfile.model_validate_json(profile_path.read_text(encoding="utf-8"))
    provider = _provider(profile)
    provider.validate_environment()
    review_root = _safe_dataset_path(
        dataset_root,
        candidate_manifest.review_pack_relative_path,
    )
    images = _resolve_images(review_root, gold)
    manifest_path = dataset_root / "manifest.json"
    split_path = dataset_root / "splits/pilot_ids.txt"
    commit, dirty = _git_state(
        repository_root,
        commit_override=git_commit,
        dirty_override=git_dirty,
    )
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(UTC),
        dataset=RunDatasetRef(
            dataset_id=dataset.dataset_id,
            dataset_version=dataset.dataset_version,
            split=DatasetSplit.PILOT,
            manifest_sha256=sha256_file(manifest_path),
            split_sha256=sha256_file(split_path),
        ),
        intent=RunIntent.EVALUATION,
        tuning_enabled=False,
        git_commit=commit,
        git_dirty=dirty,
        input_artifacts=[
            _artifact(repository_root, gold_path, "application/json"),
            _artifact(repository_root, approval_path, "application/json"),
            _artifact(repository_root, candidate_manifest_path, "application/json"),
            _runtime_artifact(
                profile_path,
                logical_path="ocr-runtime/runtime-profile.json",
                media_type="application/json",
            ),
            _runtime_artifact(
                Path(profile.model_manifest_path),
                logical_path="ocr-runtime/model-manifest.json",
                media_type="application/json",
            ),
            *[
                _artifact(repository_root, repository_root / path, "text/x-python")
                for path in _EVALUATION_SOURCE_PATHS
            ],
            *[_artifact(repository_root, path, "image/png") for path in sorted(images.values())],
        ],
        component_versions={
            "provider": profile.provider,
            "model_name": profile.model_name,
            "model_manifest_sha256": profile.model_manifest_sha256,
            "profile_sha256": profile.sha256,
            "evaluation_image_id": image_id,
        },
        configuration={
            "dpi": profile.dpi,
            "max_pixels": profile.max_pixels,
            "timeout_seconds": profile.timeout_seconds,
            "max_memory_bytes": profile.max_memory_bytes,
            "max_workers": profile.max_workers,
            "automatic_tuning": False,
            "runtime_network": "disabled",
        },
        fallback_policy=FallbackPolicy.FAIL_SAMPLE,
        random_seed=0,
        llm_as_judge=False,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    runner = EvaluationRunner(
        manifest=manifest,
        checkpoint_path=output_dir / "checkpoint.json",
        partial_report_path=output_dir / "partial_report.json",
        final_report_path=output_dir / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )
    results: list[OCRPageResult] = []
    for record in gold:
        image_path = images[record.record_id]
        content = image_path.read_bytes()
        image = OCRImageInput(
            page_id=record.record_id,
            png_bytes=content,
            dpi=record.dpi,
            image_width=record.image_width,
            image_height=record.image_height,
            pdf_width_points=record.source_page_width_points,
            pdf_height_points=record.source_page_height_points,
            image_sha256=record.image_sha256,
        )

        def recognize() -> JsonValue:
            result = _recognize_page(provider, image, profile)
            return result.model_dump(mode="json")

        payload = runner.run_case(record.record_id, record_digest(record), recognize)
        results.append(OCRPageResult.model_validate(payload))
    report = evaluate_ocr_results(gold, results)
    report.update(
        {
            "provider": profile.provider,
            "profile_sha256": profile.sha256,
            "model_manifest_sha256": profile.model_manifest_sha256,
            "evaluation_image_id": image_id,
            "automatic_composite_score": None,
            "default_selection": "requires_explicit_human_decision",
        }
    )
    runner.complete(report)
    return report


def record_digest(record: OCRGold) -> str:
    from evaluation.datasets import record_digest as digest

    return digest(record)


def _provider(profile: OCRProviderProfile) -> RapidOCRAdapter | TesseractAdapter | PaddleOCRAdapter:
    if profile.provider == "rapidocr":
        return RapidOCRAdapter(profile)
    if profile.provider == "tesseract":
        return TesseractAdapter(profile)
    return PaddleOCRAdapter(profile)


def _recognize_page(
    provider: OCRProvider,
    image: OCRImageInput,
    profile: OCRProviderProfile,
) -> OCRPageResult:
    try:
        return provider.recognize(image)
    except (OCRIdentityError, OCRProviderUnavailable):
        raise
    except OCRResourceLimitError as exc:
        return _failed_page_result(
            image,
            profile,
            code="OCR_RESOURCE_LIMIT",
            message=str(exc),
            duration_ms=exc.duration_ms,
            peak_memory_bytes=exc.peak_memory_bytes,
        )
    except OCRProviderError as exc:
        return _failed_page_result(
            image,
            profile,
            code="OCR_PAGE_FAILED",
            message="OCR page failed; inspect protected service logs",
            duration_ms=exc.duration_ms,
            peak_memory_bytes=exc.peak_memory_bytes,
        )


def _failed_page_result(
    image: OCRImageInput,
    profile: OCRProviderProfile,
    *,
    code: str,
    message: str,
    duration_ms: int = 0,
    peak_memory_bytes: int = 0,
) -> OCRPageResult:
    return OCRPageResult(
        page_id=image.page_id,
        status="ready_with_warnings",
        engine=profile.provider,
        engine_version="not_completed",
        model_name=profile.model_name,
        model_manifest_sha256=profile.model_manifest_sha256,
        profile_sha256=profile.sha256,
        dpi=image.dpi,
        image_sha256=image.image_sha256,
        image_width=image.image_width,
        image_height=image.image_height,
        text="",
        duration_ms=duration_ms,
        peak_memory_bytes=peak_memory_bytes,
        warnings=(OCRWarning(code=code, message=message),),
    )


def _resolve_images(review_root: Path, gold: list[OCRGold]) -> dict[str, Path]:
    if not review_root.is_dir():
        raise ValueError("Approved OCR review package is missing")
    by_hash = {sha256_file(path): path for path in review_root.glob("*.png")}
    resolved: dict[str, Path] = {}
    for record in gold:
        path = by_hash.get(record.image_sha256)
        if path is None:
            raise ValueError(f"Approved OCR input image is missing: {record.record_id}")
        resolved[record.record_id] = path
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("Approved OCR records do not map one-to-one to input images")
    return resolved


def _safe_dataset_path(dataset_root: Path, repository_relative_path: str) -> Path:
    marker = "datasets/courserag_eval/v1/"
    path = (dataset_root / repository_relative_path.removeprefix(marker)).resolve()
    if not path.is_relative_to(dataset_root):
        raise ValueError("P05 Candidate path escapes the dataset root")
    return path


def _artifact(repository_root: Path, path: Path, media_type: str) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root):
        raise ValueError(f"P05 input is missing or outside repository: {path}")
    return HashedArtifact(
        path=resolved.relative_to(repository_root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type=media_type,
    )


def _runtime_artifact(
    path: Path,
    *,
    logical_path: str,
    media_type: str,
) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError(f"P05 runtime input is missing: {path}")
    return HashedArtifact(
        path=logical_path,
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type=media_type,
    )


def _git_state(
    repository_root: Path,
    *,
    commit_override: str | None = None,
    dirty_override: bool | None = None,
) -> tuple[str, bool]:
    if commit_override is not None or dirty_override is not None:
        if commit_override is None or dirty_override is None:
            raise ValueError("Git Commit and dirty overrides must be provided together")
        if re.fullmatch(r"[0-9a-f]{40}", commit_override) is None:
            raise ValueError("Git Commit override must be a lowercase 40-character SHA-1")
        return commit_override, dirty_override
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    status = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return commit, bool(status.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one Approved-Gold P05 OCR provider Pilot.")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--git-commit")
    parser.add_argument("--git-dirty", action="store_true")
    args = parser.parse_args()
    result = run_p05_provider(
        repository_root=args.repository_root,
        dataset_root=args.dataset_root,
        profile_path=args.profile,
        output_dir=args.output_dir,
        run_id=args.run_id,
        image_id=args.image_id,
        resume=args.resume,
        git_commit=args.git_commit,
        git_dirty=args.git_dirty if args.git_commit is not None else None,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
