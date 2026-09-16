"""Subprocess-isolated adapters for the three approved P05 OCR candidates."""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from courserag.domain.document import sha256_bytes, stable_ir_id
from courserag.parsers.ocr.resource import (
    OCRCommandRunner,
    OCRIdentityError,
    OCRProviderError,
    OCRProviderUnavailable,
    SubprocessResourceGuard,
)
from courserag.parsers.ocr.types import (
    OCRImageInput,
    OCRPageResult,
    OCRProviderProfile,
    OCRRegionResult,
    OCRWarning,
)


class _WorkerRegion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    polygon: tuple[tuple[int, int], ...] = Field(min_length=4)
    confidence: float


class _WorkerResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    engine_version: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    regions: tuple[_WorkerRegion, ...]


class SubprocessOCRAdapter:
    def __init__(
        self,
        profile: OCRProviderProfile,
        *,
        runner: OCRCommandRunner | None = None,
        python_executable: str | None = None,
    ) -> None:
        self.profile = profile
        self.runner = runner
        self.python_executable = python_executable or sys.executable

    @property
    def name(self) -> str:
        return self.profile.provider

    def validate_environment(self) -> None:
        self._validate_model_manifest()
        if self.profile.provider == "tesseract":
            if shutil.which("tesseract") is None:
                raise OCRProviderUnavailable("tesseract executable is unavailable")
            return
        package = "rapidocr" if self.profile.provider == "rapidocr" else "paddleocr"
        command = [self.python_executable, "-c", f"import {package}"]
        runner = self.runner or SubprocessResourceGuard()
        runner.run(
            command,
            timeout_seconds=min(self.profile.timeout_seconds, 15),
            max_memory_bytes=self.profile.max_memory_bytes,
        )

    def _validate_model_manifest(self) -> None:
        path = Path(self.profile.model_manifest_path)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise OCRProviderUnavailable("OCR model manifest is unavailable") from exc
        if sha256_bytes(content) != self.profile.model_manifest_sha256:
            raise OCRProviderUnavailable("OCR model manifest Hash differs from frozen profile")
        try:
            manifest = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OCRProviderUnavailable("OCR model manifest is invalid") from exc
        if not isinstance(manifest, dict) or manifest.get("identity_status") != "resolved":
            raise OCRProviderUnavailable("OCR model manifest identity is not resolved")
        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise OCRProviderUnavailable("OCR model manifest contains no hashed artifacts")

    def recognize(self, image: OCRImageInput) -> OCRPageResult:
        if image.dpi != self.profile.dpi:
            raise ValueError("OCR input DPI differs from the frozen provider profile")
        if image.image_width * image.image_height > self.profile.max_pixels:
            return self._warning_result(
                image,
                code="OCR_PIXEL_LIMIT_EXCEEDED",
                message="OCR page exceeded the configured pixel limit",
            )
        runner = self.runner or SubprocessResourceGuard()
        with tempfile.TemporaryDirectory(prefix="courserag-ocr-") as directory:
            input_path = Path(directory) / "page.png"
            input_path.write_bytes(image.png_bytes)
            output = runner.run(
                [
                    self.python_executable,
                    "-m",
                    "courserag.parsers.ocr.worker",
                    self.profile.provider,
                    str(input_path),
                    self.profile.language,
                ],
                timeout_seconds=self.profile.timeout_seconds,
                max_memory_bytes=self.profile.max_memory_bytes,
            )
        try:
            worker = _WorkerResult.model_validate_json(output.stdout)
        except ValueError as exc:
            raise OCRProviderError("OCR provider returned an invalid result contract") from exc
        if worker.model_name != self.profile.model_name:
            raise OCRIdentityError("OCR provider model identity differs from frozen profile")
        regions = tuple(
            self._region(image, index=index, region=region)
            for index, region in enumerate(worker.regions)
            if region.text.strip()
        )
        confidence = (
            sum(region.confidence for region in regions) / len(regions) if regions else None
        )
        warnings: list[OCRWarning] = []
        if not regions:
            warnings.append(OCRWarning(code="OCR_EMPTY_OUTPUT", message="OCR returned no text"))
        if confidence is not None and confidence < self.profile.min_confidence:
            warnings.append(
                OCRWarning(
                    code="OCR_LOW_CONFIDENCE",
                    message="OCR page confidence is below the configured threshold",
                )
            )
        if regions:
            low_ratio = sum(
                region.confidence < self.profile.low_region_confidence for region in regions
            ) / len(regions)
            if low_ratio > self.profile.max_low_region_ratio:
                warnings.append(
                    OCRWarning(
                        code="OCR_LOW_REGION_CONFIDENCE",
                        message="Too many OCR regions are below the confidence threshold",
                    )
                )
        text = "\n".join(region.text for region in regions)
        return OCRPageResult(
            page_id=image.page_id,
            status="ready_with_warnings" if warnings else "ready",
            engine=self.profile.provider,
            engine_version=worker.engine_version,
            model_name=worker.model_name,
            model_manifest_sha256=self.profile.model_manifest_sha256,
            profile_sha256=self.profile.sha256,
            dpi=image.dpi,
            image_sha256=image.image_sha256,
            image_width=image.image_width,
            image_height=image.image_height,
            text=text,
            regions=regions,
            confidence=confidence,
            duration_ms=output.duration_ms,
            peak_memory_bytes=output.peak_memory_bytes,
            warnings=tuple(warnings),
        )

    def _region(
        self,
        image: OCRImageInput,
        *,
        index: int,
        region: _WorkerRegion,
    ) -> OCRRegionResult:
        xs = [point[0] for point in region.polygon]
        ys = [point[1] for point in region.polygon]
        if (
            min(xs) < 0
            or min(ys) < 0
            or max(xs) > image.image_width
            or max(ys) > image.image_height
        ):
            raise OCRProviderError("OCR provider returned coordinates outside the input image")
        pixel_bbox = (min(xs), min(ys), max(xs), max(ys))
        page_bbox = (
            pixel_bbox[0] * image.pdf_width_points / image.image_width,
            pixel_bbox[1] * image.pdf_height_points / image.image_height,
            pixel_bbox[2] * image.pdf_width_points / image.image_width,
            pixel_bbox[3] * image.pdf_height_points / image.image_height,
        )
        normalized = min(1.0, max(0.0, region.confidence))
        return OCRRegionResult(
            region_id=stable_ir_id("ocrreg", image.page_id, index, region.text, pixel_bbox),
            text=region.text,
            pixel_bbox=pixel_bbox,
            pixel_polygon=region.polygon,
            page_bbox=page_bbox,
            confidence=normalized,
            raw_confidence=region.confidence,
        )

    def _warning_result(
        self,
        image: OCRImageInput,
        *,
        code: str,
        message: str,
    ) -> OCRPageResult:
        return OCRPageResult(
            page_id=image.page_id,
            status="ready_with_warnings",
            engine=self.profile.provider,
            engine_version="not_run",
            model_name=self.profile.model_name,
            model_manifest_sha256=self.profile.model_manifest_sha256,
            profile_sha256=self.profile.sha256,
            dpi=image.dpi,
            image_sha256=image.image_sha256,
            image_width=image.image_width,
            image_height=image.image_height,
            text="",
            duration_ms=0,
            peak_memory_bytes=0,
            warnings=(OCRWarning(code=code, message=message),),
        )


class RapidOCRAdapter(SubprocessOCRAdapter):
    def __init__(
        self,
        profile: OCRProviderProfile,
        *,
        runner: OCRCommandRunner | None = None,
        python_executable: str | None = None,
    ) -> None:
        _require_provider(profile, "rapidocr")
        super().__init__(profile, runner=runner, python_executable=python_executable)


class TesseractAdapter(SubprocessOCRAdapter):
    def __init__(
        self,
        profile: OCRProviderProfile,
        *,
        runner: OCRCommandRunner | None = None,
        python_executable: str | None = None,
    ) -> None:
        _require_provider(profile, "tesseract")
        super().__init__(profile, runner=runner, python_executable=python_executable)


class PaddleOCRAdapter(SubprocessOCRAdapter):
    def __init__(
        self,
        profile: OCRProviderProfile,
        *,
        runner: OCRCommandRunner | None = None,
        python_executable: str | None = None,
    ) -> None:
        _require_provider(profile, "paddleocr")
        super().__init__(profile, runner=runner, python_executable=python_executable)


def _require_provider(
    profile: OCRProviderProfile,
    expected: Literal["rapidocr", "tesseract", "paddleocr"],
) -> None:
    if profile.provider != expected:
        raise ValueError(f"{expected} Adapter requires a matching provider profile")
