from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from courserag.persistence.base import CourseRAGBase, new_id, utc_now


class VerifiedContentRecord(CourseRAGBase):
    __tablename__ = "courserag_verified_content"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "idempotency_key", name="uq_courserag_verified_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False)
    content_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    version_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="teacher_verified")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_incomplete")
    retrieval_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    approval_record_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    current_overlay_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_verified_index_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revoke_idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    revoke_request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class VerifiedContentEvidenceRecord(CourseRAGBase):
    __tablename__ = "courserag_verified_content_evidence"

    verified_content_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_verified_content.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )


class VerifiedContentKnowledgePointRecord(CourseRAGBase):
    __tablename__ = "courserag_verified_content_knowledge_points"

    verified_content_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_verified_content.id", ondelete="CASCADE"),
        primary_key=True,
    )
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )


class EnrichmentBatchRecord(CourseRAGBase):
    __tablename__ = "courserag_enrichment_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False)
    identity_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    trigger_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_snapshot_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EnrichmentBatchItemRecord(CourseRAGBase):
    __tablename__ = "courserag_enrichment_batch_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_enrichment_batches.id", ondelete="CASCADE"), index=True
    )
    verified_content_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_verified_content.id", ondelete="CASCADE")
    )
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    knowledge_point_links_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
