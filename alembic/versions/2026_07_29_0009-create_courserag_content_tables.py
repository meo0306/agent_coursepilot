"""Create CourseRAG content, knowledge, writeback, and run fact tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import MetaData, Table

from alembic import op

revision: str = "0009_courserag_content"
down_revision: str | None = "0008_courserag_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=NAMING_CONVENTION)


def _id_column() -> sa.Column[str]:
    return sa.Column("id", sa.String(36), primary_key=True)


def _core_table(name: str) -> Table:
    return Table(name, metadata, _id_column())


# Revision 0009 creates only CONTENT_TABLES. These immutable stubs let
# SQLAlchemy resolve foreign keys to tables already created by revision 0008.
knowledge_bases = _core_table("courserag_knowledge_bases")
parsed_documents = _core_table("courserag_parsed_documents")
pages = _core_table("courserag_pages")
document_versions = _core_table("courserag_document_versions")
index_versions = _core_table("courserag_index_versions")

sections = Table(
    "courserag_sections",
    metadata,
    _id_column(),
    sa.Column(
        "parsed_document_id",
        sa.String(36),
        sa.ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("parent_section_id", sa.String(36)),
    sa.Column("stable_path", sa.String(1024), nullable=False),
    sa.Column("heading", sa.Text()),
    sa.Column("level", sa.Integer(), nullable=False),
    sa.Column("ordinal", sa.Integer(), nullable=False),
    sa.Column("metadata_json", sa.JSON(), nullable=False),
    sa.UniqueConstraint(
        "parsed_document_id",
        "stable_path",
        name="uq_courserag_section_path",
    ),
)
sections.append_constraint(
    sa.ForeignKeyConstraint(
        [sections.c.parent_section_id],
        [sections.c.id],
        ondelete="CASCADE",
    )
)
sa.Index("ix_courserag_sections_parsed_document_id", sections.c.parsed_document_id)

blocks = Table(
    "courserag_blocks",
    metadata,
    _id_column(),
    sa.Column(
        "parsed_document_id",
        sa.String(36),
        sa.ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "section_id",
        sa.String(36),
        sa.ForeignKey("courserag_sections.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "page_id",
        sa.String(36),
        sa.ForeignKey("courserag_pages.id", ondelete="SET NULL"),
    ),
    sa.Column("stable_path", sa.String(1024), nullable=False),
    sa.Column("block_type", sa.String(80), nullable=False),
    sa.Column("ordinal", sa.Integer(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("metadata_json", sa.JSON(), nullable=False),
    sa.UniqueConstraint(
        "parsed_document_id",
        "stable_path",
        name="uq_courserag_block_path",
    ),
)
sa.Index("ix_courserag_blocks_parsed_document_id", blocks.c.parsed_document_id)
sa.Index("ix_courserag_blocks_content_sha256", blocks.c.content_sha256)

evidence = Table(
    "courserag_evidence",
    metadata,
    _id_column(),
    sa.Column(
        "parsed_document_id",
        sa.String(36),
        sa.ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "block_id",
        sa.String(36),
        sa.ForeignKey("courserag_blocks.id", ondelete="SET NULL"),
    ),
    sa.Column("stable_key", sa.String(1024), nullable=False),
    sa.Column("evidence_type", sa.String(80), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("char_start", sa.Integer()),
    sa.Column("char_end", sa.Integer()),
    sa.Column("confidence", sa.Float()),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("metadata_json", sa.JSON(), nullable=False),
    sa.UniqueConstraint(
        "parsed_document_id",
        "stable_key",
        name="uq_courserag_evidence_key",
    ),
)
sa.Index("ix_courserag_evidence_parsed_document_id", evidence.c.parsed_document_id)
sa.Index("ix_courserag_evidence_content_sha256", evidence.c.content_sha256)

chunks = Table(
    "courserag_chunks",
    metadata,
    _id_column(),
    sa.Column(
        "index_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_index_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "document_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("chunk_key", sa.String(1024), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("ordinal", sa.Integer(), nullable=False),
    sa.Column("metadata_json", sa.JSON(), nullable=False),
    sa.UniqueConstraint(
        "index_version_id",
        "chunk_key",
        name="uq_courserag_chunk_key",
    ),
)
sa.Index("ix_courserag_chunks_index_version_id", chunks.c.index_version_id)
sa.Index("ix_courserag_chunks_document_version_id", chunks.c.document_version_id)
sa.Index("ix_courserag_chunks_content_sha256", chunks.c.content_sha256)

chunk_evidence = Table(
    "courserag_chunk_evidence",
    metadata,
    sa.Column(
        "chunk_id",
        sa.String(36),
        sa.ForeignKey("courserag_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.String(36),
        sa.ForeignKey("courserag_evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

knowledge_points = Table(
    "courserag_knowledge_points",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("stable_key", sa.String(512), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("description", sa.Text()),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("metadata_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "knowledge_base_id",
        "stable_key",
        name="uq_courserag_kp_key",
    ),
)
sa.Index(
    "ix_courserag_knowledge_points_knowledge_base_id",
    knowledge_points.c.knowledge_base_id,
)

knowledge_point_evidence = Table(
    "courserag_knowledge_point_evidence",
    metadata,
    sa.Column(
        "knowledge_point_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.String(36),
        sa.ForeignKey("courserag_evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

knowledge_point_chunks = Table(
    "courserag_knowledge_point_chunks",
    metadata,
    sa.Column(
        "knowledge_point_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "chunk_id",
        sa.String(36),
        sa.ForeignKey("courserag_chunks.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

knowledge_point_reviews = Table(
    "courserag_knowledge_point_reviews",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_point_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("reviewer_id", sa.String(160), nullable=False),
    sa.Column("action", sa.String(32), nullable=False),
    sa.Column("comment", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sa.Index(
    "ix_courserag_knowledge_point_reviews_knowledge_point_id",
    knowledge_point_reviews.c.knowledge_point_id,
)

verified_content = Table(
    "courserag_verified_content",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("idempotency_key", sa.String(160), nullable=False),
    sa.Column("content_type", sa.String(80), nullable=False),
    sa.Column("title", sa.Text(), nullable=False),
    sa.Column("body", sa.Text(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("source_metadata_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint(
        "knowledge_base_id",
        "idempotency_key",
        name="uq_courserag_verified_key",
    ),
)
sa.Index(
    "ix_courserag_verified_content_knowledge_base_id",
    verified_content.c.knowledge_base_id,
)

verified_content_evidence = Table(
    "courserag_verified_content_evidence",
    metadata,
    sa.Column(
        "verified_content_id",
        sa.String(36),
        sa.ForeignKey("courserag_verified_content.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.String(36),
        sa.ForeignKey("courserag_evidence.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

verified_content_knowledge_points = Table(
    "courserag_verified_content_knowledge_points",
    metadata,
    sa.Column(
        "verified_content_id",
        sa.String(36),
        sa.ForeignKey("courserag_verified_content.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "knowledge_point_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_points.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

enrichment_batches = Table(
    "courserag_enrichment_batches",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("actor_id", sa.String(160), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sa.Index(
    "ix_courserag_enrichment_batches_knowledge_base_id",
    enrichment_batches.c.knowledge_base_id,
)

enrichment_batch_items = Table(
    "courserag_enrichment_batch_items",
    metadata,
    _id_column(),
    sa.Column(
        "batch_id",
        sa.String(36),
        sa.ForeignKey("courserag_enrichment_batches.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "verified_content_id",
        sa.String(36),
        sa.ForeignKey("courserag_verified_content.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("action", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("error_message", sa.Text()),
)
sa.Index(
    "ix_courserag_enrichment_batch_items_batch_id",
    enrichment_batch_items.c.batch_id,
)

query_processing_runs = Table(
    "courserag_query_processing_runs",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("request_id", sa.String(160), nullable=False),
    sa.Column("trace_id", sa.String(160), nullable=False),
    sa.Column("input_sha256", sa.String(64), nullable=False),
    sa.Column("output_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sa.Index(
    "ix_courserag_query_processing_runs_knowledge_base_id",
    query_processing_runs.c.knowledge_base_id,
)
sa.Index("ix_courserag_query_processing_runs_request_id", query_processing_runs.c.request_id)
sa.Index("ix_courserag_query_processing_runs_trace_id", query_processing_runs.c.trace_id)

retrieval_runs = Table(
    "courserag_retrieval_runs",
    metadata,
    _id_column(),
    sa.Column(
        "query_run_id",
        sa.String(36),
        sa.ForeignKey("courserag_query_processing_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "index_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_index_versions.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    sa.Column("retrieval_mode", sa.String(32), nullable=False),
    sa.Column("top_k", sa.Integer(), nullable=False),
    sa.Column("result_json", sa.JSON(), nullable=False),
    sa.Column("latency_ms", sa.Float()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sa.Index("ix_courserag_retrieval_runs_query_run_id", retrieval_runs.c.query_run_id)
sa.Index("ix_courserag_retrieval_runs_index_version_id", retrieval_runs.c.index_version_id)

qa_runs = Table(
    "courserag_qa_runs",
    metadata,
    _id_column(),
    sa.Column(
        "retrieval_run_id",
        sa.String(36),
        sa.ForeignKey("courserag_retrieval_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("answer_text", sa.Text(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("validation_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sa.Index("ix_courserag_qa_runs_retrieval_run_id", qa_runs.c.retrieval_run_id)

answer_claims = Table(
    "courserag_answer_claims",
    metadata,
    _id_column(),
    sa.Column(
        "qa_run_id",
        sa.String(36),
        sa.ForeignKey("courserag_qa_runs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("claim_index", sa.Integer(), nullable=False),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
)
sa.Index("ix_courserag_answer_claims_qa_run_id", answer_claims.c.qa_run_id)

answer_claim_evidence = Table(
    "courserag_answer_claim_evidence",
    metadata,
    sa.Column(
        "claim_id",
        sa.String(36),
        sa.ForeignKey("courserag_answer_claims.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "evidence_id",
        sa.String(36),
        sa.ForeignKey("courserag_evidence.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
)

CONTENT_TABLES = (
    sections,
    blocks,
    evidence,
    chunks,
    chunk_evidence,
    knowledge_points,
    knowledge_point_evidence,
    knowledge_point_chunks,
    knowledge_point_reviews,
    verified_content,
    verified_content_evidence,
    verified_content_knowledge_points,
    enrichment_batches,
    enrichment_batch_items,
    query_processing_runs,
    retrieval_runs,
    qa_runs,
    answer_claims,
    answer_claim_evidence,
)


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), tables=list(CONTENT_TABLES), checkfirst=False)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), tables=list(CONTENT_TABLES), checkfirst=False)
