"""Canonical, versioned document representation used by the P04 parser pipeline."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
BBox = tuple[float, float, float, float]


class StrictIRModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json_bytes(value: object) -> bytes:
    """Serialize an IR value without locale, whitespace, or key-order variability."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def stable_ir_id(prefix: str, *parts: object) -> str:
    digest = sha256_bytes(canonical_json_bytes([str(part) for part in parts]))[:24]
    return f"{prefix}_{digest}"


class SourceSpan(StrictIRModel):
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=1, max_length=160)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    block_start_id: str | None = Field(default=None, max_length=160)
    block_end_id: str | None = Field(default=None, max_length=160)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    bboxes: tuple[BBox, ...] = ()
    source_unit: str | None = Field(default=None, max_length=240)

    @model_validator(mode="after")
    def validate_ranges(self) -> SourceSpan:
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be supplied together")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must be greater than or equal to page_start")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end < self.char_start:
                raise ValueError("char_end must be greater than or equal to char_start")
        return self


class ParseWarning(StrictIRModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$", max_length=120)
    severity: Literal["info", "warning", "error"] = "warning"
    message: str = Field(min_length=1, max_length=1000)
    page_index: int | None = Field(default=None, ge=1)
    block_id: str | None = Field(default=None, max_length=160)
    details: dict[str, JsonValue] = Field(default_factory=dict)


class TextSpanIR(StrictIRModel):
    text: str
    bbox: BBox | None = None
    font_name: str | None = Field(default=None, max_length=240)
    font_size: float | None = Field(default=None, ge=0)
    flags: int = 0
    color: int | None = None
    bold: bool = False
    italic: bool = False
    source_span: SourceSpan


class LineIR(StrictIRModel):
    line_id: str = Field(min_length=1, max_length=160)
    order_index: int = Field(ge=0)
    text: str
    bbox: BBox | None = None
    writing_mode: tuple[float, float] | None = None
    spans: tuple[TextSpanIR, ...] = ()


class ImageIR(StrictIRModel):
    image_id: str = Field(min_length=1, max_length=160)
    content_sha256: Sha256
    media_type: str = Field(min_length=1, max_length=160)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    bbox: BBox | None = None
    extension: str | None = Field(default=None, max_length=16)


class DocxPageAnchor(StrictIRModel):
    physical_page_index: int | None = Field(default=None, ge=1)
    physical_page_end_index: int | None = Field(default=None, ge=1)
    display_page_label: str | None = Field(default=None, min_length=1, max_length=64)
    section_page_index: int | None = Field(default=None, ge=1)
    renderer_provider: str = Field(min_length=1, max_length=160)
    renderer_version: str = Field(min_length=1, max_length=160)
    render_profile_sha256: Sha256
    canonical_pdf_sha256: Sha256
    alignment_confidence: float = Field(ge=0, le=1)
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_page_range(self) -> DocxPageAnchor:
        if self.physical_page_end_index is not None:
            if self.physical_page_index is None:
                raise ValueError("physical_page_end_index requires physical_page_index")
            if self.physical_page_end_index < self.physical_page_index:
                raise ValueError("physical page range is reversed")
        if (self.page_width is None) != (self.page_height is None):
            raise ValueError("DOCX page dimensions must be provided together")
        if self.page_width is not None and self.physical_page_index is None:
            raise ValueError("DOCX page dimensions require a physical page")
        return self


class BlockIR(StrictIRModel):
    block_id: str = Field(min_length=1, max_length=160)
    block_type: Literal[
        "title",
        "heading",
        "paragraph",
        "list_item",
        "table",
        "figure",
        "formula",
        "page_break",
        "section_break",
        "header",
        "footer",
        "page_number",
        "other",
    ]
    text: str
    order_index: int = Field(ge=0)
    bbox: BBox | None = None
    style: dict[str, JsonValue] = Field(default_factory=dict)
    source_span: SourceSpan
    confidence: float | None = Field(default=None, ge=0, le=1)
    lines: tuple[LineIR, ...] = ()
    image_ids: tuple[str, ...] = ()
    noise_labels: tuple[str, ...] = ()
    continuation_of_block_id: str | None = Field(default=None, max_length=160)
    page_anchor: DocxPageAnchor | None = None
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_content_hash(self) -> BlockIR:
        if self.content_sha256 != sha256_text(self.text):
            raise ValueError("block content_sha256 does not match text")
        return self


class TableCellRecord(StrictIRModel):
    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    row_span: int = Field(default=1, ge=1)
    column_span: int = Field(default=1, ge=1)
    text: str
    bbox: BBox | None = None
    source_span: SourceSpan


class TableRecord(StrictIRModel):
    table_id: str = Field(min_length=1, max_length=160)
    block_id: str = Field(min_length=1, max_length=160)
    order_index: int = Field(ge=0)
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    cells: tuple[TableCellRecord, ...]
    caption: str | None = Field(default=None, max_length=2000)
    source_span: SourceSpan
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_cells(self) -> TableRecord:
        if not self.cells:
            raise ValueError("table requires at least one cell")
        if any(cell.row_index >= self.row_count for cell in self.cells):
            raise ValueError("table cell row is outside row_count")
        if any(cell.column_index >= self.column_count for cell in self.cells):
            raise ValueError("table cell column is outside column_count")
        matrix_text = "\n".join(
            cell.text
            for cell in sorted(self.cells, key=lambda item: (item.row_index, item.column_index))
        )
        if self.content_sha256 != sha256_text(matrix_text):
            raise ValueError("table content_sha256 does not match ordered cell text")
        return self


class PageParseDecision(StrictIRModel):
    mode: Literal["native", "ocr", "hybrid"]
    rule: str | None = Field(default=None, min_length=1, max_length=160)
    reasons: tuple[str, ...] = ()
    profile_name: str | None = Field(default=None, min_length=1, max_length=160)
    profile_sha256: Sha256 | None = None
    metrics: dict[str, float] = Field(default_factory=dict)


class PageIR(StrictIRModel):
    page_id: str = Field(min_length=1, max_length=160)
    physical_page_index: int | None = Field(default=None, ge=1)
    display_page_label: str | None = Field(default=None, min_length=1, max_length=64)
    section_page_index: int | None = Field(default=None, ge=1)
    width: float | None = Field(default=None, gt=0)
    height: float | None = Field(default=None, gt=0)
    source_mode: Literal[
        "native_text",
        "logical_docx",
        "ocr_pending",
        "hybrid_pending",
        "ocr",
        "hybrid",
    ]
    blocks: tuple[BlockIR, ...] = ()
    parse_decision: PageParseDecision | None = None
    content_sha256: Sha256

    @model_validator(mode="after")
    def validate_page(self) -> PageIR:
        if self.source_mode == "logical_docx" and self.physical_page_index is not None:
            raise ValueError("logical DOCX pages cannot claim a physical page index")
        if self.source_mode != "logical_docx" and self.physical_page_index is None:
            raise ValueError("physical PDF and aligned DOCX pages require a page index")
        if len({block.block_id for block in self.blocks}) != len(self.blocks):
            raise ValueError("page block IDs must be unique")
        page_text = "\n".join(block.text for block in self.blocks)
        if self.content_sha256 != sha256_text(page_text):
            raise ValueError("page content_sha256 does not match ordered block text")
        return self


class SectionIR(StrictIRModel):
    section_id: str = Field(min_length=1, max_length=160)
    parent_section_id: str | None = Field(default=None, max_length=160)
    level: int = Field(ge=1, le=12)
    title: str
    section_path: tuple[str, ...]
    order_index: int = Field(ge=0)
    block_ids: tuple[str, ...]
    source_span: SourceSpan
    content_sha256: Sha256


class RendererManifest(StrictIRModel):
    provider: str = Field(min_length=1, max_length=160)
    renderer_version: str = Field(min_length=1, max_length=160)
    profile_sha256: Sha256
    font_manifest_sha256: Sha256
    raw_pdf_sha256: Sha256
    canonical_pdf_sha256: Sha256
    page_manifest_sha256: Sha256
    page_count: int = Field(ge=1)
    command_arguments: tuple[str, ...]
    environment: dict[str, str]
    font_substitutions: dict[str, str] = Field(default_factory=dict)


class ParsedDocumentIR(StrictIRModel):
    schema_version: Literal["courserag.document-ir.v1"] = "courserag.document-ir.v1"
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=1, max_length=160)
    document_sha256: Sha256
    source_format: Literal["pdf", "docx"]
    parser_profile: str = Field(min_length=1, max_length=160)
    parser_version: str = Field(min_length=1, max_length=160)
    pages: tuple[PageIR, ...]
    sections: tuple[SectionIR, ...]
    tables: tuple[TableRecord, ...] = ()
    images: tuple[ImageIR, ...] = ()
    warnings: tuple[ParseWarning, ...] = ()
    renderer_manifest: RendererManifest | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_references(self) -> ParsedDocumentIR:
        page_ids = [page.page_id for page in self.pages]
        if len(set(page_ids)) != len(page_ids):
            raise ValueError("page IDs must be unique")
        blocks = [block for page in self.pages for block in page.blocks]
        block_ids = {block.block_id for block in blocks}
        if len(block_ids) != len(blocks):
            raise ValueError("document block IDs must be unique")
        image_ids = {image.image_id for image in self.images}
        if any(image_id not in image_ids for block in blocks for image_id in block.image_ids):
            raise ValueError("block references an unknown image")
        section_ids = {section.section_id for section in self.sections}
        if any(
            section.parent_section_id is not None and section.parent_section_id not in section_ids
            for section in self.sections
        ):
            raise ValueError("section references an unknown parent")
        if any(
            block_id not in block_ids for section in self.sections for block_id in section.block_ids
        ):
            raise ValueError("section references an unknown block")
        if any(table.block_id not in block_ids for table in self.tables):
            raise ValueError("table references an unknown block")
        if self.source_format == "docx" and self.renderer_manifest is not None:
            if any(
                block.page_anchor is not None
                and block.page_anchor.canonical_pdf_sha256
                != self.renderer_manifest.canonical_pdf_sha256
                for block in blocks
            ):
                raise ValueError("DOCX anchor and renderer snapshot hashes differ")
        return self

    @property
    def content_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class ParseQualityReport(StrictIRModel):
    schema_version: Literal["courserag.parse-quality.v1"] = "courserag.parse-quality.v1"
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=1, max_length=160)
    parser_profile: str = Field(min_length=1, max_length=160)
    page_count: int = Field(ge=0)
    native_page_count: int = Field(ge=0)
    logical_docx_page_count: int = Field(ge=0)
    ocr_pending_page_count: int = Field(ge=0)
    heading_count: int = Field(ge=0)
    paragraph_count: int = Field(ge=0)
    table_count: int = Field(ge=0)
    image_count: int = Field(ge=0)
    noise_block_count: int = Field(ge=0)
    low_confidence_alignment_count: int = Field(ge=0)
    unresolved_block_count: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    recommend_human_review: bool
    warning_codes: tuple[str, ...] = ()
    metrics: dict[str, float] = Field(default_factory=dict)


class ParsePreview(StrictIRModel):
    schema_version: Literal["courserag.parse-preview.v1"] = "courserag.parse-preview.v1"
    document_id: str
    document_version_id: str
    section_tree: tuple[dict[str, JsonValue], ...]
    page_summaries: tuple[dict[str, JsonValue], ...]
    warnings: tuple[ParseWarning, ...]
