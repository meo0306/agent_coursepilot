"""Add P10 incremental, citation migration, and verified overlay facts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_incremental_writeback_security"
down_revision: str | None = "0014_query_context_qa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[str]:
    return sa.Column("id", sa.String(36), nullable=False)


def upgrade() -> None:
    with op.batch_alter_table("courserag_document_versions") as batch:
        batch.add_column(sa.Column("previous_version_id", sa.String(36), nullable=True))
        batch.create_foreign_key(
            "fk_courserag_document_version_previous",
            "courserag_document_versions",
            ["previous_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_index(
            "ix_courserag_document_versions_previous_version_id", ["previous_version_id"]
        )

    op.create_table(
        "courserag_verified_index_versions",
        _id(),
        sa.Column("knowledge_base_id", sa.String(36), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="staging"),
        sa.Column("manifest_artifact_id", sa.String(36), nullable=True),
        sa.Column("manifest_sha256", sa.String(64), nullable=True),
        sa.Column("base_version_id", sa.String(36), nullable=True),
        sa.Column("active_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("validated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('staging','active','retired','failed')", name="verified_index_status"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["courserag_knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["manifest_artifact_id"], ["courserag_artifacts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["base_version_id"], ["courserag_verified_index_versions.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "knowledge_base_id", "version_number", name="uq_courserag_verified_index_version"
        ),
    )
    op.create_index(
        "ix_courserag_verified_index_versions_knowledge_base_id",
        "courserag_verified_index_versions",
        ["knowledge_base_id"],
    )
    with op.batch_alter_table("courserag_knowledge_bases") as batch:
        batch.add_column(
            sa.Column("active_verified_index_version_id", sa.String(36), nullable=True)
        )
        batch.create_foreign_key(
            "fk_courserag_kb_active_verified_index",
            "courserag_verified_index_versions",
            ["active_verified_index_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    op.create_table(
        "courserag_incremental_build_plans",
        _id(),
        sa.Column("knowledge_base_id", sa.String(36), nullable=False),
        sa.Column("source_version_id", sa.String(36), nullable=False),
        sa.Column("target_version_id", sa.String(36), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("plan_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planned"),
        sa.Column("change_coverage", sa.Float(), nullable=False),
        sa.Column("theoretical_reuse_ratio", sa.Float(), nullable=False),
        sa.Column("actual_reuse_ratio", sa.Float(), nullable=True),
        sa.Column("impact_summary_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('planned','running','succeeded','failed')", name="incremental_plan_status"
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["courserag_knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["courserag_document_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_version_id"], ["courserag_document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_sha256"),
        sa.UniqueConstraint(
            "source_version_id",
            "target_version_id",
            "profile_sha256",
            name="uq_courserag_incremental_plan",
        ),
    )
    op.create_index(
        "ix_courserag_incremental_build_plans_knowledge_base_id",
        "courserag_incremental_build_plans",
        ["knowledge_base_id"],
    )

    op.create_table(
        "courserag_section_impacts",
        _id(),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source_section_id", sa.String(36), nullable=True),
        sa.Column("target_section_id", sa.String(36), nullable=True),
        sa.Column("change_kind", sa.String(32), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("affected_artifacts_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("candidates_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["courserag_incremental_build_plans.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_section_id"], ["courserag_sections.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_section_id"], ["courserag_sections.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "ordinal", name="uq_courserag_section_impact"),
    )
    op.create_index(
        "ix_courserag_section_impacts_plan_id", "courserag_section_impacts", ["plan_id"]
    )

    op.create_table(
        "courserag_artifact_reuse_links",
        _id(),
        sa.Column("plan_id", sa.String(36), nullable=False),
        sa.Column("source_artifact_id", sa.String(36), nullable=False),
        sa.Column("target_artifact_id", sa.String(36), nullable=False),
        sa.Column("artifact_kind", sa.String(80), nullable=False),
        sa.Column("verified_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"], ["courserag_incremental_build_plans.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_artifact_id"], ["courserag_artifacts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_artifact_id"], ["courserag_artifacts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("plan_id", "target_artifact_id", name="uq_courserag_artifact_reuse"),
    )
    op.create_index(
        "ix_courserag_artifact_reuse_links_plan_id", "courserag_artifact_reuse_links", ["plan_id"]
    )

    op.create_table(
        "courserag_citation_migration_runs",
        _id(),
        sa.Column("source_version_id", sa.String(36), nullable=False),
        sa.Column("target_version_id", sa.String(36), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="running"),
        sa.Column("summary_json", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["courserag_document_versions.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_version_id"], ["courserag_document_versions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_version_id",
            "target_version_id",
            "profile_sha256",
            name="uq_courserag_citation_migration_run",
        ),
    )
    op.create_table(
        "courserag_citation_migration_items",
        _id(),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("source_evidence_id", sa.String(36), nullable=False),
        sa.Column("target_evidence_id", sa.String(36), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("method", sa.String(80), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("candidates_json", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("reviewed_by", sa.String(160), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["courserag_citation_migration_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_evidence_id"], ["courserag_evidence.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["target_evidence_id"], ["courserag_evidence.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id", "source_evidence_id", name="uq_courserag_citation_migration_item"
        ),
    )
    op.create_index(
        "ix_courserag_citation_migration_items_run_id",
        "courserag_citation_migration_items",
        ["run_id"],
    )

    with op.batch_alter_table("courserag_verified_content") as batch:
        for name, column_type in (
            ("content_sha256", sa.String(64)),
            ("version_sha256", sa.String(64)),
            ("request_sha256", sa.String(64)),
            ("approved_by", sa.String(160)),
            ("task_id", sa.String(160)),
            ("approval_record_id", sa.String(160)),
            ("current_overlay_version_id", sa.String(36)),
            ("revoked_by", sa.String(160)),
            ("revoke_idempotency_key", sa.String(255)),
            ("revoke_request_sha256", sa.String(64)),
        ):
            batch.add_column(sa.Column(name, column_type, nullable=True))
        batch.add_column(
            sa.Column(
                "source_tier", sa.String(32), nullable=False, server_default="teacher_verified"
            )
        )
        batch.add_column(
            sa.Column("retrieval_active", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("token_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("revoked_reason", sa.Text(), nullable=True))
        batch.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_index("ix_courserag_verified_content_content_sha256", ["content_sha256"])
        batch.create_foreign_key(
            "fk_courserag_verified_content_overlay",
            "courserag_verified_index_versions",
            ["current_overlay_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.execute("UPDATE courserag_verified_content SET status = 'legacy_incomplete'")

    with op.batch_alter_table("courserag_enrichment_batches") as batch:
        for name, column_type in (
            ("identity_sha256", sa.String(64)),
            ("trigger_reason", sa.String(32)),
            ("profile_sha256", sa.String(64)),
            ("request_sha256", sa.String(64)),
            ("worker_id", sa.String(160)),
        ):
            batch.add_column(sa.Column(name, column_type, nullable=True))
        batch.add_column(
            sa.Column("trigger_snapshot_json", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("usage_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("warnings_json", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_unique_constraint(
            "uq_courserag_enrichment_batch_identity", ["identity_sha256"]
        )

    with op.batch_alter_table("courserag_enrichment_batch_items") as batch:
        batch.add_column(
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("profile_sha256", sa.String(64), nullable=True))
        for name, default in (
            ("result_json", "{}"),
            ("knowledge_point_links_json", "[]"),
            ("usage_json", "{}"),
            ("warnings_json", "[]"),
        ):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=False, server_default=default))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("courserag_enrichment_batch_items") as batch:
        for column in (
            "completed_at",
            "warnings_json",
            "usage_json",
            "knowledge_point_links_json",
            "result_json",
            "profile_sha256",
            "attempt_count",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("courserag_enrichment_batches") as batch:
        batch.drop_constraint("uq_courserag_enrichment_batch_identity", type_="unique")
        for column in (
            "completed_at",
            "warnings_json",
            "usage_json",
            "attempt_count",
            "locked_until",
            "trigger_snapshot_json",
            "worker_id",
            "request_sha256",
            "profile_sha256",
            "trigger_reason",
            "identity_sha256",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("courserag_verified_content") as batch:
        batch.drop_constraint("fk_courserag_verified_content_overlay", type_="foreignkey")
        batch.drop_index("ix_courserag_verified_content_content_sha256")
        for column in (
            "revoked_at",
            "revoked_reason",
            "token_count",
            "retrieval_active",
            "source_tier",
            "revoke_request_sha256",
            "revoke_idempotency_key",
            "revoked_by",
            "current_overlay_version_id",
            "approval_record_id",
            "task_id",
            "approved_by",
            "request_sha256",
            "version_sha256",
            "content_sha256",
        ):
            batch.drop_column(column)
    op.drop_index(
        "ix_courserag_citation_migration_items_run_id",
        table_name="courserag_citation_migration_items",
    )
    op.drop_table("courserag_citation_migration_items")
    op.drop_table("courserag_citation_migration_runs")
    op.drop_index(
        "ix_courserag_artifact_reuse_links_plan_id", table_name="courserag_artifact_reuse_links"
    )
    op.drop_table("courserag_artifact_reuse_links")
    op.drop_index("ix_courserag_section_impacts_plan_id", table_name="courserag_section_impacts")
    op.drop_table("courserag_section_impacts")
    op.drop_index(
        "ix_courserag_incremental_build_plans_knowledge_base_id",
        table_name="courserag_incremental_build_plans",
    )
    op.drop_table("courserag_incremental_build_plans")
    with op.batch_alter_table("courserag_knowledge_bases") as batch:
        batch.drop_constraint("fk_courserag_kb_active_verified_index", type_="foreignkey")
        batch.drop_column("active_verified_index_version_id")
    op.drop_index(
        "ix_courserag_verified_index_versions_knowledge_base_id",
        table_name="courserag_verified_index_versions",
    )
    op.drop_table("courserag_verified_index_versions")
    with op.batch_alter_table("courserag_document_versions") as batch:
        batch.drop_index("ix_courserag_document_versions_previous_version_id")
        batch.drop_constraint("fk_courserag_document_version_previous", type_="foreignkey")
        batch.drop_column("previous_version_id")
