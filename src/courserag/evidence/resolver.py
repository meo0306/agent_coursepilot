"""Course-scoped Evidence resolver and source-preview application service."""

from __future__ import annotations

from pydantic import Field

from courserag.domain.document import StrictIRModel
from courserag.domain.evidence import (
    EvidenceOCRProvenance,
    EvidenceRecord,
    EvidenceSourceUnit,
    PageBBox,
)
from courserag.persistence.models import EvidenceRecord as EvidenceORMRecord
from courserag.persistence.repositories import CourseRAGRepository


class EvidenceNotFoundError(LookupError):
    pass


class EvidenceIntegrityError(RuntimeError):
    pass


class ResolvedEvidenceBatch(StrictIRModel):
    records: tuple[EvidenceRecord, ...]
    missing_ids: tuple[str, ...]


class SourcePreview(StrictIRModel):
    evidence: EvidenceRecord
    previous_text: str | None = None
    next_text: str | None = None
    max_context_chars: int = Field(ge=1)


class EvidenceResolver:
    def __init__(self, repository: CourseRAGRepository, *, batch_limit: int = 100) -> None:
        if batch_limit < 1:
            raise ValueError("Evidence batch limit must be positive")
        self.repository = repository
        self.batch_limit = batch_limit

    def resolve(self, course_id: str, evidence_id: str) -> EvidenceRecord:
        orm = self.repository.get_evidence_by_stable_key(course_id, evidence_id)
        if orm is None:
            raise EvidenceNotFoundError(f"Evidence not found: {evidence_id}")
        return self._to_domain(orm)

    def batch_resolve(self, course_id: str, evidence_ids: list[str]) -> ResolvedEvidenceBatch:
        if len(evidence_ids) > self.batch_limit:
            raise ValueError(f"Evidence batch exceeds limit {self.batch_limit}")
        records: list[EvidenceRecord] = []
        missing: list[str] = []
        for evidence_id in evidence_ids:
            orm = self.repository.get_evidence_by_stable_key(course_id, evidence_id)
            if orm is None:
                missing.append(evidence_id)
            else:
                records.append(self._to_domain(orm))
        return ResolvedEvidenceBatch(records=tuple(records), missing_ids=tuple(missing))

    def source_preview(
        self, course_id: str, evidence_id: str, *, max_context_chars: int = 500
    ) -> SourcePreview:
        if max_context_chars < 1:
            raise ValueError("Source-preview context limit must be positive")
        orm = self.repository.get_evidence_by_stable_key(course_id, evidence_id)
        if orm is None:
            raise EvidenceNotFoundError(f"Evidence not found: {evidence_id}")
        evidence = self._to_domain(orm)
        previous = self.repository.get_evidence_relation_target(orm.id, "previous")
        following = self.repository.get_evidence_relation_target(orm.id, "next")
        return SourcePreview(
            evidence=evidence,
            previous_text=(previous.text[-max_context_chars:] if previous is not None else None),
            next_text=(following.text[:max_context_chars] if following is not None else None),
            max_context_chars=max_context_chars,
        )

    def _to_domain(self, orm: EvidenceORMRecord) -> EvidenceRecord:
        metadata = orm.metadata_json
        links = self.repository.list_evidence_block_links(orm.id)
        if not links:
            raise EvidenceIntegrityError("Evidence has no source-block links")
        units = tuple(
            EvidenceSourceUnit(
                block_id=link.block_id,
                block_type=block.block_type,
                ordinal=link.ordinal,
                char_start=link.char_start,
                char_end=link.char_end,
                text=block.text[link.char_start : link.char_end],
                text_sha256=link.text_sha256,
            )
            for link, block in links
        )
        bboxes = tuple(
            PageBBox(
                page_id=bbox.page_id,
                physical_page_index=bbox.physical_page_index,
                display_page_label=bbox.display_page_label,
                bbox=tuple(bbox.bbox_json),
                coordinate_space=bbox.coordinate_space,
                page_width=bbox.page_width,
                page_height=bbox.page_height,
                source_region_id=bbox.source_region_id,
            )
            for bbox in self.repository.list_evidence_page_bboxes(orm.id)
        )
        previous = self.repository.get_evidence_relation_target(orm.id, "previous")
        following = self.repository.get_evidence_relation_target(orm.id, "next")
        try:
            return EvidenceRecord(
                evidence_id=orm.stable_key,
                document_id=str(metadata["document_id"]),
                document_version_id=str(metadata["document_version_id"]),
                section_id=(str(metadata["section_id"]) if metadata.get("section_id") else None),
                section_path=tuple(str(value) for value in metadata.get("section_path", [])),
                evidence_type=orm.evidence_type,
                source_mode=str(metadata["source_mode"]),
                text=orm.text,
                content_sha256=orm.content_sha256,
                normalized_sha256=str(metadata["normalized_sha256"]),
                source_units=units,
                page_bboxes=bboxes,
                previous_evidence_id=previous.stable_key if previous is not None else None,
                next_evidence_id=following.stable_key if following is not None else None,
                confidence=orm.confidence,
                ocr=(
                    EvidenceOCRProvenance.model_validate(metadata["ocr"])
                    if metadata.get("ocr") is not None
                    else None
                ),
                warning_codes=tuple(str(code) for code in metadata.get("warning_codes", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvidenceIntegrityError("Persisted Evidence failed integrity validation") from exc
