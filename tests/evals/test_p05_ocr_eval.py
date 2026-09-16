import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from courserag.domain.document import sha256_bytes
from courserag.evals.ocr_metrics import evaluate_ocr_results, routing_metrics
from courserag.evals.schemas import OCRGold, OCRRegion
from courserag.parsers.ocr import (
    OCRImageInput,
    OCRPageResult,
    OCRProviderProfile,
    OCRRegionResult,
    runtime_profile,
)
from courserag.parsers.ocr.resource import OCRResourceLimitError
from evaluation.contracts import ApprovalRecord, SourceSpan
from evaluation.p05_ocr_compare import compare_runs
from evaluation.p05_ocr_eval import _git_state, _recognize_page, run_p05_provider


def _gold() -> OCRGold:
    text = "人工智能"
    raw_text = "页眉\n人工智能"
    provisional = OCRGold(
        record_id="ocr-1",
        review_status="candidate",
        source_span=SourceSpan(
            document_id="source",
            document_version="v1",
            document_sha256="a" * 64,
            page_start=1,
            page_end=1,
        ),
        ocr_input_document_id="scan",
        ocr_input_document_version="v1-scan",
        ocr_input_document_sha256="b" * 64,
        ocr_input_page_number=1,
        image_sha256="c" * 64,
        image_width=100,
        image_height=100,
        dpi=200,
        source_page_width_points=50,
        source_page_height_points=50,
        raw_text=raw_text,
        raw_text_sha256=hashlib.sha256(raw_text.encode()).hexdigest(),
        gold_text=text,
        gold_text_sha256=hashlib.sha256(text.encode()).hexdigest(),
        regions=[
            OCRRegion(
                region_id="gold-region",
                bbox=(10, 10, 60, 30),
                source_bbox_pdf_points=(5, 5, 30, 15),
                role="body",
                gold_text=text,
                include_in_body_text=True,
                body_order_index=0,
            ),
            OCRRegion(
                region_id="gold-header",
                bbox=(0, 0, 100, 8),
                source_bbox_pdf_points=(0, 0, 50, 4),
                role="header",
                gold_text="页眉",
                include_in_body_text=False,
            ),
        ],
        reading_order=["gold-region"],
    )
    return OCRGold.model_validate(
        {
            **provisional.model_dump(mode="json"),
            "review_status": "approved",
            "approval": ApprovalRecord(
                review_id="review-1",
                reviewer_id="course_owner",
                reviewed_at="2026-08-02T00:00:00Z",
                candidate_sha256="d" * 64,
                approved_record_sha256="e" * 64,
            ).model_dump(mode="json"),
        }
    )


def _result() -> OCRPageResult:
    body_region = OCRRegionResult(
        region_id="result-region",
        text="人工智X",
        pixel_bbox=(10, 10, 60, 30),
        pixel_polygon=((10, 10), (60, 10), (60, 30), (10, 30)),
        page_bbox=(5, 5, 30, 15),
        confidence=0.9,
        raw_confidence=0.9,
    )
    header_region = OCRRegionResult(
        region_id="result-header",
        text="页眉",
        pixel_bbox=(0, 1, 100, 7),
        pixel_polygon=((0, 1), (100, 1), (100, 7), (0, 7)),
        page_bbox=(0, 0.5, 50, 3.5),
        confidence=0.9,
        raw_confidence=0.9,
    )
    return OCRPageResult(
        page_id="ocr-1",
        status="ready",
        engine="rapidocr",
        engine_version="1",
        model_name="rapidocr-bundled",
        model_manifest_sha256="f" * 64,
        profile_sha256="1" * 64,
        dpi=200,
        image_sha256="c" * 64,
        image_width=100,
        image_height=100,
        text=f"{header_region.text}\n{body_region.text}",
        regions=(header_region, body_region),
        confidence=0.9,
        duration_ms=100,
        peak_memory_bytes=200,
    )


def test_routing_and_ocr_metrics_have_frozen_denominators() -> None:
    routing = routing_metrics(
        {"native": "native", "scan": "ocr", "mixed": "native"},
        {"native": "native", "scan": "ocr", "mixed": "hybrid"},
    )
    report = evaluate_ocr_results([_gold()], [_result()])

    assert routing["ocr_routing_precision"].value == 1
    assert routing["ocr_routing_recall"].value == 0.5
    assert routing["confusion"]["hybrid"]["native"] == 1
    assert report["macro_cer"] == 0.25
    assert report["micro_cer"] == 0.25
    assert report["body_macro_cer"] == 0.25
    assert report["gold_body_region_count"] == 1
    assert report["gold_excluded_region_count"] == 1
    assert report["predicted_excluded_region_count"] == 1
    assert report["mean_bbox_iou"] == 1
    assert report["region_recall_at_iou_0_5"] == 1
    assert report["p50_latency_ms"] == 100
    assert report["peak_memory_bytes"] == 200
    assert report["resource_limit_page_count"] == 0
    assert report["provider_failure_page_count"] == 0


def test_runner_refuses_to_start_without_human_approved_gold(tmp_path: Path) -> None:
    dataset_root = tmp_path / "datasets" / "courserag_eval" / "v1"
    dataset_root.mkdir(parents=True)
    with pytest.raises(ValueError, match="human-approved OCR Gold"):
        run_p05_provider(
            repository_root=tmp_path,
            dataset_root=dataset_root,
            profile_path=tmp_path / "profile.json",
            output_dir=tmp_path / "runtime",
            run_id="p05-test",
            image_id="image:test",
        )
    assert not (tmp_path / "runtime").exists()


def test_tesseract_model_discovery_accepts_quoted_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_file = tmp_path / "chi_sim.traineddata"
    model_file.write_bytes(b"model")
    monkeypatch.setattr(runtime_profile.shutil, "which", lambda executable: f"/{executable}")
    monkeypatch.setattr(
        runtime_profile.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=f'List of available languages in "{tmp_path}" (1):\nchi_sim\n',
        ),
    )

    assert runtime_profile._model_files("tesseract") == [model_file.resolve()]


def test_default_v1_selects_rapidocr_with_approved_resource_envelope() -> None:
    profile = OCRProviderProfile.model_validate_json(
        Path("resources/ocr_profiles/default_v1.json").read_text(encoding="utf-8")
    )

    assert profile.name == "default_v1"
    assert profile.provider == "rapidocr"
    assert profile.timeout_seconds == 90
    assert profile.dpi == 200
    assert profile.max_pixels == 20_000_000
    assert profile.max_memory_bytes == 1_610_612_736
    assert profile.max_workers == 1


def test_runtime_profile_resolves_default_model_identity_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model-v1")
    monkeypatch.setattr(runtime_profile, "_model_files", lambda provider: [model])
    output_dir = tmp_path / "runtime"

    first = runtime_profile.prepare_runtime_profile(
        candidate_profile_path=Path("resources/ocr_profiles/default_v1.json"),
        output_dir=output_dir,
    )
    second = runtime_profile.prepare_runtime_profile(
        candidate_profile_path=Path("resources/ocr_profiles/default_v1.json"),
        output_dir=output_dir,
    )
    resolved = OCRProviderProfile.model_validate_json(
        (output_dir / "runtime-profile.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((output_dir / "model-manifest.json").read_text(encoding="utf-8"))

    assert first == second
    assert resolved.name == "default_v1"
    assert resolved.timeout_seconds == 90
    assert manifest["identity_status"] == "resolved"
    assert manifest["artifacts"][0]["sha256"] == hashlib.sha256(b"model-v1").hexdigest()
    assert not list(output_dir.glob("*.tmp"))


def test_runner_accepts_validated_host_git_identity(tmp_path: Path) -> None:
    commit = "a" * 40

    assert _git_state(
        tmp_path,
        commit_override=commit,
        dirty_override=True,
    ) == (commit, True)
    with pytest.raises(ValueError, match="lowercase 40-character SHA-1"):
        _git_state(
            tmp_path,
            commit_override="not-a-commit",
            dirty_override=True,
        )


def test_runner_converts_page_timeout_to_traceable_warning() -> None:
    content = b"png"
    image = OCRImageInput(
        page_id="page-timeout",
        png_bytes=content,
        dpi=200,
        image_width=10,
        image_height=10,
        pdf_width_points=5,
        pdf_height_points=5,
        image_sha256=sha256_bytes(content),
    )
    profile = OCRProviderProfile(
        name="rapidocr_candidate_v1",
        provider="rapidocr",
        model_name="rapidocr-bundled",
        model_manifest_sha256="a" * 64,
        model_manifest_path="model-manifest.json",
    )

    class TimedOutProvider:
        @property
        def name(self) -> str:
            return "rapidocr"

        def validate_environment(self) -> None:
            return

        def recognize(self, image: OCRImageInput) -> OCRPageResult:
            raise OCRResourceLimitError(
                "OCR page exceeded the configured timeout",
                duration_ms=60_001,
                peak_memory_bytes=700_000_000,
            )

    result = _recognize_page(TimedOutProvider(), image, profile)

    assert result.status == "ready_with_warnings"
    assert result.duration_ms == 60_001
    assert result.peak_memory_bytes == 700_000_000
    assert [warning.code for warning in result.warnings] == ["OCR_RESOURCE_LIMIT"]


def test_comparison_binds_complete_deployment_evidence(tmp_path: Path) -> None:
    report_paths: dict[str, tuple[Path, Path]] = {}
    for provider in ("rapidocr", "tesseract", "paddleocr"):
        paths = (tmp_path / f"{provider}-1.json", tmp_path / f"{provider}-2.json")
        result = _result().model_copy(update={"engine": provider})
        payload = {
            "status": "completed",
            "cases": {"ocr-1": {"result": result.model_dump(mode="json")}},
            "report": {"provider": provider},
        }
        for path in paths:
            path.write_text(json.dumps(payload), encoding="utf-8")
        report_paths[provider] = paths
    evidence_path = tmp_path / "deployment.json"
    evidence_path.write_text(
        json.dumps(
            {
                "schema_version": "courserag.p05-ocr-deployment-evidence.v1",
                "providers": {provider: {"image_size_bytes": 1} for provider in report_paths},
            }
        ),
        encoding="utf-8",
    )

    comparison = compare_runs(
        reports=report_paths,
        output_path=tmp_path / "comparison.json",
        deployment_evidence_path=evidence_path,
    )

    assert (
        comparison["deployment_evidence_sha256"]
        == hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    )
    assert comparison["automatic_composite_score"] is None
