"""Structured native PDF parsing based on PyMuPDF rawdict output."""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from typing import TypeAlias

import fitz

from courserag.domain.document import (
    BBox,
    BlockIR,
    ImageIR,
    LineIR,
    PageIR,
    ParsedDocumentIR,
    ParseWarning,
    SourceSpan,
    TableCellRecord,
    TableRecord,
    TextSpanIR,
    sha256_bytes,
    sha256_text,
    stable_ir_id,
)
from courserag.parsers.base import ParseResult, ParserLimits, validate_pdf
from courserag.parsers.page_classifier import (
    PageClassifier,
    PageClassifierProfile,
    extract_page_features,
)


def _bbox(value: object) -> BBox | None:
    if not isinstance(value, (tuple, list)) or len(value) != 4:
        return None
    return (float(value[0]), float(value[1]), float(value[2]), float(value[3]))


RawMapping: TypeAlias = Mapping[str, object]


def _iter_dicts(value: object) -> Iterable[RawMapping]:
    if not isinstance(value, list):
        return ()
    return (item for item in value if isinstance(item, dict))


def _int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, (str, int, float)) else default


def _float(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (str, int, float)) else default


def _span_text(span: RawMapping) -> str:
    text = span.get("text")
    if isinstance(text, str):
        return text
    return "".join(str(char.get("c", "")) for char in _iter_dicts(span.get("chars")))


def _writing_mode(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    if not all(isinstance(item, (str, int, float)) for item in value):
        return None
    return _float(value[0]), _float(value[1])


def _is_bold(font_name: str, flags: int) -> bool:
    lowered = font_name.lower()
    return bool(flags & 16) or any(marker in lowered for marker in ("bold", "black", "heavy"))


def _is_italic(font_name: str, flags: int) -> bool:
    lowered = font_name.lower()
    return bool(flags & 2) or any(marker in lowered for marker in ("italic", "oblique"))


def _reading_order(blocks: list[tuple[int, BBox | None]], page_width: float) -> list[int]:
    positioned = [(index, bbox) for index, bbox in blocks if bbox is not None]
    if len(positioned) < 2:
        return [index for index, _ in blocks]
    middle = page_width / 2
    left = [(index, box) for index, box in positioned if box[2] <= middle * 1.08]
    right = [(index, box) for index, box in positioned if box[0] >= middle * 0.92]
    crossing = [
        (index, box)
        for index, box in positioned
        if box[0] < middle * 0.92 and box[2] > middle * 1.08
    ]
    ordered: list[tuple[int, BBox]]
    if left and right and len(crossing) <= max(2, len(positioned) // 5):
        top_crossing = sorted(
            (
                (index, box)
                for index, box in crossing
                if box[1] < min(item[1][1] for item in left + right)
            ),
            key=lambda item: (item[1][1], item[1][0]),
        )
        bottom_crossing = [item for item in crossing if item not in top_crossing]
        ordered = (
            top_crossing
            + sorted(left, key=lambda item: (item[1][1], item[1][0]))
            + sorted(right, key=lambda item: (item[1][1], item[1][0]))
            + sorted(bottom_crossing, key=lambda item: (item[1][1], item[1][0]))
        )
    else:
        ordered = sorted(positioned, key=lambda item: (item[1][1], item[1][0]))
    ordered_ids = [index for index, _ in ordered]
    ordered_ids.extend(index for index, bbox in blocks if bbox is None and index not in ordered_ids)
    return ordered_ids


class StructuredPDFParser:
    parser_profile = "structured_pdf_v1"
    parser_version = "1.0"

    def __init__(
        self,
        *,
        limits: ParserLimits | None = None,
        min_native_chars: int = 30,
        classifier_profile: PageClassifierProfile | None = None,
        force_ocr: bool = False,
    ) -> None:
        self.limits = limits or ParserLimits()
        self.classifier = PageClassifier(
            classifier_profile or PageClassifierProfile(min_native_chars=min_native_chars)
        )
        self.force_ocr = force_ocr

    def parse(
        self,
        content: bytes,
        *,
        document_id: str,
        document_version_id: str,
        document_sha256: str,
    ) -> ParseResult:
        validate_pdf(content, self.limits)
        actual_sha256 = sha256_bytes(content)
        if actual_sha256 != document_sha256:
            raise ValueError("PDF content does not match document_sha256")
        pages: list[PageIR] = []
        tables: list[TableRecord] = []
        images: list[ImageIR] = []
        warnings: list[ParseWarning] = []
        assets: dict[str, bytes] = {}
        with fitz.open(stream=content, filetype="pdf") as document:
            for page_number, page in enumerate(document, start=1):
                parsed_page, page_images, page_tables, page_assets, page_warnings = (
                    self._parse_page(
                        page,
                        page_number=page_number,
                        document_id=document_id,
                        document_version_id=document_version_id,
                    )
                )
                pages.append(parsed_page)
                images.extend(page_images)
                tables.extend(page_tables)
                assets.update(page_assets)
                warnings.extend(page_warnings)
        return ParseResult(
            document=ParsedDocumentIR(
                document_id=document_id,
                document_version_id=document_version_id,
                document_sha256=document_sha256,
                source_format="pdf",
                parser_profile=self.parser_profile,
                parser_version=self.parser_version,
                pages=tuple(pages),
                sections=(),
                tables=tuple(tables),
                images=tuple(images),
                warnings=tuple(warnings),
            ),
            binary_assets=assets,
        )

    def _parse_page(
        self,
        page: fitz.Page,
        *,
        page_number: int,
        document_id: str,
        document_version_id: str,
    ) -> tuple[PageIR, list[ImageIR], list[TableRecord], dict[str, bytes], list[ParseWarning]]:
        raw: RawMapping = page.get_text("rawdict", sort=False)
        raw_blocks = list(_iter_dicts(raw.get("blocks")))
        block_positions = [
            (index, _bbox(block.get("bbox"))) for index, block in enumerate(raw_blocks)
        ]
        order = _reading_order(block_positions, float(page.rect.width))
        rank = {raw_index: order_index for order_index, raw_index in enumerate(order)}
        blocks: list[BlockIR] = []
        images: list[ImageIR] = []
        assets: dict[str, bytes] = {}
        font_sizes: list[float] = []
        image_area = 0.0
        for raw_index, raw_block in enumerate(raw_blocks):
            block_type = _int(raw_block.get("type"))
            block_bbox = _bbox(raw_block.get("bbox"))
            if block_bbox is not None:
                image_area += (
                    max(0.0, block_bbox[2] - block_bbox[0])
                    * max(0.0, block_bbox[3] - block_bbox[1])
                    if block_type == 1
                    else 0.0
                )
            block_id = stable_ir_id("blk", document_version_id, page_number, raw_index, block_type)
            span = SourceSpan(
                document_id=document_id,
                document_version_id=document_version_id,
                page_start=page_number,
                page_end=page_number,
                block_start_id=block_id,
                block_end_id=block_id,
                bboxes=(block_bbox,) if block_bbox is not None else (),
                source_unit=f"pdf:block:{raw_index}",
            )
            if block_type == 1:
                image_bytes = raw_block.get("image")
                if not isinstance(image_bytes, bytes):
                    image_bytes = b""
                digest = sha256_bytes(image_bytes)
                extension = str(raw_block.get("ext", "bin"))
                image_id = stable_ir_id("img", document_version_id, page_number, raw_index, digest)
                media_type = f"image/{'jpeg' if extension in {'jpg', 'jpeg'} else extension}"
                images.append(
                    ImageIR(
                        image_id=image_id,
                        content_sha256=digest,
                        media_type=media_type,
                        width=_int(raw_block.get("width")) or None,
                        height=_int(raw_block.get("height")) or None,
                        bbox=block_bbox,
                        extension=extension,
                    )
                )
                if image_bytes:
                    assets[f"images/{digest}.{extension}"] = image_bytes
                blocks.append(
                    BlockIR(
                        block_id=block_id,
                        block_type="figure",
                        text="",
                        order_index=rank[raw_index],
                        bbox=block_bbox,
                        style={"raw_block_index": raw_index},
                        source_span=span,
                        image_ids=(image_id,),
                        content_sha256=sha256_text(""),
                    )
                )
                continue

            lines: list[LineIR] = []
            line_texts: list[str] = []
            for line_index, raw_line in enumerate(_iter_dicts(raw_block.get("lines"))):
                parsed_spans: list[TextSpanIR] = []
                span_texts: list[str] = []
                for span_index, raw_span in enumerate(_iter_dicts(raw_line.get("spans"))):
                    text = _span_text(raw_span)
                    span_bbox = _bbox(raw_span.get("bbox"))
                    font_name = str(raw_span.get("font", "")) or None
                    font_size = _float(raw_span.get("size")) or None
                    if font_size is not None:
                        font_sizes.append(font_size)
                    flags = _int(raw_span.get("flags"))
                    parsed_spans.append(
                        TextSpanIR(
                            text=text,
                            bbox=span_bbox,
                            font_name=font_name,
                            font_size=font_size,
                            flags=flags,
                            color=(
                                _int(raw_span["color"])
                                if isinstance(raw_span.get("color"), int)
                                else None
                            ),
                            bold=_is_bold(font_name or "", flags),
                            italic=_is_italic(font_name or "", flags),
                            source_span=SourceSpan(
                                document_id=document_id,
                                document_version_id=document_version_id,
                                page_start=page_number,
                                page_end=page_number,
                                block_start_id=block_id,
                                block_end_id=block_id,
                                bboxes=(span_bbox,) if span_bbox is not None else (),
                                source_unit=(
                                    f"pdf:block:{raw_index}:line:{line_index}:span:{span_index}"
                                ),
                            ),
                        )
                    )
                    span_texts.append(text)
                line_text = "".join(span_texts)
                line_texts.append(line_text)
                lines.append(
                    LineIR(
                        line_id=stable_ir_id(
                            "line", document_version_id, page_number, raw_index, line_index
                        ),
                        order_index=line_index,
                        text=line_text,
                        bbox=_bbox(raw_line.get("bbox")),
                        writing_mode=_writing_mode(raw_line.get("dir")),
                        spans=tuple(parsed_spans),
                    )
                )
            text = "\n".join(line_texts).strip()
            blocks.append(
                BlockIR(
                    block_id=block_id,
                    block_type="paragraph",
                    text=text,
                    order_index=rank[raw_index],
                    bbox=block_bbox,
                    style={"raw_block_index": raw_index},
                    source_span=span,
                    lines=tuple(lines),
                    content_sha256=sha256_text(text),
                )
            )

        blocks.sort(key=lambda block: block.order_index)
        parsed_tables, table_blocks, table_warnings = self._parse_tables(
            page,
            page_number=page_number,
            document_id=document_id,
            document_version_id=document_version_id,
            next_order_index=max((block.order_index for block in blocks), default=-1) + 1,
        )
        blocks.extend(table_blocks)
        blocks.sort(key=lambda block: block.order_index)
        text = "\n".join(block.text for block in blocks)
        text_bboxes = tuple(
            block.bbox
            for block in blocks
            if block.bbox is not None and block.text and block.block_type != "figure"
        )
        features = extract_page_features(
            text,
            page_width=float(page.rect.width),
            page_height=float(page.rect.height),
            image_area=image_area,
            native_text_bboxes=text_bboxes,
        )
        decision = self.classifier.classify(features, force_ocr=self.force_ocr)
        mode = decision.mode
        source_mode = {
            "native": "native_text",
            "ocr": "ocr_pending",
            "hybrid": "hybrid_pending",
        }[mode]
        page_warnings: list[ParseWarning] = list(table_warnings)
        if mode != "native":
            page_warnings.append(
                ParseWarning(
                    code="OCR_REQUIRED",
                    message="Page requires OCR in P05; P04 did not recognize image text.",
                    page_index=page_number,
                    details={"decision": mode},
                )
            )
        if features.printable_ratio < self.classifier.profile.min_printable_ratio and text:
            page_warnings.append(
                ParseWarning(
                    code="LOW_PRINTABLE_TEXT_RATIO",
                    message="Extracted native text contains a high proportion of control characters.",
                    page_index=page_number,
                    details={"printable_ratio": features.printable_ratio},
                )
            )
        median_font_size = statistics.median(font_sizes) if font_sizes else 0.0
        page_ir = PageIR(
            page_id=stable_ir_id("page", document_version_id, page_number),
            physical_page_index=page_number,
            display_page_label=page.get_label() or None,
            width=float(page.rect.width),
            height=float(page.rect.height),
            source_mode=source_mode,
            blocks=tuple(blocks),
            parse_decision=decision.model_copy(
                update={"metrics": {**decision.metrics, "median_font_size": median_font_size}}
            ),
            content_sha256=sha256_text(text),
        )
        return page_ir, images, parsed_tables, assets, page_warnings

    @staticmethod
    def _parse_tables(
        page: fitz.Page,
        *,
        page_number: int,
        document_id: str,
        document_version_id: str,
        next_order_index: int,
    ) -> tuple[list[TableRecord], list[BlockIR], list[ParseWarning]]:
        try:
            detected = page.find_tables()
        except (RuntimeError, ValueError) as exc:
            return (
                [],
                [],
                [
                    ParseWarning(
                        code="PDF_TABLE_DETECTION_FAILED",
                        message="Native PDF table detection failed; text blocks remain available.",
                        page_index=page_number,
                        details={"error_type": type(exc).__name__},
                    )
                ],
            )
        records: list[TableRecord] = []
        blocks: list[BlockIR] = []
        for table_index, table in enumerate(detected.tables):
            matrix = table.extract()
            if not matrix or not any(
                any(str(value or "").strip() for value in row) for row in matrix
            ):
                continue
            block_id = stable_ir_id("blk", document_version_id, page_number, "table", table_index)
            table_id = stable_ir_id("table", document_version_id, page_number, table_index)
            table_bbox = _bbox(table.bbox)
            span = SourceSpan(
                document_id=document_id,
                document_version_id=document_version_id,
                page_start=page_number,
                page_end=page_number,
                block_start_id=block_id,
                block_end_id=block_id,
                bboxes=(table_bbox,) if table_bbox is not None else (),
                source_unit=f"pdf:page:{page_number}:table:{table_index}",
            )
            cells: list[TableCellRecord] = []
            for row_index, row in enumerate(matrix):
                for column_index, value in enumerate(row):
                    cells.append(
                        TableCellRecord(
                            row_index=row_index,
                            column_index=column_index,
                            text=str(value or ""),
                            source_span=span,
                        )
                    )
            text = "\n".join(cell.text for cell in cells)
            records.append(
                TableRecord(
                    table_id=table_id,
                    block_id=block_id,
                    order_index=next_order_index + table_index,
                    row_count=len(matrix),
                    column_count=max(len(row) for row in matrix),
                    cells=tuple(cells),
                    source_span=span,
                    content_sha256=sha256_text(text),
                )
            )
            blocks.append(
                BlockIR(
                    block_id=block_id,
                    block_type="table",
                    text=text,
                    order_index=next_order_index + table_index,
                    bbox=table_bbox,
                    style={"table_id": table_id, "detector": "pymupdf.find_tables"},
                    source_span=span,
                    content_sha256=sha256_text(text),
                )
            )
        return records, blocks, []
