"""Idempotent projection of immutable ParsedDocumentIR facts into P03 tables."""

from __future__ import annotations

from courserag.domain.document import ParsedDocumentIR, stable_ir_id
from courserag.parsers.ocr.types import OCRPageResult
from courserag.persistence.models import (
    ArtifactRecord,
    BlockRecord,
    OCRPageResultRecord,
    PageRecord,
    ParsedDocumentRecord,
    SectionRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class ParsedDocumentConflictError(RuntimeError):
    pass


def materialize_parsed_document(
    repository: CourseRAGRepository,
    *,
    document: ParsedDocumentIR,
    artifact: ArtifactRecord,
) -> ParsedDocumentRecord:
    existing = repository.get_parsed_document_by_version(document.document_version_id)
    if existing is not None:
        if (
            existing.artifact_id == artifact.id
            and existing.parser_profile == document.parser_profile
            and existing.parser_version == document.parser_version
        ):
            return existing
        raise ParsedDocumentConflictError(
            "document version already has a different immutable parsed-document projection"
        )
    parsed = ParsedDocumentRecord(
        id=stable_ir_id("parsed", document.document_version_id),
        document_version_id=document.document_version_id,
        parser_profile=document.parser_profile,
        parser_version=document.parser_version,
        artifact_id=artifact.id,
        status="ready_with_warnings" if document.warnings else "ready",
        warnings_json=[warning.model_dump(mode="json") for warning in document.warnings],
    )
    repository.add(parsed)
    repository.flush()
    pages_by_block: dict[str, str] = {}
    for page_ordinal, page in enumerate(document.pages, start=1):
        repository.add(
            PageRecord(
                id=page.page_id,
                parsed_document_id=parsed.id,
                page_index=page_ordinal,
                display_page_label=page.display_page_label,
                width=page.width,
                height=page.height,
                source_mode=page.source_mode,
                content_sha256=page.content_sha256,
                metadata_json={
                    "physical_page_index": page.physical_page_index,
                    "section_page_index": page.section_page_index,
                    "parse_decision": (
                        page.parse_decision.model_dump(mode="json")
                        if page.parse_decision is not None
                        else None
                    ),
                },
            )
        )
        pages_by_block.update({block.block_id: page.page_id for block in page.blocks})
    repository.flush()
    sections_by_block: dict[str, str] = {}
    for section in sorted(document.sections, key=lambda item: item.order_index):
        repository.add(
            SectionRecord(
                id=section.section_id,
                parsed_document_id=parsed.id,
                parent_section_id=section.parent_section_id,
                stable_path=section.section_id,
                heading=section.title,
                level=section.level,
                ordinal=section.order_index,
                metadata_json={
                    "section_path": list(section.section_path),
                    "source_span": section.source_span.model_dump(mode="json"),
                    "content_sha256": section.content_sha256,
                },
            )
        )
        for block_id in section.block_ids:
            sections_by_block[block_id] = section.section_id
    repository.flush()
    for page in document.pages:
        for block in page.blocks:
            repository.add(
                BlockRecord(
                    id=block.block_id,
                    parsed_document_id=parsed.id,
                    section_id=sections_by_block.get(block.block_id),
                    page_id=pages_by_block.get(block.block_id),
                    stable_path=block.block_id,
                    block_type=block.block_type,
                    ordinal=block.order_index,
                    text=block.text,
                    content_sha256=block.content_sha256,
                    metadata_json={
                        "bbox": list(block.bbox) if block.bbox is not None else None,
                        "style": block.style,
                        "noise_labels": list(block.noise_labels),
                        "continuation_of_block_id": block.continuation_of_block_id,
                        "confidence": block.confidence,
                        "source_span": block.source_span.model_dump(mode="json"),
                        "page_anchor": (
                            block.page_anchor.model_dump(mode="json")
                            if block.page_anchor is not None
                            else None
                        ),
                    },
                )
            )
    repository.flush()
    return parsed


def materialize_ocr_page_results(
    repository: CourseRAGRepository,
    *,
    results: tuple[OCRPageResult, ...],
    artifact: ArtifactRecord,
) -> tuple[OCRPageResultRecord, ...]:
    records: list[OCRPageResultRecord] = []
    for result in results:
        existing = repository.get_ocr_page_result(result.page_id)
        if existing is not None:
            if existing.result_sha256 == result.result_sha256:
                records.append(existing)
                continue
            raise ParsedDocumentConflictError(
                "page already has a different immutable OCR result projection"
            )
        record = OCRPageResultRecord(
            page_id=result.page_id,
            artifact_id=artifact.id,
            engine=result.engine,
            engine_version=result.engine_version,
            image_sha256=result.image_sha256,
            confidence=result.confidence,
            warnings_json=[warning.model_dump(mode="json") for warning in result.warnings],
            status=result.status,
            model_name=result.model_name,
            model_manifest_sha256=result.model_manifest_sha256,
            profile_sha256=result.profile_sha256,
            dpi=result.dpi,
            image_width=result.image_width,
            image_height=result.image_height,
            text_content=result.text,
            regions_json=[region.model_dump(mode="json") for region in result.regions],
            result_sha256=result.result_sha256,
            duration_ms=result.duration_ms,
            peak_memory_bytes=result.peak_memory_bytes,
        )
        repository.add(record)
        records.append(record)
    repository.flush()
    return tuple(records)
