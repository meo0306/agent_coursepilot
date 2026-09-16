import json

import pytest

from courserag.domain.document import (
    BlockIR,
    PageIR,
    ParsedDocumentIR,
    ParsePreview,
    ParseQualityReport,
    SourceSpan,
    canonical_json_bytes,
    sha256_text,
)
from courserag.parsers.artifact_bundle import build_parsed_artifact_bundle, read_bundle_json


def _document() -> ParsedDocumentIR:
    span = SourceSpan(
        document_id="doc-1",
        document_version_id="version-1",
        page_start=1,
        page_end=1,
        block_start_id="block-1",
        block_end_id="block-1",
        char_start=0,
        char_end=4,
    )
    block = BlockIR(
        block_id="block-1",
        block_type="paragraph",
        text="body text",
        order_index=0,
        source_span=span,
        content_sha256=sha256_text("body text"),
    )
    page = PageIR(
        page_id="page-1",
        physical_page_index=1,
        source_mode="native_text",
        blocks=(block,),
        content_sha256=sha256_text("body text"),
    )
    return ParsedDocumentIR(
        document_id="doc-1",
        document_version_id="version-1",
        document_sha256="a" * 64,
        source_format="pdf",
        parser_profile="structured_v1",
        parser_version="1.0",
        pages=(page,),
        sections=(),
    )


def test_ir_hash_and_bundle_are_deterministic() -> None:
    document = _document()
    quality = ParseQualityReport(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        parser_profile=document.parser_profile,
        page_count=1,
        native_page_count=1,
        logical_docx_page_count=0,
        ocr_pending_page_count=0,
        heading_count=0,
        paragraph_count=1,
        table_count=0,
        image_count=0,
        noise_block_count=0,
        low_confidence_alignment_count=0,
        unresolved_block_count=0,
        warning_count=0,
        recommend_human_review=False,
    )
    preview = ParsePreview(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        section_tree=(),
        page_summaries=(),
        warnings=(),
    )
    first = build_parsed_artifact_bundle(document, quality, preview)
    second = build_parsed_artifact_bundle(document, quality, preview)
    assert first == second
    decoded = json.loads(read_bundle_json(first.content, "document_ir.json"))
    assert decoded["document_id"] == "doc-1"
    assert canonical_json_bytes(document) == read_bundle_json(first.content, "document_ir.json")


def test_source_span_and_content_hash_fail_closed() -> None:
    with pytest.raises(ValueError, match="page_end"):
        SourceSpan(
            document_id="doc",
            document_version_id="version",
            page_start=2,
            page_end=1,
        )
    with pytest.raises(ValueError, match="content_sha256"):
        BlockIR(
            block_id="block",
            block_type="paragraph",
            text="content",
            order_index=0,
            source_span=SourceSpan(document_id="doc", document_version_id="version"),
            content_sha256="0" * 64,
        )


def test_bundle_rejects_path_escape() -> None:
    document = _document()
    quality = ParseQualityReport(
        document_id="doc-1",
        document_version_id="version-1",
        parser_profile="structured_v1",
        page_count=1,
        native_page_count=1,
        logical_docx_page_count=0,
        ocr_pending_page_count=0,
        heading_count=0,
        paragraph_count=1,
        table_count=0,
        image_count=0,
        noise_block_count=0,
        low_confidence_alignment_count=0,
        unresolved_block_count=0,
        warning_count=0,
        recommend_human_review=False,
    )
    preview = ParsePreview(
        document_id="doc-1",
        document_version_id="version-1",
        section_tree=(),
        page_summaries=(),
        warnings=(),
    )
    with pytest.raises(ValueError, match="inside"):
        build_parsed_artifact_bundle(
            document,
            quality,
            preview,
            binary_assets={"../escape.bin": b"x"},
        )
