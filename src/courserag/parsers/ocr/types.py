"""Provider-neutral OCR contracts with deterministic identity and validation."""

from __future__ import annotations

from typing import Annotated, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from courserag.domain.document import BBox, canonical_json_bytes, sha256_bytes

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
PixelBBox = tuple[int, int, int, int]
PixelPoint = tuple[int, int]


class StrictOCRModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OCRWarning(StrictOCRModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=120)
    message: str = Field(min_length=1, max_length=1000)


class OCRImageInput(StrictOCRModel):
    page_id: str = Field(min_length=1, max_length=160)
    png_bytes: bytes = Field(min_length=1, exclude=True)
    dpi: int = Field(ge=72, le=600)
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    pdf_width_points: float = Field(gt=0)
    pdf_height_points: float = Field(gt=0)
    image_sha256: Sha256

    @model_validator(mode="after")
    def validate_image_hash(self) -> OCRImageInput:
        if sha256_bytes(self.png_bytes) != self.image_sha256:
            raise ValueError("OCR image bytes do not match image_sha256")
        return self


class OCRRegionResult(StrictOCRModel):
    region_id: str = Field(min_length=1, max_length=160)
    text: str
    pixel_bbox: PixelBBox
    pixel_polygon: tuple[PixelPoint, ...] = Field(min_length=4)
    page_bbox: BBox
    confidence: float = Field(ge=0, le=1)
    raw_confidence: float

    @model_validator(mode="after")
    def validate_coordinates(self) -> OCRRegionResult:
        x0, y0, x1, y1 = self.pixel_bbox
        if x1 <= x0 or y1 <= y0 or min(x0, y0) < 0:
            raise ValueError("OCR pixel bbox must have positive area in top-left coordinates")
        px0, py0, px1, py1 = self.page_bbox
        if px1 <= px0 or py1 <= py0 or min(px0, py0) < 0:
            raise ValueError("OCR page bbox must have positive area in top-left coordinates")
        return self


class OCRPageResult(StrictOCRModel):
    schema_version: Literal["courserag.ocr-page-result.v1"] = "courserag.ocr-page-result.v1"
    page_id: str = Field(min_length=1, max_length=160)
    status: Literal["ready", "ready_with_warnings", "failed"]
    engine: Literal["rapidocr", "tesseract", "paddleocr"]
    engine_version: str = Field(min_length=1, max_length=160)
    model_name: str = Field(min_length=1, max_length=240)
    model_manifest_sha256: Sha256
    profile_sha256: Sha256
    dpi: int = Field(ge=72, le=600)
    image_sha256: Sha256
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    text: str
    regions: tuple[OCRRegionResult, ...] = ()
    confidence: float | None = Field(default=None, ge=0, le=1)
    duration_ms: int = Field(ge=0)
    peak_memory_bytes: int = Field(ge=0)
    warnings: tuple[OCRWarning, ...] = ()

    @model_validator(mode="after")
    def validate_status(self) -> OCRPageResult:
        if self.status == "ready" and self.warnings:
            raise ValueError("ready OCR result cannot contain warnings")
        if self.status == "ready" and not self.regions:
            raise ValueError("ready OCR result requires at least one region")
        if self.regions and self.confidence is None:
            raise ValueError("OCR regions require a page confidence")
        return self

    @property
    def result_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))

    @property
    def semantic_sha256(self) -> str:
        payload = self.model_dump(mode="json", exclude={"duration_ms", "peak_memory_bytes"})
        return sha256_bytes(canonical_json_bytes(payload))


class OCRProviderProfile(StrictOCRModel):
    schema_version: Literal["courserag.ocr-profile.v1"] = "courserag.ocr-profile.v1"
    name: str = Field(min_length=1, max_length=160)
    provider: Literal["rapidocr", "tesseract", "paddleocr"]
    model_name: str = Field(min_length=1, max_length=240)
    model_manifest_sha256: Sha256
    model_manifest_path: str = Field(min_length=1, max_length=1024)
    language: str = Field(default="ch", min_length=1, max_length=80)
    dpi: int = Field(default=200, ge=72, le=600)
    max_pixels: int = Field(default=20_000_000, ge=1)
    timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    max_memory_bytes: int = Field(default=1_610_612_736, ge=64 * 1024 * 1024)
    max_workers: Literal[1] = 1
    min_confidence: float = Field(default=0.75, ge=0, le=1)
    low_region_confidence: float = Field(default=0.50, ge=0, le=1)
    max_low_region_ratio: float = Field(default=0.25, ge=0, le=1)

    @property
    def sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class OCRProvider(Protocol):
    @property
    def name(self) -> str: ...

    def validate_environment(self) -> None: ...

    def recognize(self, image: OCRImageInput) -> OCRPageResult: ...
