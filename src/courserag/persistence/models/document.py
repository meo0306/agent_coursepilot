from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
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


class KnowledgeBaseRecord(CourseRAGBase):
    __tablename__ = "courserag_knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            "status IN ('empty','building','ready','ready_with_warnings','failed','archived')",
            name="knowledge_base_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    course_id: Mapped[str] = mapped_column(String(160), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(32), nullable=False, default="zh-CN")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="empty")
    active_index_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "courserag_index_versions.id",
            name="fk_courserag_kb_active_index_version",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    active_verified_index_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "courserag_verified_index_versions.id",
            name="fk_courserag_kb_active_verified_index",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class SourceDocumentRecord(CourseRAGBase):
    __tablename__ = "courserag_source_documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('pdf','docx')",
            name="source_document_type",
        ),
        CheckConstraint(
            "status IN ('registered','building','ready','failed','deleted')",
            name="source_document_status",
        ),
        CheckConstraint(
            "source_tier IN ('primary_source','teacher_verified','external_reference','generated_draft')",
            name="source_document_tier",
        ),
        UniqueConstraint(
            "knowledge_base_id",
            "legacy_document_id",
            name="uq_courserag_source_documents_kb_legacy",
        ),
        Index("ix_courserag_source_documents_tier", "knowledge_base_id", "source_tier"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    legacy_document_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    document_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    source_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="primary_source")
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "courserag_document_versions.id",
            name="fk_courserag_source_document_current_version",
            use_alter=True,
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class DocumentVersionRecord(CourseRAGBase):
    __tablename__ = "courserag_document_versions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('registered','building','ready','failed','superseded')",
            name="document_version_status",
        ),
        UniqueConstraint(
            "source_document_id",
            "version_number",
            name="uq_courserag_document_versions_number",
        ),
        UniqueConstraint(
            "source_document_id",
            "content_sha256",
            name="uq_courserag_document_versions_content",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source_document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_source_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "courserag_document_versions.id",
            name="fk_courserag_document_version_previous",
            ondelete="SET NULL",
        ),
        nullable=True,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    object_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(160), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="registered")
    source_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ParsedDocumentRecord(CourseRAGBase):
    __tablename__ = "courserag_parsed_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','running','ready','ready_with_warnings','failed')",
            name="parsed_document_status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    document_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    parser_profile: Mapped[str] = mapped_column(String(160), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(160), nullable=False)
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class PageRecord(CourseRAGBase):
    __tablename__ = "courserag_pages"
    __table_args__ = (
        UniqueConstraint(
            "parsed_document_id", "page_index", name="uq_courserag_pages_document_index"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parsed_document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_index: Mapped[int] = mapped_column(Integer, nullable=False)
    display_page_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class OCRPageResultRecord(CourseRAGBase):
    __tablename__ = "courserag_ocr_page_results"
    __table_args__ = (
        CheckConstraint(
            "status IN ('legacy_incomplete','ready','ready_with_warnings','failed')",
            name="ocr_page_result_status",
        ),
        CheckConstraint(
            "status NOT IN ('ready','ready_with_warnings') OR ("
            "model_name IS NOT NULL AND model_manifest_sha256 IS NOT NULL AND "
            "profile_sha256 IS NOT NULL AND dpi IS NOT NULL AND image_width IS NOT NULL AND "
            "image_height IS NOT NULL AND text_content IS NOT NULL AND regions_json IS NOT NULL "
            "AND result_sha256 IS NOT NULL AND duration_ms IS NOT NULL AND "
            "peak_memory_bytes IS NOT NULL AND created_at IS NOT NULL)",
            name="ocr_page_result_complete",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    page_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("courserag_pages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    artifact_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_artifacts.id", ondelete="SET NULL"), nullable=True
    )
    engine: Mapped[str] = mapped_column(String(160), nullable=False)
    engine_version: Mapped[str] = mapped_column(String(160), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="legacy_incomplete")
    model_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    model_manifest_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dpi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    regions_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    peak_memory_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
