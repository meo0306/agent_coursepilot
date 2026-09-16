"""Parse quality report and source-grounded preview builders."""

from __future__ import annotations

from courserag.domain.document import ParsedDocumentIR, ParsePreview, ParseQualityReport


def build_quality_report(
    document: ParsedDocumentIR,
    *,
    low_alignment_threshold: float = 0.75,
) -> ParseQualityReport:
    blocks = [block for page in document.pages for block in page.blocks]
    citation_blocks = [
        block
        for block in blocks
        if block.text.strip() and block.block_type not in {"header", "footer", "page_number"}
    ]
    anchors = [block.page_anchor for block in citation_blocks if block.page_anchor is not None]
    low_alignment = sum(
        anchor.alignment_confidence < low_alignment_threshold or anchor.physical_page_index is None
        for anchor in anchors
    )
    unresolved = sum(
        document.source_format == "docx"
        and (block.page_anchor is None or block.page_anchor.physical_page_index is None)
        for block in citation_blocks
    )
    ocr_pending = sum(
        page.source_mode in {"ocr_pending", "hybrid_pending"} for page in document.pages
    )
    warning_codes = tuple(sorted({warning.code for warning in document.warnings}))
    assigned = sum(
        block.page_anchor is not None and block.page_anchor.physical_page_index is not None
        for block in citation_blocks
    )
    return ParseQualityReport(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        parser_profile=document.parser_profile,
        page_count=(
            document.renderer_manifest.page_count
            if document.renderer_manifest
            else len(document.pages)
        ),
        native_page_count=sum(page.source_mode == "native_text" for page in document.pages),
        logical_docx_page_count=sum(page.source_mode == "logical_docx" for page in document.pages),
        ocr_pending_page_count=ocr_pending,
        heading_count=sum(block.block_type == "heading" for block in blocks),
        paragraph_count=sum(block.block_type == "paragraph" for block in blocks),
        table_count=len(document.tables),
        image_count=len(document.images),
        noise_block_count=sum(bool(block.noise_labels) for block in blocks),
        low_confidence_alignment_count=low_alignment,
        unresolved_block_count=unresolved,
        warning_count=len(document.warnings),
        recommend_human_review=bool(
            ocr_pending or low_alignment or unresolved or document.warnings
        ),
        warning_codes=warning_codes,
        metrics={
            "docx_page_assignment_coverage": (
                assigned / len(citation_blocks) if citation_blocks else 1.0
            ),
            "section_coverage": (
                len({block_id for section in document.sections for block_id in section.block_ids})
                / len(blocks)
                if blocks
                else 1.0
            ),
        },
    )


def build_parse_preview(document: ParsedDocumentIR) -> ParsePreview:
    return ParsePreview(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        section_tree=tuple(
            {
                "section_id": section.section_id,
                "parent_section_id": section.parent_section_id,
                "level": section.level,
                "title": section.title,
                "section_path": list(section.section_path),
                "block_count": len(section.block_ids),
            }
            for section in document.sections
        ),
        page_summaries=tuple(
            {
                "page_id": page.page_id,
                "physical_page_index": page.physical_page_index,
                "display_page_label": page.display_page_label,
                "source_mode": page.source_mode,
                "block_count": len(page.blocks),
                "warning_codes": [
                    warning.code
                    for warning in document.warnings
                    if warning.page_index == page.physical_page_index
                ],
            }
            for page in document.pages
        ),
        warnings=document.warnings,
    )
