from courserag.domain.document import (
    BlockIR,
    PageIR,
    PageParseDecision,
    ParsedDocumentIR,
    SourceSpan,
    sha256_text,
)
from courserag.parsers.normalizer import bbox_iou, merge_ocr_results, normalize_ocr_text
from courserag.parsers.ocr import OCRPageResult, OCRRegionResult, OCRWarning


def _document() -> ParsedDocumentIR:
    native_text = "原生文字"
    native = BlockIR(
        block_id="native-1",
        block_type="paragraph",
        text=native_text,
        order_index=0,
        bbox=(10, 10, 50, 30),
        source_span=SourceSpan(
            document_id="doc",
            document_version_id="version",
            page_start=1,
            page_end=1,
            block_start_id="native-1",
            block_end_id="native-1",
        ),
        content_sha256=sha256_text(native_text),
    )
    return ParsedDocumentIR(
        document_id="doc",
        document_version_id="version",
        document_sha256="a" * 64,
        source_format="pdf",
        parser_profile="structured_pdf_v1",
        parser_version="1.0",
        pages=(
            PageIR(
                page_id="page-1",
                physical_page_index=1,
                width=100,
                height=100,
                source_mode="hybrid_pending",
                blocks=(native,),
                parse_decision=PageParseDecision(mode="hybrid"),
                content_sha256=sha256_text(native_text),
            ),
        ),
        sections=(),
    )


def _region(identifier: str, text: str, bbox: tuple[int, int, int, int]) -> OCRRegionResult:
    x0, y0, x1, y1 = bbox
    return OCRRegionResult(
        region_id=identifier,
        text=text,
        pixel_bbox=bbox,
        pixel_polygon=((x0, y0), (x1, y0), (x1, y1), (x0, y1)),
        page_bbox=(float(x0), float(y0), float(x1), float(y1)),
        confidence=0.9,
        raw_confidence=0.9,
    )


def _result(*regions: OCRRegionResult) -> OCRPageResult:
    return OCRPageResult(
        page_id="page-1",
        status="ready",
        engine="rapidocr",
        engine_version="1",
        model_name="rapidocr-bundled",
        model_manifest_sha256="b" * 64,
        profile_sha256="c" * 64,
        dpi=200,
        image_sha256="d" * 64,
        image_width=100,
        image_height=100,
        text="\n".join(region.text for region in regions),
        regions=regions,
        confidence=0.9,
        duration_ms=10,
        peak_memory_bytes=20,
    )


def test_mixed_merge_prefers_native_duplicate_and_keeps_ocr_only_text() -> None:
    document = _document()
    result = _result(
        _region("duplicate", "原生文字", (10, 10, 50, 30)),
        _region("new", "OCR 新增", (10, 40, 60, 60)),
    )

    merged = merge_ocr_results(document, (result,))
    page = merged.pages[0]

    assert page.source_mode == "hybrid"
    assert [block.text for block in page.blocks] == ["原生文字", "OCR 新增"]
    assert page.blocks[0].style["content_source"] == "native_ocr_deduplicated"
    assert page.blocks[1].style["content_source"] == "ocr"
    assert page.blocks[1].confidence == 0.9
    assert merged.metadata["ocr_result_hashes"] == [result.result_sha256]


def test_warning_result_does_not_silently_complete_pending_page() -> None:
    document = _document()
    result = _result(_region("low", "低置信度", (10, 40, 60, 60))).model_copy(
        update={
            "status": "ready_with_warnings",
            "warnings": (OCRWarning(code="OCR_LOW_CONFIDENCE", message="manual review required"),),
        }
    )

    merged = merge_ocr_results(document, (result,))

    assert merged.pages[0].source_mode == "hybrid_pending"
    assert [warning.code for warning in merged.warnings] == ["OCR_LOW_CONFIDENCE"]


def test_text_normalization_and_iou_are_deterministic() -> None:
    assert normalize_ocr_text("Ａ  \n B") == "A B"
    assert bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0
    assert bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)) == 0.0
