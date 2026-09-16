import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

import pytest

from courserag.domain.document import sha256_bytes
from courserag.parsers.ocr import (
    OCRImageInput,
    OCRProviderProfile,
    PaddleOCRAdapter,
    RapidOCRAdapter,
    TesseractAdapter,
)
from courserag.parsers.ocr.resource import (
    OCRCommandOutput,
    OCRProviderError,
    OCRProviderUnavailable,
    OCRResourceLimitError,
    SubprocessResourceGuard,
)


class FakeRunner:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.commands: list[tuple[str, ...]] = []

    def run(
        self,
        command: Sequence[str],
        *,
        timeout_seconds: float,
        max_memory_bytes: int,
    ) -> OCRCommandOutput:
        assert timeout_seconds == 60
        assert max_memory_bytes == 1_610_612_736
        self.commands.append(tuple(command))
        return OCRCommandOutput(
            stdout=json.dumps(self.payload).encode(),
            duration_ms=123,
            peak_memory_bytes=456,
        )


def _profile(provider: str, model_name: str) -> OCRProviderProfile:
    return OCRProviderProfile.model_validate(
        {
            "name": f"{provider}_candidate_v1",
            "provider": provider,
            "model_name": model_name,
            "model_manifest_sha256": "a" * 64,
            "model_manifest_path": "fake-model-manifest.json",
        }
    )


def _image(*, width: int = 100, height: int = 100) -> OCRImageInput:
    content = b"deterministic-png-fixture"
    return OCRImageInput(
        page_id="page-1",
        png_bytes=content,
        dpi=200,
        image_width=width,
        image_height=height,
        pdf_width_points=50,
        pdf_height_points=50,
        image_sha256=sha256_bytes(content),
    )


@pytest.mark.parametrize(
    ("adapter_type", "provider", "model_name"),
    [
        (RapidOCRAdapter, "rapidocr", "rapidocr-bundled"),
        (TesseractAdapter, "tesseract", "tesseract-chi_sim"),
        (PaddleOCRAdapter, "paddleocr", "paddleocr-ch"),
    ],
)
def test_all_adapters_satisfy_the_same_result_contract(
    adapter_type: type[RapidOCRAdapter | TesseractAdapter | PaddleOCRAdapter],
    provider: str,
    model_name: str,
) -> None:
    runner = FakeRunner(
        {
            "engine_version": "1.0",
            "model_name": model_name,
            "regions": [
                {
                    "text": "课程内容",
                    "polygon": [[10, 20], [60, 20], [60, 40], [10, 40]],
                    "confidence": 0.9,
                }
            ],
        }
    )
    adapter = adapter_type(_profile(provider, model_name), runner=runner)

    result = adapter.recognize(_image())

    assert result.status == "ready"
    assert result.engine == provider
    assert result.text == "课程内容"
    assert result.regions[0].pixel_bbox == (10, 20, 60, 40)
    assert result.regions[0].page_bbox == (5, 10, 30, 20)
    assert result.duration_ms == 123
    assert result.peak_memory_bytes == 456
    assert result.result_sha256 == result.result_sha256


def test_low_confidence_and_empty_output_are_not_silent() -> None:
    low_runner = FakeRunner(
        {
            "engine_version": "1.0",
            "model_name": "rapidocr-bundled",
            "regions": [
                {
                    "text": "不确定",
                    "polygon": [[1, 1], [20, 1], [20, 20], [1, 20]],
                    "confidence": 0.4,
                }
            ],
        }
    )
    empty_runner = FakeRunner(
        {"engine_version": "1.0", "model_name": "rapidocr-bundled", "regions": []}
    )

    low = RapidOCRAdapter(_profile("rapidocr", "rapidocr-bundled"), runner=low_runner).recognize(
        _image()
    )
    empty = RapidOCRAdapter(
        _profile("rapidocr", "rapidocr-bundled"), runner=empty_runner
    ).recognize(_image())

    assert low.status == "ready_with_warnings"
    assert {warning.code for warning in low.warnings} == {
        "OCR_LOW_CONFIDENCE",
        "OCR_LOW_REGION_CONFIDENCE",
    }
    assert empty.status == "ready_with_warnings"
    assert [warning.code for warning in empty.warnings] == ["OCR_EMPTY_OUTPUT"]


def test_pixel_limit_rejects_page_before_provider_execution() -> None:
    runner = FakeRunner({})
    profile = _profile("rapidocr", "rapidocr-bundled").model_copy(update={"max_pixels": 50})
    result = RapidOCRAdapter(profile, runner=runner).recognize(_image())

    assert result.status == "ready_with_warnings"
    assert [warning.code for warning in result.warnings] == ["OCR_PIXEL_LIMIT_EXCEEDED"]
    assert runner.commands == []


def test_adapter_rejects_mismatched_profile() -> None:
    with pytest.raises(ValueError, match="matching provider profile"):
        RapidOCRAdapter(_profile("tesseract", "tesseract-chi_sim"), runner=FakeRunner({}))


def test_unresolved_or_hash_mismatched_model_manifest_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"identity_status": "unresolved", "artifacts": []}), encoding="utf-8"
    )
    profile = _profile("rapidocr", "rapidocr-bundled").model_copy(
        update={
            "model_manifest_path": str(path),
            "model_manifest_sha256": sha256_bytes(path.read_bytes()),
        }
    )
    adapter = RapidOCRAdapter(profile, runner=FakeRunner({}))

    with pytest.raises(OCRProviderUnavailable, match="identity is not resolved"):
        adapter.validate_environment()

    mismatched = RapidOCRAdapter(
        profile.model_copy(update={"model_manifest_sha256": "f" * 64}),
        runner=FakeRunner({}),
    )
    with pytest.raises(OCRProviderUnavailable, match="Hash differs"):
        mismatched.validate_environment()


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 42
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: float) -> int:
        assert timeout == 5
        self.returncode = -9
        return self.returncode

    def communicate(self) -> tuple[bytes, bytes]:
        return b"", b""


class _LimitSampler:
    def __init__(self, process: _FakeProcess, rss: int) -> None:
        self.process = process
        self.rss = rss
        self.terminated = False

    def rss_bytes(self, pid: int) -> int:
        assert pid == self.process.pid
        return self.rss

    def terminate(self, pid: int) -> None:
        assert pid == self.process.pid
        self.terminated = True
        self.process.returncode = -9


def test_resource_guard_kills_process_tree_on_memory_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeProcess()
    sampler = _LimitSampler(process, rss=101)
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    guard = SubprocessResourceGuard(sampler=sampler)

    with pytest.raises(OCRResourceLimitError, match="memory limit"):
        guard.run(["fake"], timeout_seconds=60, max_memory_bytes=100)
    assert sampler.terminated


def test_resource_guard_kills_process_tree_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeProcess()
    sampler = _LimitSampler(process, rss=0)
    times = iter((0.0, 2.0))
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr("courserag.parsers.ocr.resource.time.monotonic", lambda: next(times))
    guard = SubprocessResourceGuard(sampler=sampler)

    with pytest.raises(OCRResourceLimitError, match="timeout"):
        guard.run(["fake"], timeout_seconds=1, max_memory_bytes=100)
    assert sampler.terminated


def test_resource_guard_preserves_timing_for_protected_provider_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    process = _FakeProcess()
    process.returncode = 1
    sampler = _LimitSampler(process, rss=0)
    times = iter((0.0, 1.25))
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: process)
    monkeypatch.setattr("courserag.parsers.ocr.resource.time.monotonic", lambda: next(times))
    guard = SubprocessResourceGuard(sampler=sampler)

    with pytest.raises(OCRProviderError, match="protected service logs") as captured:
        guard.run(["fake"], timeout_seconds=60, max_memory_bytes=100)

    assert captured.value.duration_ms == 1250
    assert captured.value.peak_memory_bytes == 0
