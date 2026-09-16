from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from courserag.persistence.base import utc_now
from courserag.persistence.models import (
    ArtifactRecord,
    AuditEventRecord,
    BuildJobDocumentVersionRecord,
    BuildJobRecord,
    BuildStageRunRecord,
    ChunkEvidenceRecord,
    ChunkProfileRecord,
    ChunkRecord,
    ChunkSetRecord,
    ContextPackageRecord,
    DocumentVersionRecord,
    EvidenceBlockLinkRecord,
    EvidencePageBBoxRecord,
    EvidenceRecord,
    EvidenceRelationRecord,
    IndexChunkRecord,
    IndexDocumentVersionRecord,
    IndexVersionRecord,
    KnowledgeBaseRecord,
    KnowledgePointAliasRecord,
    KnowledgePointChunkRecord,
    KnowledgePointEvidenceRecord,
    KnowledgePointExtractionBatchRecord,
    KnowledgePointRecord,
    KnowledgePointReviewRecord,
    KnowledgePointWindowRecord,
    KnowledgePointWindowRunRecord,
    OCRPageResultRecord,
    ParsedDocumentRecord,
    QARunRecord,
    QueryProcessingRunRecord,
    RerankCacheRecord,
    RetrievalRunRecord,
    SectionRecord,
    SourceDocumentRecord,
)
from courserag.persistence.models.content import BlockRecord


class CourseRAGRepository:
    """Only persistence boundary used by the P03 application services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def add(self, record: object) -> None:
        self.session.add(record)

    def flush(self) -> None:
        self.session.flush()

    def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseRecord | None:
        return self.session.get(KnowledgeBaseRecord, knowledge_base_id)

    def get_knowledge_base_by_course(self, course_id: str) -> KnowledgeBaseRecord | None:
        return self.session.scalar(
            select(KnowledgeBaseRecord).where(KnowledgeBaseRecord.course_id == course_id)
        )

    def lock_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseRecord | None:
        return self.session.scalar(
            select(KnowledgeBaseRecord)
            .where(KnowledgeBaseRecord.id == knowledge_base_id)
            .with_for_update()
        )

    def get_source_document_by_legacy_id(
        self, knowledge_base_id: str, legacy_document_id: str
    ) -> SourceDocumentRecord | None:
        return self.session.scalar(
            select(SourceDocumentRecord).where(
                SourceDocumentRecord.knowledge_base_id == knowledge_base_id,
                SourceDocumentRecord.legacy_document_id == legacy_document_id,
            )
        )

    def next_document_version(self, source_document_id: str) -> int:
        value = self.session.scalar(
            select(func.max(DocumentVersionRecord.version_number)).where(
                DocumentVersionRecord.source_document_id == source_document_id
            )
        )
        return int(value or 0) + 1

    def get_build_job(self, build_job_id: str) -> BuildJobRecord | None:
        return self.session.get(BuildJobRecord, build_job_id)

    def get_document_version(self, document_version_id: str) -> DocumentVersionRecord | None:
        return self.session.get(DocumentVersionRecord, document_version_id)

    def get_parsed_document_by_version(
        self, document_version_id: str
    ) -> ParsedDocumentRecord | None:
        return self.session.scalar(
            select(ParsedDocumentRecord).where(
                ParsedDocumentRecord.document_version_id == document_version_id
            )
        )

    def get_evidence_by_stable_key(self, course_id: str, stable_key: str) -> EvidenceRecord | None:
        return self.session.scalar(
            select(EvidenceRecord)
            .join(
                ParsedDocumentRecord,
                ParsedDocumentRecord.id == EvidenceRecord.parsed_document_id,
            )
            .join(
                DocumentVersionRecord,
                DocumentVersionRecord.id == ParsedDocumentRecord.document_version_id,
            )
            .join(
                SourceDocumentRecord,
                SourceDocumentRecord.id == DocumentVersionRecord.source_document_id,
            )
            .join(
                KnowledgeBaseRecord,
                KnowledgeBaseRecord.id == SourceDocumentRecord.knowledge_base_id,
            )
            .where(
                KnowledgeBaseRecord.course_id == course_id,
                EvidenceRecord.stable_key == stable_key,
            )
        )

    def get_evidence_by_parsed_document_and_key(
        self, parsed_document_id: str, stable_key: str
    ) -> EvidenceRecord | None:
        return self.session.scalar(
            select(EvidenceRecord).where(
                EvidenceRecord.parsed_document_id == parsed_document_id,
                EvidenceRecord.stable_key == stable_key,
            )
        )

    def get_evidence(self, evidence_id: str) -> EvidenceRecord | None:
        return self.session.get(EvidenceRecord, evidence_id)

    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        return self.session.get(ChunkRecord, chunk_id)

    def get_chunk_profile_by_sha256(self, profile_sha256: str) -> ChunkProfileRecord | None:
        return self.session.scalar(
            select(ChunkProfileRecord).where(ChunkProfileRecord.profile_sha256 == profile_sha256)
        )

    def get_chunk_set_by_content_sha256(self, content_sha256: str) -> ChunkSetRecord | None:
        return self.session.scalar(
            select(ChunkSetRecord).where(ChunkSetRecord.content_sha256 == content_sha256)
        )

    def list_chunks_by_set(self, chunk_set_id: str) -> list[ChunkRecord]:
        return list(
            self.session.scalars(
                select(ChunkRecord)
                .where(ChunkRecord.chunk_set_id == chunk_set_id)
                .order_by(ChunkRecord.chunk_kind.desc(), ChunkRecord.ordinal)
            )
        )

    def get_knowledge_point(self, knowledge_point_id: str) -> KnowledgePointRecord | None:
        return self.session.get(KnowledgePointRecord, knowledge_point_id)

    def get_knowledge_point_by_key(
        self, knowledge_base_id: str, stable_key: str
    ) -> KnowledgePointRecord | None:
        return self.session.scalar(
            select(KnowledgePointRecord).where(
                KnowledgePointRecord.knowledge_base_id == knowledge_base_id,
                KnowledgePointRecord.stable_key == stable_key,
            )
        )

    def get_knowledge_point_by_normalized_name(
        self, knowledge_base_id: str, normalized_name: str
    ) -> KnowledgePointRecord | None:
        return self.session.scalar(
            select(KnowledgePointRecord).where(
                KnowledgePointRecord.knowledge_base_id == knowledge_base_id,
                KnowledgePointRecord.normalized_name == normalized_name,
                KnowledgePointRecord.status != "deprecated",
            )
        )

    def list_knowledge_points(
        self,
        knowledge_base_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgePointRecord]:
        statement = select(KnowledgePointRecord).where(
            KnowledgePointRecord.knowledge_base_id == knowledge_base_id
        )
        if status is not None:
            statement = statement.where(KnowledgePointRecord.status == status)
        return list(
            self.session.scalars(
                statement.order_by(KnowledgePointRecord.title, KnowledgePointRecord.id)
                .offset(offset)
                .limit(limit)
            )
        )

    def list_knowledge_point_aliases(
        self, knowledge_point_id: str
    ) -> list[KnowledgePointAliasRecord]:
        return list(
            self.session.scalars(
                select(KnowledgePointAliasRecord)
                .where(KnowledgePointAliasRecord.knowledge_point_id == knowledge_point_id)
                .order_by(KnowledgePointAliasRecord.alias)
            )
        )

    def delete_knowledge_point_aliases(self, knowledge_point_id: str) -> None:
        self.session.execute(
            delete(KnowledgePointAliasRecord).where(
                KnowledgePointAliasRecord.knowledge_point_id == knowledge_point_id
            )
        )

    def get_knowledge_point_alias(
        self, knowledge_point_id: str, normalized_alias: str
    ) -> KnowledgePointAliasRecord | None:
        return self.session.scalar(
            select(KnowledgePointAliasRecord).where(
                KnowledgePointAliasRecord.knowledge_point_id == knowledge_point_id,
                KnowledgePointAliasRecord.normalized_alias == normalized_alias,
            )
        )

    def list_knowledge_point_evidence(
        self, knowledge_point_id: str
    ) -> list[KnowledgePointEvidenceRecord]:
        return list(
            self.session.scalars(
                select(KnowledgePointEvidenceRecord).where(
                    KnowledgePointEvidenceRecord.knowledge_point_id == knowledge_point_id
                )
            )
        )

    def get_knowledge_point_evidence_link(
        self, knowledge_point_id: str, evidence_id: str
    ) -> KnowledgePointEvidenceRecord | None:
        return self.session.get(KnowledgePointEvidenceRecord, (knowledge_point_id, evidence_id))

    def get_knowledge_point_chunk_link(
        self, knowledge_point_id: str, chunk_id: str
    ) -> KnowledgePointChunkRecord | None:
        return self.session.get(KnowledgePointChunkRecord, (knowledge_point_id, chunk_id))

    def list_knowledge_point_chunks(
        self, knowledge_point_id: str
    ) -> list[KnowledgePointChunkRecord]:
        return list(
            self.session.scalars(
                select(KnowledgePointChunkRecord).where(
                    KnowledgePointChunkRecord.knowledge_point_id == knowledge_point_id
                )
            )
        )

    def list_knowledge_point_reviews(
        self, knowledge_point_id: str
    ) -> list[KnowledgePointReviewRecord]:
        return list(
            self.session.scalars(
                select(KnowledgePointReviewRecord)
                .where(KnowledgePointReviewRecord.knowledge_point_id == knowledge_point_id)
                .order_by(KnowledgePointReviewRecord.created_at)
            )
        )

    def list_chunks_for_evidence(self, evidence_id: str) -> list[ChunkRecord]:
        return list(
            self.session.scalars(
                select(ChunkRecord)
                .join(ChunkEvidenceRecord, ChunkEvidenceRecord.chunk_id == ChunkRecord.id)
                .where(ChunkEvidenceRecord.evidence_id == evidence_id)
                .order_by(ChunkRecord.ordinal)
            )
        )

    def list_sections_for_document_versions(
        self, document_version_ids: tuple[str, ...]
    ) -> list[SectionRecord]:
        if not document_version_ids:
            return []
        return list(
            self.session.scalars(
                select(SectionRecord)
                .join(
                    ParsedDocumentRecord,
                    ParsedDocumentRecord.id == SectionRecord.parsed_document_id,
                )
                .where(ParsedDocumentRecord.document_version_id.in_(document_version_ids))
                .order_by(
                    ParsedDocumentRecord.document_version_id,
                    SectionRecord.ordinal,
                    SectionRecord.id,
                )
            )
        )

    def list_evidence_for_section(self, section_id: str) -> list[EvidenceRecord]:
        return list(
            self.session.scalars(
                select(EvidenceRecord)
                .join(
                    EvidenceBlockLinkRecord,
                    EvidenceBlockLinkRecord.evidence_id == EvidenceRecord.id,
                )
                .join(BlockRecord, BlockRecord.id == EvidenceBlockLinkRecord.block_id)
                .where(BlockRecord.section_id == section_id)
                .order_by(BlockRecord.ordinal, EvidenceBlockLinkRecord.ordinal)
                .distinct()
            )
        )

    def delete_knowledge_point_chunk_links(self, knowledge_point_id: str) -> None:
        self.session.execute(
            delete(KnowledgePointChunkRecord).where(
                KnowledgePointChunkRecord.knowledge_point_id == knowledge_point_id
            )
        )

    def get_kp_extraction_batch(
        self, knowledge_base_id: str, identity_sha256: str
    ) -> KnowledgePointExtractionBatchRecord | None:
        return self.session.scalar(
            select(KnowledgePointExtractionBatchRecord).where(
                KnowledgePointExtractionBatchRecord.knowledge_base_id == knowledge_base_id,
                KnowledgePointExtractionBatchRecord.identity_sha256 == identity_sha256,
            )
        )

    def get_kp_window(self, batch_id: str, window_key: str) -> KnowledgePointWindowRecord | None:
        return self.session.scalar(
            select(KnowledgePointWindowRecord).where(
                KnowledgePointWindowRecord.batch_id == batch_id,
                KnowledgePointWindowRecord.window_key == window_key,
            )
        )

    def get_kp_window_by_key(self, window_key: str) -> KnowledgePointWindowRecord | None:
        return self.session.scalar(
            select(KnowledgePointWindowRecord)
            .where(KnowledgePointWindowRecord.window_key == window_key)
            .order_by(KnowledgePointWindowRecord.created_at.desc())
            .limit(1)
        )

    def find_cached_kp_window_run(self, cache_key: str) -> KnowledgePointWindowRunRecord | None:
        return self.session.scalar(
            select(KnowledgePointWindowRunRecord)
            .where(
                KnowledgePointWindowRunRecord.cache_key == cache_key,
                KnowledgePointWindowRunRecord.status.in_(("succeeded", "cached")),
                KnowledgePointWindowRunRecord.artifact_id.is_not(None),
            )
            .order_by(KnowledgePointWindowRunRecord.completed_at.desc())
            .limit(1)
        )

    def next_kp_window_attempt(self, window_id: str) -> int:
        value = self.session.scalar(
            select(func.max(KnowledgePointWindowRunRecord.attempt_number)).where(
                KnowledgePointWindowRunRecord.window_id == window_id
            )
        )
        return int(value or 0) + 1

    def get_running_kp_window_run(self, window_id: str) -> KnowledgePointWindowRunRecord | None:
        return self.session.scalar(
            select(KnowledgePointWindowRunRecord)
            .where(
                KnowledgePointWindowRunRecord.window_id == window_id,
                KnowledgePointWindowRunRecord.status == "running",
            )
            .order_by(KnowledgePointWindowRunRecord.attempt_number.desc())
            .limit(1)
        )

    def get_kp_review_by_idempotency(
        self, action: str, idempotency_key: str
    ) -> KnowledgePointReviewRecord | None:
        return self.session.scalar(
            select(KnowledgePointReviewRecord).where(
                KnowledgePointReviewRecord.action == action,
                KnowledgePointReviewRecord.idempotency_key == idempotency_key,
            )
        )

    def list_evidence_block_links(
        self, evidence_id: str
    ) -> list[tuple[EvidenceBlockLinkRecord, BlockRecord]]:
        statement = (
            select(EvidenceBlockLinkRecord, BlockRecord)
            .join(BlockRecord, BlockRecord.id == EvidenceBlockLinkRecord.block_id)
            .where(EvidenceBlockLinkRecord.evidence_id == evidence_id)
            .order_by(EvidenceBlockLinkRecord.ordinal)
        )
        return list(self.session.execute(statement).tuples())

    def list_evidence_page_bboxes(self, evidence_id: str) -> list[EvidencePageBBoxRecord]:
        return list(
            self.session.scalars(
                select(EvidencePageBBoxRecord)
                .where(EvidencePageBBoxRecord.evidence_id == evidence_id)
                .order_by(EvidencePageBBoxRecord.ordinal)
            )
        )

    def get_evidence_relation_target(
        self, evidence_id: str, relation_type: str
    ) -> EvidenceRecord | None:
        return self.session.scalar(
            select(EvidenceRecord)
            .join(
                EvidenceRelationRecord,
                EvidenceRelationRecord.target_evidence_id == EvidenceRecord.id,
            )
            .where(
                EvidenceRelationRecord.source_evidence_id == evidence_id,
                EvidenceRelationRecord.relation_type == relation_type,
            )
        )

    def list_build_document_versions(self, build_job_id: str) -> list[DocumentVersionRecord]:
        return list(
            self.session.scalars(
                select(DocumentVersionRecord)
                .join(
                    BuildJobDocumentVersionRecord,
                    BuildJobDocumentVersionRecord.document_version_id == DocumentVersionRecord.id,
                )
                .where(BuildJobDocumentVersionRecord.build_job_id == build_job_id)
                .order_by(DocumentVersionRecord.id)
            )
        )

    def get_build_job_by_request(
        self, knowledge_base_id: str, request_hash: str
    ) -> BuildJobRecord | None:
        return self.session.scalar(
            select(BuildJobRecord).where(
                BuildJobRecord.knowledge_base_id == knowledge_base_id,
                BuildJobRecord.request_hash == request_hash,
            )
        )

    def next_stage_attempt(self, build_job_id: str, stage_name: str) -> int:
        value = self.session.scalar(
            select(func.max(BuildStageRunRecord.attempt_number)).where(
                BuildStageRunRecord.build_job_id == build_job_id,
                BuildStageRunRecord.stage_name == stage_name,
            )
        )
        return int(value or 0) + 1

    def find_reusable_job_stage(
        self, build_job_id: str, stage_name: str, fingerprint: str
    ) -> BuildStageRunRecord | None:
        return self.session.scalar(
            select(BuildStageRunRecord)
            .where(
                BuildStageRunRecord.build_job_id == build_job_id,
                BuildStageRunRecord.stage_name == stage_name,
                BuildStageRunRecord.fingerprint == fingerprint,
                BuildStageRunRecord.status.in_(("succeeded", "cached")),
                BuildStageRunRecord.artifact_id.is_not(None),
            )
            .order_by(BuildStageRunRecord.attempt_number.desc())
            .limit(1)
        )

    def list_running_stage_attempts(
        self, build_job_id: str, stage_name: str
    ) -> list[BuildStageRunRecord]:
        return list(
            self.session.scalars(
                select(BuildStageRunRecord).where(
                    BuildStageRunRecord.build_job_id == build_job_id,
                    BuildStageRunRecord.stage_name == stage_name,
                    BuildStageRunRecord.status == "running",
                )
            )
        )

    def find_cached_stage(self, fingerprint: str) -> BuildStageRunRecord | None:
        query: Select[tuple[BuildStageRunRecord]] = (
            select(BuildStageRunRecord)
            .where(
                BuildStageRunRecord.fingerprint == fingerprint,
                BuildStageRunRecord.status.in_(("succeeded", "cached")),
                BuildStageRunRecord.artifact_id.is_not(None),
            )
            .order_by(BuildStageRunRecord.completed_at.desc())
            .limit(1)
        )
        return self.session.scalar(query)

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.session.get(ArtifactRecord, artifact_id)

    def get_ocr_page_result(self, page_id: str) -> OCRPageResultRecord | None:
        return self.session.scalar(
            select(OCRPageResultRecord).where(OCRPageResultRecord.page_id == page_id)
        )

    def get_artifact_by_sha256(self, sha256: str) -> ArtifactRecord | None:
        return self.session.scalar(select(ArtifactRecord).where(ArtifactRecord.sha256 == sha256))

    def get_or_create_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        existing = self.get_artifact_by_sha256(record.sha256)
        if existing is not None:
            return existing
        try:
            with self.session.begin_nested():
                self.add(record)
                self.flush()
        except IntegrityError:
            existing = self.get_artifact_by_sha256(record.sha256)
            if existing is None:
                raise
            return existing
        return record

    def list_artifact_uris(self) -> set[str]:
        return set(self.session.scalars(select(ArtifactRecord.uri)))

    def get_index_version(self, index_version_id: str) -> IndexVersionRecord | None:
        return self.session.get(IndexVersionRecord, index_version_id)

    def next_index_version(self, knowledge_base_id: str) -> int:
        value = self.session.scalar(
            select(func.max(IndexVersionRecord.version_number)).where(
                IndexVersionRecord.knowledge_base_id == knowledge_base_id
            )
        )
        return int(value or 0) + 1

    def add_index_document_versions(
        self, index_version_id: str, document_version_ids: list[str]
    ) -> None:
        for document_version_id in document_version_ids:
            self.add(
                IndexDocumentVersionRecord(
                    index_version_id=index_version_id,
                    document_version_id=document_version_id,
                )
            )
        self.flush()

    def add_index_chunks(self, index_version_id: str, chunk_ids: list[str]) -> None:
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("Index Chunk IDs must be unique")
        for ordinal, chunk_id in enumerate(chunk_ids):
            self.add(
                IndexChunkRecord(
                    index_version_id=index_version_id,
                    chunk_id=chunk_id,
                    ordinal=ordinal,
                )
            )
        self.flush()

    def list_index_chunk_ids(self, index_version_id: str) -> list[str]:
        statement = (
            select(IndexChunkRecord.chunk_id)
            .where(IndexChunkRecord.index_version_id == index_version_id)
            .order_by(IndexChunkRecord.ordinal)
        )
        return list(self.session.scalars(statement))

    def get_chunks(self, chunk_ids: list[str]) -> dict[str, ChunkRecord]:
        if not chunk_ids:
            return {}
        rows = self.session.scalars(select(ChunkRecord).where(ChunkRecord.id.in_(chunk_ids)))
        return {row.id: row for row in rows}

    def get_rerank_cache(self, cache_key: str) -> RerankCacheRecord | None:
        return self.session.get(RerankCacheRecord, cache_key)

    def add_retrieval_run(self, record: RetrievalRunRecord) -> None:
        self.add(record)
        self.flush()

    def add_context_package(self, record: ContextPackageRecord) -> None:
        self.add(record)
        self.flush()

    def get_context_package(self, context_package_id: str) -> ContextPackageRecord | None:
        return self.session.get(ContextPackageRecord, context_package_id)

    def add_qa_run(self, record: QARunRecord) -> None:
        self.add(record)
        self.flush()

    def get_or_create_normalize_query_run(
        self,
        *,
        knowledge_base_id: str,
        request_id: str,
        trace_id: str,
        input_sha256: str,
        normalized_query: str,
    ) -> QueryProcessingRunRecord:
        existing = self.session.scalar(
            select(QueryProcessingRunRecord).where(
                QueryProcessingRunRecord.knowledge_base_id == knowledge_base_id,
                QueryProcessingRunRecord.request_id == request_id,
                QueryProcessingRunRecord.input_sha256 == input_sha256,
            )
        )
        if existing is not None:
            return existing
        record = QueryProcessingRunRecord(
            knowledge_base_id=knowledge_base_id,
            request_id=request_id,
            trace_id=trace_id,
            input_sha256=input_sha256,
            output_json={"profile": "normalize-only/p08", "normalized_query": normalized_query},
        )
        self.add(record)
        self.flush()
        return record

    def list_cleanup_artifacts(self, cutoff: datetime) -> list[ArtifactRecord]:
        referenced = (
            select(BuildStageRunRecord.artifact_id)
            .where(BuildStageRunRecord.artifact_id.is_not(None))
            .union(
                select(IndexVersionRecord.dense_manifest_artifact_id).where(
                    IndexVersionRecord.dense_manifest_artifact_id.is_not(None)
                ),
                select(IndexVersionRecord.sparse_manifest_artifact_id).where(
                    IndexVersionRecord.sparse_manifest_artifact_id.is_not(None)
                ),
                select(IndexVersionRecord.overall_manifest_artifact_id).where(
                    IndexVersionRecord.overall_manifest_artifact_id.is_not(None)
                ),
                select(ParsedDocumentRecord.artifact_id).where(
                    ParsedDocumentRecord.artifact_id.is_not(None)
                ),
                select(OCRPageResultRecord.artifact_id).where(
                    OCRPageResultRecord.artifact_id.is_not(None)
                ),
            )
        )
        return list(
            self.session.scalars(
                select(ArtifactRecord).where(
                    ArtifactRecord.created_at < cutoff,
                    ArtifactRecord.status == "available",
                    ArtifactRecord.id.not_in(referenced),
                )
            )
        )

    def list_stale_staging_indexes(
        self, cutoff: datetime, active_index_id: str | None = None
    ) -> list[IndexVersionRecord]:
        clauses = [
            IndexVersionRecord.status.in_(("staging", "failed")),
            IndexVersionRecord.created_at < cutoff,
        ]
        if active_index_id is not None:
            clauses.append(IndexVersionRecord.id != active_index_id)
        return list(self.session.scalars(select(IndexVersionRecord).where(*clauses)))

    def audit(
        self,
        event_type: str,
        scope_type: str,
        scope_id: str,
        *,
        actor_id: str = "system",
        details: dict | None = None,
    ) -> None:
        self.add(
            AuditEventRecord(
                event_type=event_type,
                scope_type=scope_type,
                scope_id=scope_id,
                actor_id=actor_id,
                details_json=details or {},
                created_at=utc_now(),
            )
        )
