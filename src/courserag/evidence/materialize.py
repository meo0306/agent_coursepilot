"""Idempotent projection of immutable Evidence artifacts into P06 facts."""

from __future__ import annotations

from courserag.domain.document import stable_ir_id
from courserag.domain.evidence import EvidenceArtifact
from courserag.persistence.models import (
    EvidenceBlockLinkRecord,
    EvidencePageBBoxRecord,
    EvidenceRelationRecord,
)
from courserag.persistence.models import EvidenceRecord as EvidenceORMRecord
from courserag.persistence.repositories import CourseRAGRepository


class EvidenceMaterializationConflict(RuntimeError):
    pass


def materialize_evidence_artifact(
    repository: CourseRAGRepository,
    *,
    parsed_document_id: str,
    artifact: EvidenceArtifact,
) -> tuple[EvidenceORMRecord, ...]:
    internal_ids = {
        record.evidence_id: stable_ir_id("evidence", record.evidence_id)
        for record in artifact.records
    }
    persisted: list[EvidenceORMRecord] = []
    new_ids: set[str] = set()
    for record in artifact.records:
        existing = repository.get_evidence_by_parsed_document_and_key(
            parsed_document_id, record.evidence_id
        )
        if existing is not None:
            if existing.content_sha256 != record.content_sha256 or existing.text != record.text:
                raise EvidenceMaterializationConflict(
                    "stable Evidence ID already has different immutable content"
                )
            persisted.append(existing)
            continue
        orm = EvidenceORMRecord(
            id=internal_ids[record.evidence_id],
            parsed_document_id=parsed_document_id,
            block_id=record.source_units[0].block_id,
            stable_key=record.evidence_id,
            evidence_type=record.evidence_type,
            text=record.text,
            char_start=0,
            char_end=len(record.text),
            confidence=record.confidence,
            content_sha256=record.content_sha256,
            metadata_json={
                "document_id": record.document_id,
                "document_version_id": record.document_version_id,
                "section_id": record.section_id,
                "section_path": list(record.section_path),
                "source_mode": record.source_mode,
                "normalized_sha256": record.normalized_sha256,
                "ocr": record.ocr.model_dump(mode="json") if record.ocr is not None else None,
                "warning_codes": list(record.warning_codes),
            },
        )
        repository.add(orm)
        persisted.append(orm)
        new_ids.add(record.evidence_id)
    repository.flush()

    for record in artifact.records:
        if record.evidence_id not in new_ids:
            continue
        evidence_id = internal_ids[record.evidence_id]
        for unit in record.source_units:
            repository.add(
                EvidenceBlockLinkRecord(
                    evidence_id=evidence_id,
                    block_id=unit.block_id,
                    ordinal=unit.ordinal,
                    char_start=unit.char_start,
                    char_end=unit.char_end,
                    text_sha256=unit.text_sha256,
                )
            )
        for ordinal, bbox in enumerate(record.page_bboxes):
            repository.add(
                EvidencePageBBoxRecord(
                    evidence_id=evidence_id,
                    ordinal=ordinal,
                    page_id=bbox.page_id,
                    bbox_json=list(bbox.bbox),
                    coordinate_space=bbox.coordinate_space,
                    physical_page_index=bbox.physical_page_index,
                    display_page_label=bbox.display_page_label,
                    page_width=bbox.page_width,
                    page_height=bbox.page_height,
                    source_region_id=bbox.source_region_id,
                )
            )
        for relation_type, target in (
            ("previous", record.previous_evidence_id),
            ("next", record.next_evidence_id),
        ):
            if target is not None:
                repository.add(
                    EvidenceRelationRecord(
                        source_evidence_id=evidence_id,
                        target_evidence_id=internal_ids[target],
                        relation_type=relation_type,
                    )
                )
    repository.flush()
    return tuple(persisted)
