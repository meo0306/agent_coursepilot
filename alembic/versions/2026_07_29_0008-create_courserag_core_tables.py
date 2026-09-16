"""Create CourseRAG document, build, and versioned-index fact tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import MetaData, Table

from alembic import op

revision: str = "0008_courserag_core"
down_revision: str | None = "0007_add_async_task_queue_fields"
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


artifacts = Table(
    "courserag_artifacts",
    metadata,
    _id_column(),
    sa.Column("uri", sa.String(1024), nullable=False, unique=True),
    sa.Column("sha256", sa.String(64), nullable=False),
    sa.Column("size_bytes", sa.BigInteger(), nullable=False),
    sa.Column("media_type", sa.String(160), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_verified_at", sa.DateTime(timezone=True)),
    sa.Column("deleted_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "status IN ('available','quarantined','orphaned','deleted')",
        name="artifact_status",
    ),
)
sa.Index("ix_courserag_artifacts_sha256", artifacts.c.sha256, unique=True)

knowledge_bases = Table(
    "courserag_knowledge_bases",
    metadata,
    _id_column(),
    sa.Column("course_id", sa.String(160), nullable=False),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("description", sa.Text()),
    sa.Column("language", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("active_index_version_id", sa.String(36)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('empty','building','ready','ready_with_warnings','failed','archived')",
        name="knowledge_base_status",
    ),
)
sa.Index("ix_courserag_knowledge_bases_course_id", knowledge_bases.c.course_id, unique=True)

source_documents = Table(
    "courserag_source_documents",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("legacy_document_id", sa.String(160)),
    sa.Column("filename", sa.String(512), nullable=False),
    sa.Column("document_type", sa.String(16), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("current_version_id", sa.String(36)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("document_type IN ('pdf','docx')", name="source_document_type"),
    sa.CheckConstraint(
        "status IN ('registered','building','ready','failed','deleted')",
        name="source_document_status",
    ),
    sa.UniqueConstraint(
        "knowledge_base_id",
        "legacy_document_id",
        name="uq_courserag_source_documents_kb_legacy",
    ),
)
sa.Index(
    "ix_courserag_source_documents_knowledge_base_id",
    source_documents.c.knowledge_base_id,
)

document_versions = Table(
    "courserag_document_versions",
    metadata,
    _id_column(),
    sa.Column(
        "source_document_id",
        sa.String(36),
        sa.ForeignKey("courserag_source_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("version_number", sa.Integer(), nullable=False),
    sa.Column("content_sha256", sa.String(64), nullable=False),
    sa.Column("object_uri", sa.String(1024), nullable=False),
    sa.Column("mime_type", sa.String(160), nullable=False),
    sa.Column("size_bytes", sa.BigInteger(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("source_metadata_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('registered','building','ready','failed','superseded')",
        name="document_version_status",
    ),
    sa.UniqueConstraint(
        "source_document_id",
        "version_number",
        name="uq_courserag_document_versions_number",
    ),
    sa.UniqueConstraint(
        "source_document_id",
        "content_sha256",
        name="uq_courserag_document_versions_content",
    ),
)
sa.Index(
    "ix_courserag_document_versions_source_document_id",
    document_versions.c.source_document_id,
)
sa.Index(
    "ix_courserag_document_versions_content_sha256",
    document_versions.c.content_sha256,
)

source_documents.append_constraint(
    sa.ForeignKeyConstraint(
        [source_documents.c.current_version_id],
        [document_versions.c.id],
        name="fk_courserag_source_document_current_version",
        use_alter=True,
        ondelete="SET NULL",
    )
)

parsed_documents = Table(
    "courserag_parsed_documents",
    metadata,
    _id_column(),
    sa.Column(
        "document_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    sa.Column("parser_profile", sa.String(160), nullable=False),
    sa.Column("parser_version", sa.String(160), nullable=False),
    sa.Column(
        "artifact_id",
        sa.String(36),
        sa.ForeignKey("courserag_artifacts.id", ondelete="SET NULL"),
    ),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("warnings_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint(
        "status IN ('pending','running','ready','ready_with_warnings','failed')",
        name="parsed_document_status",
    ),
)

pages = Table(
    "courserag_pages",
    metadata,
    _id_column(),
    sa.Column(
        "parsed_document_id",
        sa.String(36),
        sa.ForeignKey("courserag_parsed_documents.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("page_index", sa.Integer(), nullable=False),
    sa.Column("display_page_label", sa.String(64)),
    sa.Column("width", sa.Float()),
    sa.Column("height", sa.Float()),
    sa.Column("source_mode", sa.String(32), nullable=False),
    sa.Column("content_sha256", sa.String(64)),
    sa.Column("metadata_json", sa.JSON(), nullable=False),
    sa.UniqueConstraint(
        "parsed_document_id",
        "page_index",
        name="uq_courserag_pages_document_index",
    ),
)
sa.Index("ix_courserag_pages_parsed_document_id", pages.c.parsed_document_id)

ocr_page_results = Table(
    "courserag_ocr_page_results",
    metadata,
    _id_column(),
    sa.Column(
        "page_id",
        sa.String(36),
        sa.ForeignKey("courserag_pages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    sa.Column(
        "artifact_id",
        sa.String(36),
        sa.ForeignKey("courserag_artifacts.id", ondelete="SET NULL"),
    ),
    sa.Column("engine", sa.String(160), nullable=False),
    sa.Column("engine_version", sa.String(160), nullable=False),
    sa.Column("image_sha256", sa.String(64), nullable=False),
    sa.Column("confidence", sa.Float()),
    sa.Column("warnings_json", sa.JSON(), nullable=False),
)

build_jobs = Table(
    "courserag_build_jobs",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("queue_task_id", sa.String(160), unique=True),
    sa.Column("request_hash", sa.String(64), nullable=False),
    sa.Column("build_mode", sa.String(32), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("force_rebuild", sa.Boolean(), nullable=False),
    sa.Column("retry_from_stage", sa.String(160)),
    sa.Column("target_index_version_id", sa.String(36)),
    sa.Column("attempt_count", sa.Integer(), nullable=False),
    sa.Column("worker_id", sa.String(160)),
    sa.Column("locked_until", sa.DateTime(timezone=True)),
    sa.Column("error_code", sa.String(160)),
    sa.Column("error_message", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "status IN ('queued','running','succeeded','failed','cancelled')",
        name="build_job_status",
    ),
    sa.UniqueConstraint(
        "knowledge_base_id",
        "request_hash",
        name="uq_courserag_build_jobs_request",
    ),
)
sa.Index("ix_courserag_build_jobs_knowledge_base_id", build_jobs.c.knowledge_base_id)
sa.Index(
    "ix_courserag_build_jobs_queue",
    build_jobs.c.status,
    build_jobs.c.locked_until,
    build_jobs.c.created_at,
)

build_job_document_versions = Table(
    "courserag_build_job_document_versions",
    metadata,
    sa.Column(
        "build_job_id",
        sa.String(36),
        sa.ForeignKey("courserag_build_jobs.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "document_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

build_stage_runs = Table(
    "courserag_build_stage_runs",
    metadata,
    _id_column(),
    sa.Column(
        "build_job_id",
        sa.String(36),
        sa.ForeignKey("courserag_build_jobs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("stage_name", sa.String(160), nullable=False),
    sa.Column("stage_version", sa.String(160), nullable=False),
    sa.Column("fingerprint", sa.String(64), nullable=False),
    sa.Column("attempt_number", sa.Integer(), nullable=False),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column("cache_hit", sa.Boolean(), nullable=False),
    sa.Column(
        "artifact_id",
        sa.String(36),
        sa.ForeignKey("courserag_artifacts.id", ondelete="SET NULL"),
    ),
    sa.Column("input_hashes_json", sa.JSON(), nullable=False),
    sa.Column("config_hash", sa.String(64), nullable=False),
    sa.Column("provider_metadata_json", sa.JSON(), nullable=False),
    sa.Column("counts_json", sa.JSON(), nullable=False),
    sa.Column("warnings_json", sa.JSON(), nullable=False),
    sa.Column("error_code", sa.String(160)),
    sa.Column("error_message", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "status IN ('queued','running','succeeded','failed','cached','skipped')",
        name="build_stage_status",
    ),
    sa.UniqueConstraint(
        "build_job_id",
        "stage_name",
        "attempt_number",
        name="uq_courserag_stage_job_name_attempt",
    ),
)
sa.Index(
    "ix_courserag_build_stage_runs_build_job_id",
    build_stage_runs.c.build_job_id,
)
sa.Index(
    "ix_courserag_stage_fingerprint_status",
    build_stage_runs.c.fingerprint,
    build_stage_runs.c.status,
)

index_versions = Table(
    "courserag_index_versions",
    metadata,
    _id_column(),
    sa.Column(
        "knowledge_base_id",
        sa.String(36),
        sa.ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "build_job_id",
        sa.String(36),
        sa.ForeignKey("courserag_build_jobs.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("version_number", sa.Integer(), nullable=False),
    sa.Column(
        "base_index_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_index_versions.id", ondelete="SET NULL"),
    ),
    sa.Column("status", sa.String(32), nullable=False),
    sa.Column(
        "dense_manifest_artifact_id",
        sa.String(36),
        sa.ForeignKey("courserag_artifacts.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "sparse_manifest_artifact_id",
        sa.String(36),
        sa.ForeignKey("courserag_artifacts.id", ondelete="SET NULL"),
    ),
    sa.Column(
        "overall_manifest_artifact_id",
        sa.String(36),
        sa.ForeignKey("courserag_artifacts.id", ondelete="SET NULL"),
    ),
    sa.Column("sparse_status", sa.String(32), nullable=False),
    sa.Column("manifest_sha256", sa.String(64)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("published_at", sa.DateTime(timezone=True)),
    sa.CheckConstraint(
        "status IN ('staging','validating','active','retired','failed')",
        name="index_version_status",
    ),
    sa.CheckConstraint(
        "sparse_status IN ('ready','not_materialized')",
        name="index_sparse_status",
    ),
    sa.UniqueConstraint(
        "knowledge_base_id",
        "version_number",
        name="uq_courserag_index_versions_number",
    ),
)
sa.Index("ix_courserag_index_versions_knowledge_base_id", index_versions.c.knowledge_base_id)
sa.Index(
    "uq_courserag_one_active_index",
    index_versions.c.knowledge_base_id,
    unique=True,
    postgresql_where=sa.text("status = 'active'"),
    sqlite_where=sa.text("status = 'active'"),
)

knowledge_bases.append_constraint(
    sa.ForeignKeyConstraint(
        [knowledge_bases.c.active_index_version_id],
        [index_versions.c.id],
        name="fk_courserag_kb_active_index_version",
        use_alter=True,
        ondelete="SET NULL",
    )
)
build_jobs.append_constraint(
    sa.ForeignKeyConstraint(
        [build_jobs.c.target_index_version_id],
        [index_versions.c.id],
        name="fk_courserag_build_job_target_index",
        use_alter=True,
        ondelete="SET NULL",
    )
)

index_document_versions = Table(
    "courserag_index_document_versions",
    metadata,
    sa.Column(
        "index_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_index_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column(
        "document_version_id",
        sa.String(36),
        sa.ForeignKey("courserag_document_versions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)

audit_events = Table(
    "courserag_audit_events",
    metadata,
    _id_column(),
    sa.Column("event_type", sa.String(160), nullable=False),
    sa.Column("scope_type", sa.String(80), nullable=False),
    sa.Column("scope_id", sa.String(160), nullable=False),
    sa.Column("actor_id", sa.String(160), nullable=False),
    sa.Column("details_json", sa.JSON(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
sa.Index(
    "ix_courserag_audit_scope",
    audit_events.c.scope_type,
    audit_events.c.scope_id,
    audit_events.c.created_at,
)

TABLES = (
    artifacts,
    knowledge_bases,
    source_documents,
    document_versions,
    parsed_documents,
    pages,
    ocr_page_results,
    build_jobs,
    build_job_document_versions,
    build_stage_runs,
    index_versions,
    index_document_versions,
    audit_events,
)


def upgrade() -> None:
    metadata.create_all(bind=op.get_bind(), tables=list(TABLES), checkfirst=False)


def downgrade() -> None:
    metadata.drop_all(bind=op.get_bind(), tables=list(TABLES), checkfirst=False)
