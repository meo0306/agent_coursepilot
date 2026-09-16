from __future__ import annotations

from courserag.domain.document import (
    BlockIR,
    LineIR,
    PageIR,
    ParsedDocumentIR,
    SourceSpan,
    TextSpanIR,
    sha256_text,
)
from courserag.parsers.quality import build_parse_preview, build_quality_report
from courserag.parsers.structure import enrich_document_structure


def _block(
    block_id: str,
    text: str,
    order: int,
    page: int,
    *,
    bbox: tuple[float, float, float, float],
    font_size: float = 10,
    bold: bool = False,
) -> BlockIR:
    source = SourceSpan(
        document_id="doc",
        document_version_id="version",
        page_start=page,
        page_end=page,
        block_start_id=block_id,
        block_end_id=block_id,
    )
    return BlockIR(
        block_id=block_id,
        block_type="paragraph",
        text=text,
        order_index=order,
        bbox=bbox,
        source_span=source,
        lines=(
            LineIR(
                line_id=f"line-{block_id}",
                order_index=0,
                text=text,
                spans=(
                    TextSpanIR(
                        text=text,
                        font_size=font_size,
                        bold=bold,
                        source_span=source,
                    ),
                ),
            ),
        ),
        content_sha256=sha256_text(text),
    )


def _page(index: int, blocks: tuple[BlockIR, ...]) -> PageIR:
    return PageIR(
        page_id=f"page-{index}",
        physical_page_index=index,
        width=400,
        height=600,
        source_mode="native_text",
        blocks=blocks,
        content_sha256=sha256_text("\n".join(block.text for block in blocks)),
    )


def test_structure_labels_noise_builds_sections_and_links_cross_page_continuation() -> None:
    first = _page(
        1,
        (
            _block("header-1", "Course title", 0, 1, bbox=(20, 10, 200, 25)),
            _block(
                "heading", "1. Foundations", 1, 1, bbox=(20, 60, 220, 85), font_size=18, bold=True
            ),
            _block("body-1", "A paragraph continues", 2, 1, bbox=(20, 100, 350, 580)),
            _block("number-1", "1", 3, 1, bbox=(190, 580, 205, 595)),
        ),
    )
    second = _page(
        2,
        (
            _block("header-2", "Course title", 0, 2, bbox=(20, 10, 200, 25)),
            _block("body-2", "on the next page.", 1, 2, bbox=(20, 30, 350, 60)),
            _block("number-2", "2", 2, 2, bbox=(190, 580, 205, 595)),
        ),
    )
    document = ParsedDocumentIR(
        document_id="doc",
        document_version_id="version",
        document_sha256="a" * 64,
        source_format="pdf",
        parser_profile="structured_pdf_v1",
        parser_version="1.0",
        pages=(first, second),
        sections=(),
    )
    enriched = enrich_document_structure(document)
    assert enriched.pages[0].blocks[0].noise_labels == ("repeated_header_footer",)
    assert "page_number" in enriched.pages[0].blocks[-1].noise_labels
    assert enriched.pages[1].blocks[1].continuation_of_block_id == "body-1"
    assert enriched.sections[0].title == "1. Foundations"
    assert enriched.pages[0].blocks[1].block_type == "heading"


def test_quality_and_preview_report_reviewable_counts() -> None:
    document = enrich_document_structure(
        ParsedDocumentIR(
            document_id="doc",
            document_version_id="version",
            document_sha256="a" * 64,
            source_format="pdf",
            parser_profile="structured_pdf_v1",
            parser_version="1.0",
            pages=(
                _page(
                    1,
                    (
                        _block("heading", "1. Start", 0, 1, bbox=(20, 20, 200, 50), font_size=18),
                        _block("body", "Body.", 1, 1, bbox=(20, 80, 350, 120)),
                    ),
                ),
            ),
            sections=(),
        )
    )
    quality = build_quality_report(document)
    preview = build_parse_preview(document)
    assert quality.heading_count == 1
    assert quality.metrics["section_coverage"] == 1
    assert preview.section_tree[0]["title"] == "1. Start"
