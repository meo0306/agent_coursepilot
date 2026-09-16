from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from courserag.persistence.base import CourseRAGBase, new_id, utc_now


class KnowledgePointRecord(CourseRAGBase):
    __tablename__ = "courserag_knowledge_points"
    __table_args__ = (
        UniqueConstraint("knowledge_base_id", "stable_key", name="uq_courserag_kp_key"),
        CheckConstraint(
            "status IN ('unreviewed','needs_review','approved','rejected','deprecated')",
            name="knowledge_point_status",
        ),
        Index("ix_courserag_kp_status_score", "knowledge_base_id", "status", "publish_score"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    stable_key: Mapped[str] = mapped_column(String(512), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_knowledge_point_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_points.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    publish_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    publish_score_components_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    auto_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    origin: Mapped[str] = mapped_column(String(80), nullable=False, default="auto_extracted")
    extractor_version: Mapped[str | None] = mapped_column(String(160), nullable=True)
    extractor_profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class KnowledgePointAliasRecord(CourseRAGBase):
    __tablename__ = "courserag_knowledge_point_aliases"
    __table_args__ = (
        UniqueConstraint("knowledge_point_id", "normalized_alias", name="uq_courserag_kp_alias"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias: Mapped[str] = mapped_column(String(240), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(240), nullable=False)
    basis: Mapped[str] = mapped_column(String(80), nullable=False, default="provider")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePointExtractionBatchRecord(CourseRAGBase):
    __tablename__ = "courserag_kp_extraction_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','partial','failed')",
            name="kp_extraction_batch_status",
        ),
        UniqueConstraint("knowledge_base_id", "identity_sha256", name="uq_courserag_kp_batch"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    build_job_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_build_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    identity_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(160), nullable=False)
    model_name: Mapped[str] = mapped_column(String(240), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scoring_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    window_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cost_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgePointWindowRecord(CourseRAGBase):
    __tablename__ = "courserag_kp_windows"
    __table_args__ = (UniqueConstraint("batch_id", "window_key", name="uq_courserag_kp_window"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_kp_extraction_batches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_sections.id", ondelete="CASCADE"), nullable=False
    )
    window_key: Mapped[str] = mapped_column(String(80), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence_ids_json: Mapped[list] = mapped_column(JSON, nullable=False)
    warning_codes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePointWindowRunRecord(CourseRAGBase):
    __tablename__ = "courserag_kp_window_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed','cached')",
            name="kp_window_run_status",
        ),
        UniqueConstraint("window_id", "attempt_number", name="uq_courserag_kp_window_attempt"),
        Index("ix_courserag_kp_window_cache", "cache_key", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    window_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_kp_windows.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(160), nullable=False)
    model_name: Mapped[str] = mapped_column(String(240), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class KnowledgePointEvidenceRecord(CourseRAGBase):
    __tablename__ = "courserag_knowledge_point_evidence"

    knowledge_point_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="summary")
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    extraction_batch_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_kp_extraction_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_status: Mapped[str] = mapped_column(String(32), nullable=False, default="unreviewed")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePointChunkRecord(CourseRAGBase):
    __tablename__ = "courserag_knowledge_point_chunks"

    knowledge_point_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_chunks.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="summary")
    strength: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    use_for_filtering: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    use_for_ranking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    derivation_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class KnowledgePointReviewRecord(CourseRAGBase):
    __tablename__ = "courserag_knowledge_point_reviews"
    __table_args__ = (
        UniqueConstraint("action", "idempotency_key", name="uq_courserag_kp_review_request"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_point_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"), index=True
    )
    reviewer_id: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    related_knowledge_point_ids_json: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    response_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resulting_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
