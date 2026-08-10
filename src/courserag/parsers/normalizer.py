"""Deterministic native/OCR coordinate merge for P05 parsed-document artifacts."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from courserag.domain.document import (
    BBox,
    BlockIR,
    PageIR,
    ParsedDocumentIR,
    ParseWarning,
    SourceSpan,
    sha256_text,
    stable_ir_id,
)
from courserag.parsers.ocr.types import OCRPageResult, OCRRegionResult


def normalize_ocr_text(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def bbox_iou(left: BBox, right: BBox) -> float:
    x0 = max(left[0], right[0])
    y0 = max(left[1], right[1])
    x1 = min(left[2], right[2])
    y1 = min(left[3], right[3])
    intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if intersection == 0:
        return 0.0
    left_area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    right_area = max(0.0, right[2] - right[0]) * max(0.0, right[3] - right[1])
    union = left_area + right_area - intersection
    return intersection / union if union else 0.0


def merge_ocr_results(
    document: ParsedDocumentIR,
    results: tuple[OCRPageResult, ...],
    *,
    iou_threshold: float = 0.50,
    text_similarity_threshold: float = 0.92,
) -> ParsedDocumentIR:
    by_page = {result.page_id: result for result in results}
    if len(by_page) != len(results):
        raise ValueError("OCR results contain duplicate page IDs")
    unknown = set(by_page) - {page.page_id for page in document.pages}
    if unknown:
        raise ValueError("OCR result references an unknown parsed-document page")

    pages: list[PageIR] = []
    handled_clean_pages: set[int] = set()
    added_warnings: list[ParseWarning] = []
    for page in document.pages:
        result = by_page.get(page.page_id)
        if result is None:
            pages.append(page)
            continue
        merged, duplicate_count = _merge_page(
            document,
            page,
            result,
            iou_threshold=iou_threshold,
            text_similarity_threshold=text_similarity_threshold,
        )
        pages.append(merged)
        if result.status == "ready" and page.physical_page_index is not None:
            handled_clean_pages.add(page.physical_page_index)
        added_warnings.extend(
            ParseWarning(
                code=warning.code,
                message=warning.message,
                page_index=page.physical_page_index,
                details={
                    "engine": result.engine,
                    "profile_sha256": result.profile_sha256,
                    "duplicate_region_count": duplicate_count,
                },
            )
            for warning in result.warnings
        )

    warnings = tuple(
        warning
        for warning in document.warnings
        if not (warning.code == "OCR_REQUIRED" and warning.page_index in handled_clean_pages)
    ) + tuple(added_warnings)
    return document.model_copy(
        update={
            "parser_profile": f"{document.parser_profile}+ocr",
            "parser_version": f"{document.parser_version}+p05",
            "pages": tuple(pages),
            "warnings": warnings,
            "metadata": {
                **document.metadata,
                "ocr_result_count": len(results),
                "ocr_result_hashes": [result.result_sha256 for result in results],
            },
        }
    )


def _merge_page(
    document: ParsedDocumentIR,
    page: PageIR,
    result: OCRPageResult,
    *,
    iou_threshold: float,
    text_similarity_threshold: float,
) -> tuple[PageIR, int]:
    native_blocks = list(page.blocks)
    ocr_blocks: list[BlockIR] = []
    duplicate_native_ids: set[str] = set()
    duplicate_count = 0
    for region in result.regions:
        duplicate = _find_duplicate(
            region,
            native_blocks,
            iou_threshold=iou_threshold,
            text_similarity_threshold=text_similarity_threshold,
        )
        if duplicate is not None:
            duplicate_native_ids.add(duplicate.block_id)
            duplicate_count += 1
            continue
        ocr_blocks.append(_ocr_block(document, page, region, result))

    marked_native = [
        block.model_copy(
            update={
                "style": {
                    **block.style,
                    "content_source": (
                        "native_ocr_deduplicated"
                        if block.block_id in duplicate_native_ids
                        else block.style.get("content_source", "native")
                    ),
                }
            }
        )
        for block in native_blocks
    ]
    ordered = sorted(
        [*marked_native, *ocr_blocks],
        key=lambda block: (
            block.bbox is None,
            block.bbox[1] if block.bbox is not None else float("inf"),
            block.bbox[0] if block.bbox is not None else float("inf"),
            block.order_index,
            block.block_id,
        ),
    )
    ordered = [
        block.model_copy(update={"order_index": index}) for index, block in enumerate(ordered)
    ]
    page_text = "\n".join(block.text for block in ordered)
    source_mode = page.source_mode
    if result.status == "ready":
        source_mode = (
            "ocr" if page.parse_decision and page.parse_decision.mode == "ocr" else "hybrid"
        )
    return (
        page.model_copy(
            update={
                "source_mode": source_mode,
                "blocks": tuple(ordered),
                "content_sha256": sha256_text(page_text),
            }
        ),
        duplicate_count,
    )


def _find_duplicate(
    region: OCRRegionResult,
    native_blocks: list[BlockIR],
    *,
    iou_threshold: float,
    text_similarity_threshold: float,
) -> BlockIR | None:
    normalized_region = normalize_ocr_text(region.text)
    if not normalized_region:
        return None
    for block in native_blocks:
        if block.bbox is None or not block.text.strip():
            continue
        if bbox_iou(region.page_bbox, block.bbox) < iou_threshold:
            continue
        normalized_native = normalize_ocr_text(block.text)
        similarity = SequenceMatcher(None, normalized_region, normalized_native).ratio()
        if normalized_region == normalized_native or similarity >= text_similarity_threshold:
            return block
    return None


def _ocr_block(
    document: ParsedDocumentIR,
    page: PageIR,
    region: OCRRegionResult,
    result: OCRPageResult,
) -> BlockIR:
    page_index = page.physical_page_index
    block_id = stable_ir_id("blkocr", page.page_id, region.region_id, result.result_sha256)
    span = SourceSpan(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        page_start=page_index,
        page_end=page_index,
        block_start_id=block_id,
        block_end_id=block_id,
        bboxes=(region.page_bbox,),
        source_unit=f"ocr:{result.engine}:{region.region_id}",
    )
    return BlockIR(
        block_id=block_id,
        block_type="paragraph",
        text=region.text,
        order_index=len(page.blocks),
        bbox=region.page_bbox,
        style={
            "content_source": "ocr",
            "engine": result.engine,
            "model_name": result.model_name,
            "image_sha256": result.image_sha256,
            "pixel_bbox": list(region.pixel_bbox),
            "profile_sha256": result.profile_sha256,
            "warning_codes": [warning.code for warning in result.warnings],
            "ocr_region_id": region.region_id,
        },
        source_span=span,
        confidence=region.confidence,
        content_sha256=sha256_text(region.text),
    )
