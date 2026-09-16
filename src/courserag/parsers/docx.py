"""Structured DOCX parser preserving OOXML document order and source anchors."""

from __future__ import annotations

import io
import re
from collections.abc import Iterable

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph

from courserag.domain.document import (
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
from courserag.parsers.base import ParseResult, ParserLimits, validate_docx

_HEADING_STYLE = re.compile(
    r"^(?:Heading|\u6807\u9898)\s*([1-9][0-9]?)$",
    re.IGNORECASE,
)


def _iter_body_items(document: DocumentObject) -> Iterable[Paragraph | Table]:
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    match = _HEADING_STYLE.match(style_name)
    if match:
        return int(match.group(1))
    paragraph_properties = paragraph._p.pPr
    if paragraph_properties is not None:
        outline = paragraph_properties.find(qn("w:outlineLvl"))
        if outline is not None:
            value = outline.get(qn("w:val"))
            if value is not None and value.isdigit():
                return int(value) + 1
    return None


def _numbering(paragraph: Paragraph) -> tuple[str | None, int | None]:
    num_ids = paragraph._p.xpath("./w:pPr/w:numPr/w:numId")
    levels = paragraph._p.xpath("./w:pPr/w:numPr/w:ilvl")
    if not num_ids and paragraph.style is not None:
        num_ids = paragraph.style.element.xpath("./w:pPr/w:numPr/w:numId")
        levels = paragraph.style.element.xpath("./w:pPr/w:numPr/w:ilvl")
    if not num_ids:
        return None, None
    num_id = num_ids[0].get(qn("w:val"))
    level = levels[0].get(qn("w:val")) if levels else None
    return (
        str(num_id) if num_id is not None else None,
        int(level) if level is not None else None,
    )


def _paragraph_breaks(paragraph: Paragraph) -> tuple[str, ...]:
    values: list[str] = []
    for element in paragraph._p.iter(qn("w:br")):
        values.append(element.get(qn("w:type"), "line"))
    if paragraph.paragraph_format.page_break_before:
        values.append("page_before")
    return tuple(values)


def _requested_fonts(paragraph: Paragraph) -> set[str]:
    fonts: set[str] = set()
    for run in paragraph.runs:
        if run.font.name:
            fonts.add(run.font.name)
        run_properties = run._r.rPr
        if run_properties is None or run_properties.rFonts is None:
            continue
        for attribute in ("ascii", "hAnsi", "eastAsia", "cs"):
            value = run_properties.rFonts.get(qn(f"w:{attribute}"))
            if value:
                fonts.add(value)
    return fonts


def _block_span(
    document_id: str,
    document_version_id: str,
    block_id: str,
    source_unit: str,
) -> SourceSpan:
    return SourceSpan(
        document_id=document_id,
        document_version_id=document_version_id,
        block_start_id=block_id,
        block_end_id=block_id,
        source_unit=source_unit,
    )


class StructuredDOCXParser:
    parser_profile = "structured_docx_v1"
    parser_version = "1.0"

    def __init__(self, *, limits: ParserLimits | None = None) -> None:
        self.limits = limits or ParserLimits()

    def parse(
        self,
        content: bytes,
        *,
        document_id: str,
        document_version_id: str,
        document_sha256: str,
    ) -> ParseResult:
        validate_docx(content, self.limits)
        if sha256_bytes(content) != document_sha256:
            raise ValueError("DOCX content does not match document_sha256")
        try:
            document = Document(io.BytesIO(content))
        except Exception as exc:
            raise ValueError("DOCX cannot be parsed") from exc

        blocks: list[BlockIR] = []
        tables: list[TableRecord] = []
        images: dict[str, ImageIR] = {}
        assets: dict[str, bytes] = {}
        warnings: list[ParseWarning] = []
        requested_fonts: set[str] = set()
        paragraph_index = 0
        table_index = 0
        order_index = 0
        for item in _iter_body_items(document):
            if isinstance(item, Paragraph):
                block, paragraph_images, paragraph_assets = self._paragraph(
                    item,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    paragraph_index=paragraph_index,
                    order_index=order_index,
                    document=document,
                )
                blocks.append(block)
                images.update({image.image_id: image for image in paragraph_images})
                assets.update(paragraph_assets)
                requested_fonts.update(_requested_fonts(item))
                paragraph_index += 1
            else:
                block, table = self._table(
                    item,
                    document_id=document_id,
                    document_version_id=document_version_id,
                    table_index=table_index,
                    order_index=order_index,
                )
                blocks.append(block)
                tables.append(table)
                table_index += 1
            order_index += 1

        for section_index, section in enumerate(document.sections):
            for kind, container in (("header", section.header), ("footer", section.footer)):
                for container_index, paragraph in enumerate(container.paragraphs):
                    text = paragraph.text.strip()
                    if not text:
                        continue
                    block_id = stable_ir_id(
                        "blk", document_version_id, kind, section_index, container_index
                    )
                    span = _block_span(
                        document_id,
                        document_version_id,
                        block_id,
                        f"docx:{kind}:{section_index}:{container_index}",
                    )
                    blocks.append(
                        BlockIR(
                            block_id=block_id,
                            block_type=kind,
                            text=text,
                            order_index=order_index,
                            source_span=span,
                            style={"section_index": section_index},
                            noise_labels=(kind,),
                            content_sha256=sha256_text(text),
                        )
                    )
                    order_index += 1

        logical_text = "\n".join(block.text for block in blocks)
        page = PageIR(
            page_id=stable_ir_id("logical", document_version_id),
            physical_page_index=None,
            source_mode="logical_docx",
            blocks=tuple(blocks),
            content_sha256=sha256_text(logical_text),
        )
        return ParseResult(
            document=ParsedDocumentIR(
                document_id=document_id,
                document_version_id=document_version_id,
                document_sha256=document_sha256,
                source_format="docx",
                parser_profile=self.parser_profile,
                parser_version=self.parser_version,
                pages=(page,),
                sections=(),
                tables=tuple(tables),
                images=tuple(images.values()),
                warnings=tuple(warnings),
                metadata={
                    "requested_fonts": sorted(requested_fonts),
                    "source_paragraph_count": paragraph_index,
                    "source_table_count": table_index,
                    "source_section_count": len(document.sections),
                },
            ),
            binary_assets=assets,
        )

    def _paragraph(
        self,
        paragraph: Paragraph,
        *,
        document_id: str,
        document_version_id: str,
        paragraph_index: int,
        order_index: int,
        document: DocumentObject,
    ) -> tuple[BlockIR, list[ImageIR], dict[str, bytes]]:
        block_id = stable_ir_id("blk", document_version_id, "paragraph", paragraph_index)
        span = _block_span(
            document_id,
            document_version_id,
            block_id,
            f"docx:paragraph:{paragraph_index}",
        )
        level = _heading_level(paragraph)
        num_id, list_level = _numbering(paragraph)
        block_type = "heading" if level is not None else "list_item" if num_id else "paragraph"
        parsed_spans: list[TextSpanIR] = []
        paragraph_images: list[ImageIR] = []
        assets: dict[str, bytes] = {}
        for run_index, run in enumerate(paragraph.runs):
            run_span = SourceSpan(
                document_id=document_id,
                document_version_id=document_version_id,
                block_start_id=block_id,
                block_end_id=block_id,
                source_unit=f"docx:paragraph:{paragraph_index}:run:{run_index}",
            )
            parsed_spans.append(
                TextSpanIR(
                    text=run.text,
                    font_name=run.font.name,
                    font_size=run.font.size.pt if run.font.size is not None else None,
                    bold=bool(run.bold),
                    italic=bool(run.italic),
                    source_span=run_span,
                )
            )
        for image_index, blip in enumerate(paragraph._p.xpath(".//a:blip")):
            relationship_id = blip.get(qn("r:embed"))
            if not relationship_id or relationship_id not in document.part.related_parts:
                continue
            part = document.part.related_parts[relationship_id]
            blob = getattr(part, "blob", None)
            content_type = getattr(part, "content_type", None)
            if not isinstance(blob, bytes) or not isinstance(content_type, str):
                continue
            digest = sha256_bytes(blob)
            extension = content_type.rsplit("/", maxsplit=1)[-1].replace("jpeg", "jpg")
            image = ImageIR(
                image_id=stable_ir_id(
                    "img", document_version_id, paragraph_index, image_index, digest
                ),
                content_sha256=digest,
                media_type=content_type,
                extension=extension,
            )
            paragraph_images.append(image)
            assets[f"images/{digest}.{extension}"] = blob
        text = paragraph.text
        lines = (
            LineIR(
                line_id=stable_ir_id("line", document_version_id, paragraph_index),
                order_index=0,
                text=text,
                spans=tuple(parsed_spans),
            ),
        )
        style_name = paragraph.style.name if paragraph.style is not None else None
        section_break = paragraph._p.pPr is not None and paragraph._p.pPr.sectPr is not None
        return (
            BlockIR(
                block_id=block_id,
                block_type="section_break" if section_break and not text else block_type,
                text=text,
                order_index=order_index,
                style={
                    "paragraph_index": paragraph_index,
                    "style_name": style_name,
                    "heading_level": level,
                    "numbering_id": num_id,
                    "numbering_level": list_level,
                    "breaks": list(_paragraph_breaks(paragraph)),
                    "has_section_break": section_break,
                },
                source_span=span,
                lines=lines,
                image_ids=tuple(image.image_id for image in paragraph_images),
                content_sha256=sha256_text(text),
            ),
            paragraph_images,
            assets,
        )

    def _table(
        self,
        table: Table,
        *,
        document_id: str,
        document_version_id: str,
        table_index: int,
        order_index: int,
    ) -> tuple[BlockIR, TableRecord]:
        block_id = stable_ir_id("blk", document_version_id, "table", table_index)
        table_id = stable_ir_id("table", document_version_id, table_index)
        span = _block_span(
            document_id,
            document_version_id,
            block_id,
            f"docx:table:{table_index}",
        )
        row_count = max(1, len(table.rows))
        column_count = max(1, max((len(row.cells) for row in table.rows), default=1))
        cells: list[TableCellRecord] = []
        seen_cells: set[object] = set()
        for row_index, row in enumerate(table.rows):
            for column_index, cell in enumerate(row.cells):
                cell_element = cell._tc
                if cell_element in seen_cells:
                    continue
                seen_cells.add(cell_element)
                cells.append(
                    TableCellRecord(
                        row_index=row_index,
                        column_index=column_index,
                        row_span=self._row_span(cell),
                        column_span=self._column_span(cell),
                        text=cell.text,
                        source_span=SourceSpan(
                            document_id=document_id,
                            document_version_id=document_version_id,
                            block_start_id=block_id,
                            block_end_id=block_id,
                            source_unit=f"docx:table:{table_index}:cell:{row_index}:{column_index}",
                        ),
                    )
                )
        cells.sort(key=lambda item: (item.row_index, item.column_index))
        matrix_text = "\n".join(cell.text for cell in cells)
        table_record = TableRecord(
            table_id=table_id,
            block_id=block_id,
            order_index=order_index,
            row_count=row_count,
            column_count=column_count,
            cells=tuple(cells),
            source_span=span,
            content_sha256=sha256_text(matrix_text),
        )
        block = BlockIR(
            block_id=block_id,
            block_type="table",
            text=matrix_text,
            order_index=order_index,
            style={
                "table_index": table_index,
                "row_count": row_count,
                "column_count": column_count,
            },
            source_span=span,
            content_sha256=sha256_text(matrix_text),
        )
        return block, table_record

    @staticmethod
    def _column_span(cell: _Cell) -> int:
        properties = cell._tc.tcPr
        grid_span = properties.gridSpan if properties is not None else None
        return int(grid_span.val) if grid_span is not None else 1

    @staticmethod
    def _row_span(cell: _Cell) -> int:
        # python-docx repeats vertically merged cell proxies. De-duplication keeps the
        # anchor cell; exact multi-row extent remains recoverable from the source XML.
        return 1
