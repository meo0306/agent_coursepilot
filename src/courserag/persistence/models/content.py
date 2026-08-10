from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
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


class SectionRecord(CourseRAGBase):
    __tablename__ = "courserag_sections"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "stable_path", name="uq_courserag_section_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parsed_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"), index=True
    )
    parent_section_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_sections.id", ondelete="CASCADE"), nullable=True
    )
    stable_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    heading: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class BlockRecord(CourseRAGBase):
    __tablename__ = "courserag_blocks"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "stable_path", name="uq_courserag_block_path"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parsed_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_sections.id", ondelete="SET NULL"), nullable=True
    )
    page_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_pages.id", ondelete="SET NULL"), nullable=True
    )
    stable_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    block_type: Mapped[str] = mapped_column(String(80), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class EvidenceRecord(CourseRAGBase):
    __tablename__ = "courserag_evidence"
    __table_args__ = (
        UniqueConstraint("parsed_document_id", "stable_key", name="uq_courserag_evidence_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parsed_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"), index=True
    )
    block_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_blocks.id", ondelete="SET NULL"), nullable=True
    )
    stable_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class EvidenceBlockLinkRecord(CourseRAGBase):
    __tablename__ = "courserag_evidence_block_links"

    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )
    block_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_blocks.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False)


class EvidencePageBBoxRecord(CourseRAGBase):
    __tablename__ = "courserag_evidence_page_bboxes"

    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    page_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_pages.id", ondelete="CASCADE"), nullable=False
    )
    bbox_json: Mapped[list] = mapped_column(JSON, nullable=False)
    coordinate_space: Mapped[str] = mapped_column(String(80), nullable=False)
    physical_page_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_page_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    page_width: Mapped[float] = mapped_column(Float, nullable=False)
    page_height: Mapped[float] = mapped_column(Float, nullable=False)
    source_region_id: Mapped[str | None] = mapped_column(String(160), nullable=True)


class EvidenceRelationRecord(CourseRAGBase):
    __tablename__ = "courserag_evidence_relations"
    __table_args__ = (
        CheckConstraint("relation_type IN ('previous','next')", name="evidence_relation_type"),
    )

    source_evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )
    target_evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )
    relation_type: Mapped[str] = mapped_column(String(16), primary_key=True)


class ChunkProfileRecord(CourseRAGBase):
    __tablename__ = "courserag_chunk_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    tokenizer_id: Mapped[str] = mapped_column(String(160), nullable=False)
    tokenizer_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChunkSetRecord(CourseRAGBase):
    __tablename__ = "courserag_chunk_sets"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ready','ready_with_warnings','failed')", name="chunk_set_status"
        ),
        UniqueConstraint(
            "parsed_document_id",
            "profile_id",
            "evidence_artifact_sha256",
            name="uq_courserag_chunk_set_identity",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    parsed_document_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_chunk_profiles.id", ondelete="RESTRICT"), index=True
    )
    evidence_artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ChunkRecord(CourseRAGBase):
    __tablename__ = "courserag_chunks"
    __table_args__ = (
        UniqueConstraint("index_version_id", "chunk_key", name="uq_courserag_chunk_key"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    index_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_index_versions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    chunk_set_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_chunk_sets.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    parent_chunk_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("courserag_chunks.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    document_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_document_versions.id", ondelete="CASCADE"), index=True
    )
    chunk_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warning_codes_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class ChunkEvidenceRecord(CourseRAGBase):
    __tablename__ = "courserag_chunk_evidence"

    chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_chunks.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    coverage_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
