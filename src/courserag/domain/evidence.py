"""Stable, source-addressable Evidence domain objects for the P06 pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from courserag.domain.document import (
    BBox,
    Sha256,
    StrictIRModel,
    canonical_json_bytes,
    sha256_bytes,
    sha256_text,
)

EvidenceType = Literal[
    "definition",
    "paragraph",
    "list",
    "steps",
    "table",
    "example",
    "formula",
    "caption",
    "other",
]
EvidenceSourceMode = Literal["native", "ocr", "hybrid"]


class EvidenceSourceUnit(StrictIRModel):
    block_id: str = Field(min_length=1, max_length=160)
    block_type: str = Field(min_length=1, max_length=80)
    ordinal: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    text: str
    text_sha256: Sha256

    @model_validator(mode="after")
    def validate_unit(self) -> EvidenceSourceUnit:
        if self.char_end < self.char_start:
            raise ValueError("Evidence source-unit range is reversed")
        if self.char_end - self.char_start != len(self.text):
            raise ValueError("Evidence source-unit range must match source text length")
        if self.text_sha256 != sha256_text(self.text):
            raise ValueError("Evidence source-unit text hash does not match")
        return self


class PageBBox(StrictIRModel):
    page_id: str = Field(min_length=1, max_length=160)
    physical_page_index: int | None = Field(default=None, ge=1)
    display_page_label: str | None = Field(default=None, max_length=64)
    bbox: BBox
    coordinate_space: Literal["pdf_points_top_left", "docx_rendered_pdf_points_top_left"]
    page_width: float = Field(gt=0)
    page_height: float = Field(gt=0)
    source_region_id: str | None = Field(default=None, max_length=160)

    @model_validator(mode="after")
    def validate_bbox(self) -> PageBBox:
        x0, y0, x1, y1 = self.bbox
        if x0 < 0 or y0 < 0 or x1 <= x0 or y1 <= y0:
            raise ValueError("Evidence BBox must be a positive non-empty rectangle")
        if x1 > self.page_width + 0.01 or y1 > self.page_height + 0.01:
            raise ValueError("Evidence BBox lies outside the page")
        return self


class EvidenceOCRProvenance(StrictIRModel):
    engine: str = Field(min_length=1, max_length=160)
    model_name: str = Field(min_length=1, max_length=240)
    profile_sha256: Sha256
    image_sha256: Sha256
    confidence: float = Field(ge=0, le=1)
    warning_codes: tuple[str, ...] = ()


class EvidenceRecord(StrictIRModel):
    schema_version: Literal["courserag.evidence.v1"] = "courserag.evidence.v1"
    evidence_id: str = Field(pattern=r"^ev1_[0-9a-f]{64}$")
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=1, max_length=160)
    section_id: str | None = Field(default=None, max_length=160)
    section_path: tuple[str, ...] = ()
    evidence_type: EvidenceType
    source_mode: EvidenceSourceMode
    text: str = Field(min_length=1)
    content_sha256: Sha256
    normalized_sha256: Sha256
    source_units: tuple[EvidenceSourceUnit, ...] = Field(min_length=1)
    page_bboxes: tuple[PageBBox, ...] = ()
    previous_evidence_id: str | None = Field(default=None, pattern=r"^ev1_[0-9a-f]{64}$")
    next_evidence_id: str | None = Field(default=None, pattern=r"^ev1_[0-9a-f]{64}$")
    confidence: float | None = Field(default=None, ge=0, le=1)
    ocr: EvidenceOCRProvenance | None = None
    warning_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_record(self) -> EvidenceRecord:
        if self.content_sha256 != sha256_text(self.text):
            raise ValueError("Evidence content hash does not match text")
        if self.normalized_sha256 != sha256_text(normalize_evidence_text(self.text)):
            raise ValueError("Evidence normalized hash does not match text")
        expected_id = stable_evidence_id(
            self.document_version_id,
            self.source_units,
            self.content_sha256,
        )
        if self.evidence_id != expected_id:
            raise ValueError("Evidence ID does not match stable source identity")
        if self.source_mode == "native" and self.ocr is not None:
            raise ValueError("Native Evidence cannot carry OCR provenance")
        if self.source_mode == "ocr" and self.ocr is None:
            raise ValueError("OCR Evidence requires OCR provenance")
        return self


class EvidenceArtifact(StrictIRModel):
    schema_version: Literal["courserag.evidence-artifact.v1"] = "courserag.evidence-artifact.v1"
    document_id: str
    document_version_id: str
    parsed_document_sha256: Sha256
    builder_profile: str = Field(min_length=1, max_length=160)
    builder_profile_sha256: Sha256
    records: tuple[EvidenceRecord, ...]
    warning_codes: tuple[str, ...] = ()

    @property
    def content_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


def normalize_evidence_text(text: str) -> str:
    return " ".join(text.split())


def stable_evidence_id(
    document_version_id: str,
    source_units: tuple[EvidenceSourceUnit, ...],
    content_sha256: str,
) -> str:
    identity = {
        "document_version_id": document_version_id,
        "source_units": [
            {
                "block_id": unit.block_id,
                "char_start": unit.char_start,
                "char_end": unit.char_end,
                "text_sha256": unit.text_sha256,
            }
            for unit in source_units
        ],
        "content_sha256": content_sha256,
    }
    return f"ev1_{sha256_bytes(canonical_json_bytes(identity))}"
