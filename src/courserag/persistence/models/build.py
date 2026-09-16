from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from courserag.persistence.base import CourseRAGBase, new_id, utc_now


class ArtifactRecord(CourseRAGBase):
    __tablename__ = "courserag_artifacts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available','quarantined','orphaned','deleted')",
            name="artifact_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    uri: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    media_type: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="available")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BuildJobRecord(CourseRAGBase):
    __tablename__ = "courserag_build_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="build_job_status",
        ),
        UniqueConstraint(
            "knowledge_base_id", "request_hash", name="uq_courserag_build_jobs_request"
        ),
        Index("ix_courserag_build_jobs_queue", "status", "locked_until", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    queue_task_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    build_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="incremental")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    force_rebuild: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_from_stage: Mapped[str | None] = mapped_column(String(160), nullable=True)
    target_index_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "courserag_index_versions.id",
            name="fk_courserag_build_job_target_index",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    worker_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BuildJobDocumentVersionRecord(CourseRAGBase):
    __tablename__ = "courserag_build_job_document_versions"

    build_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_build_jobs.id", ondelete="CASCADE"), primary_key=True
    )
    document_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class BuildStageRunRecord(CourseRAGBase):
    __tablename__ = "courserag_build_stage_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cached','skipped')",
            name="build_stage_status",
        ),
        UniqueConstraint(
            "build_job_id",
            "stage_name",
            "attempt_number",
            name="uq_courserag_stage_job_name_attempt",
        ),
        Index("ix_courserag_stage_fingerprint_status", "fingerprint", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    build_job_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_build_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_name: Mapped[str] = mapped_column(String(160), nullable=False)
    stage_version: Mapped[str] = mapped_column(String(160), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    input_hashes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    config_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    counts_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(160), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndexVersionRecord(CourseRAGBase):
    __tablename__ = "courserag_index_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('staging','validating','active','retired','failed')",
            name="index_version_status",
        ),
        CheckConstraint(
            "sparse_status IN ('ready','not_materialized')",
            name="index_sparse_status",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "version_number",
            name="uq_courserag_index_versions_number",
        ),
        Index(
            "uq_courserag_one_active_index",
            "knowledge_base_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    build_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_build_jobs.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    base_index_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_index_versions.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staging")
    dense_manifest_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    sparse_manifest_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    overall_manifest_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    sparse_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_materialized"
    )
    manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndexDocumentVersionRecord(CourseRAGBase):
    __tablename__ = "courserag_index_document_versions"

    index_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_index_versions.id", ondelete="CASCADE"), primary_key=True
    )
    document_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class AuditEventRecord(CourseRAGBase):
    __tablename__ = "courserag_audit_events"
    __table_args__ = (Index("ix_courserag_audit_scope", "scope_type", "scope_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(80), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(160), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(160), nullable=False, default="system")
    details_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
