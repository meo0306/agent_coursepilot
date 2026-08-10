from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from courserag.persistence.base import CourseRAGBase, new_id, utc_now


class IncrementalBuildPlanRecord(CourseRAGBase):
    __tablename__ = "courserag_incremental_build_plans"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "target_version_id",
            "profile_sha256",
            name="uq_courserag_incremental_plan",
        ),
        CheckConstraint(
            "status IN ('planned','running','succeeded','failed')", name="incremental_plan_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    source_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_document_versions.id", ondelete="RESTRICT")
    )
    target_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_document_versions.id", ondelete="CASCADE")
    )
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    change_coverage: Mapped[float] = mapped_column(Float, nullable=False)
    theoretical_reuse_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    actual_reuse_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    impact_summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SectionImpactRecord(CourseRAGBase):
    __tablename__ = "courserag_section_impacts"
    __table_args__ = (UniqueConstraint("plan_id", "ordinal", name="uq_courserag_section_impact"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_incremental_build_plans.id", ondelete="CASCADE"),
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source_section_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_sections.id", ondelete="SET NULL"), nullable=True
    )
    target_section_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_sections.id", ondelete="SET NULL"), nullable=True
    )
    change_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    affected_artifacts_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    candidates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class ArtifactReuseLinkRecord(CourseRAGBase):
    __tablename__ = "courserag_artifact_reuse_links"
    __table_args__ = (
        UniqueConstraint("plan_id", "target_artifact_id", name="uq_courserag_artifact_reuse"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_incremental_build_plans.id", ondelete="CASCADE"),
        index=True,
    )
    source_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="RESTRICT")
    )
    target_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="CASCADE")
    )
    artifact_kind: Mapped[str] = mapped_column(String(80), nullable=False)
    verified_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CitationMigrationRunRecord(CourseRAGBase):
    __tablename__ = "courserag_citation_migration_runs"
    __table_args__ = (
        UniqueConstraint(
            "source_version_id",
            "target_version_id",
            "profile_sha256",
            name="uq_courserag_citation_migration_run",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_document_versions.id", ondelete="RESTRICT")
    )
    target_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_document_versions.id", ondelete="CASCADE")
    )
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    summary_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CitationMigrationItemRecord(CourseRAGBase):
    __tablename__ = "courserag_citation_migration_items"
    __table_args__ = (
        UniqueConstraint(
            "run_id", "source_evidence_id", name="uq_courserag_citation_migration_item"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_citation_migration_runs.id", ondelete="CASCADE"),
        index=True,
    )
    source_evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="RESTRICT")
    )
    target_evidence_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    method: Mapped[str] = mapped_column(String(80), nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidates_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    reviewed_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class VerifiedIndexVersionRecord(CourseRAGBase):
    __tablename__ = "courserag_verified_index_versions"
    __table_args__ = (
        UniqueConstraint(
            "knowledge_base_id", "version_number", name="uq_courserag_verified_index_version"
        ),
        CheckConstraint(
            "status IN ('staging','active','retired','failed')", name="verified_index_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="staging")
    manifest_artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    base_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_verified_index_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    active_item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
