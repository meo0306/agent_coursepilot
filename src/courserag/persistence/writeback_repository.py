from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from courserag.persistence.models import (
    ArtifactRecord,
    EnrichmentBatchItemRecord,
    EnrichmentBatchRecord,
    EvidenceRecord,
    KnowledgeBaseRecord,
    KnowledgePointRecord,
    VerifiedContentEvidenceRecord,
    VerifiedContentKnowledgePointRecord,
    VerifiedContentRecord,
    VerifiedIndexVersionRecord,
)
from courserag.persistence.models.document import (
    DocumentVersionRecord,
    ParsedDocumentRecord,
    SourceDocumentRecord,
)


class WritebackRepository:
    """Persistence boundary for verified content and its independent overlay."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def knowledge_base_for_course(self, course_id: str) -> KnowledgeBaseRecord | None:
        return self.session.scalar(
            select(KnowledgeBaseRecord).where(KnowledgeBaseRecord.course_id == course_id)
        )

    def lock_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseRecord | None:
        return self.session.scalar(
            select(KnowledgeBaseRecord)
            .where(KnowledgeBaseRecord.id == knowledge_base_id)
            .with_for_update()
        )

    def get_by_idempotency_key(
        self, knowledge_base_id: str, key: str
    ) -> VerifiedContentRecord | None:
        return self.session.scalar(
            select(VerifiedContentRecord).where(
                VerifiedContentRecord.knowledge_base_id == knowledge_base_id,
                VerifiedContentRecord.idempotency_key == key,
            )
        )

    def get_content(self, content_id: str) -> VerifiedContentRecord | None:
        return self.session.get(VerifiedContentRecord, content_id)

    def evidence_belongs_to(self, evidence_ids: list[str], knowledge_base_id: str) -> bool:
        if not evidence_ids:
            return False
        count = self.session.scalar(
            select(func.count(EvidenceRecord.id))
            .join(
                ParsedDocumentRecord, ParsedDocumentRecord.id == EvidenceRecord.parsed_document_id
            )
            .join(
                DocumentVersionRecord,
                DocumentVersionRecord.id == ParsedDocumentRecord.document_version_id,
            )
            .join(
                SourceDocumentRecord,
                SourceDocumentRecord.id == DocumentVersionRecord.source_document_id,
            )
            .where(
                EvidenceRecord.id.in_(evidence_ids),
                SourceDocumentRecord.knowledge_base_id == knowledge_base_id,
            )
        )
        return int(count or 0) == len(set(evidence_ids))

    def knowledge_points_belong_to(
        self, knowledge_point_ids: list[str], knowledge_base_id: str
    ) -> bool:
        if not knowledge_point_ids:
            return True
        count = self.session.scalar(
            select(func.count(KnowledgePointRecord.id)).where(
                KnowledgePointRecord.id.in_(knowledge_point_ids),
                KnowledgePointRecord.knowledge_base_id == knowledge_base_id,
            )
        )
        return int(count or 0) == len(set(knowledge_point_ids))

    def add_content(
        self,
        record: VerifiedContentRecord,
        *,
        evidence_ids: list[str],
        knowledge_point_ids: list[str],
    ) -> None:
        self.session.add(record)
        self.session.flush()
        for evidence_id in sorted(set(evidence_ids)):
            self.session.add(
                VerifiedContentEvidenceRecord(
                    verified_content_id=record.id, evidence_id=evidence_id
                )
            )
        for knowledge_point_id in sorted(set(knowledge_point_ids)):
            self.session.add(
                VerifiedContentKnowledgePointRecord(
                    verified_content_id=record.id, knowledge_point_id=knowledge_point_id
                )
            )
        self.session.flush()

    def active_contents(self, knowledge_base_id: str) -> list[VerifiedContentRecord]:
        return list(
            self.session.scalars(
                select(VerifiedContentRecord)
                .where(
                    VerifiedContentRecord.knowledge_base_id == knowledge_base_id,
                    VerifiedContentRecord.retrieval_active.is_(True),
                    VerifiedContentRecord.status != "revoked",
                )
                .order_by(VerifiedContentRecord.id)
            )
        )

    def next_overlay_version(self, knowledge_base_id: str) -> int:
        value = self.session.scalar(
            select(func.max(VerifiedIndexVersionRecord.version_number)).where(
                VerifiedIndexVersionRecord.knowledge_base_id == knowledge_base_id
            )
        )
        return int(value or 0) + 1

    def get_overlay_version(self, version_id: str | None) -> VerifiedIndexVersionRecord | None:
        return self.session.get(VerifiedIndexVersionRecord, version_id) if version_id else None

    def add(self, record: object) -> None:
        self.session.add(record)

    def flush(self) -> None:
        self.session.flush()

    def add_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        existing = self.session.scalar(
            select(ArtifactRecord).where(ArtifactRecord.sha256 == record.sha256)
        )
        if existing is not None:
            return existing
        self.session.add(record)
        self.session.flush()
        return record

    def pending_enrichment(self, knowledge_base_id: str) -> list[VerifiedContentRecord]:
        return list(
            self.session.scalars(
                select(VerifiedContentRecord)
                .where(
                    VerifiedContentRecord.knowledge_base_id == knowledge_base_id,
                    VerifiedContentRecord.status == "pending_enrichment",
                    VerifiedContentRecord.retrieval_active.is_(True),
                )
                .order_by(VerifiedContentRecord.created_at, VerifiedContentRecord.id)
                .with_for_update(skip_locked=True)
            )
        )

    def get_enrichment_batch_by_identity(self, identity: str) -> EnrichmentBatchRecord | None:
        return self.session.scalar(
            select(EnrichmentBatchRecord).where(EnrichmentBatchRecord.identity_sha256 == identity)
        )

    def add_enrichment_batch(
        self,
        record: EnrichmentBatchRecord,
        *,
        content_ids: tuple[str, ...],
        profile_sha256: str,
    ) -> None:
        self.session.add(record)
        self.session.flush()
        for content_id in content_ids:
            self.session.add(
                EnrichmentBatchItemRecord(
                    batch_id=record.id,
                    verified_content_id=content_id,
                    action="enrich_and_link_kp",
                    status="pending",
                    profile_sha256=profile_sha256,
                )
            )
        self.session.flush()
