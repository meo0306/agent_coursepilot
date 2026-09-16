"""Add persistent, reviewable CourseRAG Knowledge Point assets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012_knowledge_point_assets"
down_revision: str | None = "0011_stable_evidence_chunks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courserag_kp_extraction_batches",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("knowledge_base_id", sa.String(36), nullable=False),
        sa.Column("build_job_id", sa.String(36), nullable=True),
        sa.Column("identity_sha256", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(160), nullable=False),
        sa.Column("model_name", sa.String(240), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("extractor_profile_sha256", sa.String(64), nullable=False),
        sa.Column("scoring_profile_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("window_count", sa.Integer(), nullable=False),
        sa.Column("provider_call_count", sa.Integer(), nullable=False),
        sa.Column("cache_hit_count", sa.Integer(), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("cost_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','partial','failed')",
            name="kp_extraction_batch_status",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"], ["courserag_knowledge_bases.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["build_job_id"], ["courserag_build_jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_base_id", "identity_sha256", name="uq_courserag_kp_batch"),
    )
    op.create_index(
        "ix_courserag_kp_extraction_batches_knowledge_base_id",
        "courserag_kp_extraction_batches",
        ["knowledge_base_id"],
    )
    op.create_index(
        "ix_courserag_kp_extraction_batches_build_job_id",
        "courserag_kp_extraction_batches",
        ["build_job_id"],
    )

    op.execute(
        sa.text(
            "UPDATE courserag_knowledge_points SET status='unreviewed' WHERE status='candidate'"
        )
    )
    with op.batch_alter_table("courserag_knowledge_points") as batch:
        batch.add_column(sa.Column("normalized_name", sa.String(240), nullable=True))
        batch.add_column(sa.Column("parent_knowledge_point_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("publish_score", sa.Float(), nullable=True))
        batch.add_column(
            sa.Column(
                "publish_score_components_json",
                sa.JSON(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.add_column(
            sa.Column("auto_published", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("origin", sa.String(80), nullable=False, server_default="legacy_placeholder")
        )
        batch.add_column(sa.Column("extractor_version", sa.String(160), nullable=True))
        batch.add_column(sa.Column("extractor_profile_sha256", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("version_number", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.create_foreign_key(
            "fk_courserag_kp_parent",
            "courserag_knowledge_points",
            ["parent_knowledge_point_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "knowledge_point_status",
            "status IN ('unreviewed','needs_review','approved','rejected','deprecated')",
        )
        batch.create_index(
            "ix_courserag_knowledge_points_parent_knowledge_point_id",
            ["parent_knowledge_point_id"],
        )
        batch.create_index(
            "ix_courserag_kp_status_score",
            ["knowledge_base_id", "status", "publish_score"],
        )
    op.create_table(
        "courserag_knowledge_point_aliases",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("knowledge_point_id", sa.String(36), nullable=False),
        sa.Column("alias", sa.String(240), nullable=False),
        sa.Column("normalized_alias", sa.String(240), nullable=False),
        sa.Column("basis", sa.String(80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_point_id"], ["courserag_knowledge_points.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("knowledge_point_id", "normalized_alias", name="uq_courserag_kp_alias"),
    )
    op.create_index(
        "ix_courserag_knowledge_point_aliases_knowledge_point_id",
        "courserag_knowledge_point_aliases",
        ["knowledge_point_id"],
    )

    op.create_table(
        "courserag_kp_windows",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=False),
        sa.Column("section_id", sa.String(36), nullable=False),
        sa.Column("window_key", sa.String(80), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("warning_codes_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id"], ["courserag_kp_extraction_batches.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["section_id"], ["courserag_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "window_key", name="uq_courserag_kp_window"),
    )
    op.create_index("ix_courserag_kp_windows_batch_id", "courserag_kp_windows", ["batch_id"])

    op.create_table(
        "courserag_kp_window_runs",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("window_id", sa.String(36), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("artifact_id", sa.String(36), nullable=True),
        sa.Column("provider", sa.String(160), nullable=False),
        sa.Column("model_name", sa.String(240), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("extractor_profile_sha256", sa.String(64), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("worker_id", sa.String(160), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(160), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed','cached')", name="kp_window_run_status"
        ),
        sa.ForeignKeyConstraint(["window_id"], ["courserag_kp_windows.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["artifact_id"], ["courserag_artifacts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("window_id", "attempt_number", name="uq_courserag_kp_window_attempt"),
    )
    op.create_index(
        "ix_courserag_kp_window_runs_window_id", "courserag_kp_window_runs", ["window_id"]
    )
    op.create_index(
        "ix_courserag_kp_window_cache",
        "courserag_kp_window_runs",
        ["cache_key", "status"],
    )

    with op.batch_alter_table("courserag_knowledge_point_evidence") as batch:
        batch.add_column(sa.Column("role", sa.String(32), nullable=False, server_default="summary"))
        batch.add_column(sa.Column("strength", sa.Float(), nullable=False, server_default="1"))
        batch.add_column(
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("extraction_batch_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("review_status", sa.String(32), nullable=False, server_default="unreviewed")
        )
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )
        batch.create_foreign_key(
            "fk_courserag_kp_evidence_batch",
            "courserag_kp_extraction_batches",
            ["extraction_batch_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("courserag_knowledge_point_chunks") as batch:
        batch.add_column(sa.Column("role", sa.String(32), nullable=False, server_default="summary"))
        batch.add_column(sa.Column("strength", sa.Float(), nullable=False, server_default="1"))
        batch.add_column(
            sa.Column("use_for_filtering", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(
            sa.Column("use_for_ranking", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch.add_column(sa.Column("derivation_sha256", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("CURRENT_TIMESTAMP"),
            )
        )

    with op.batch_alter_table("courserag_knowledge_point_reviews") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))
        batch.add_column(sa.Column("request_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("before_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("after_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(
            sa.Column(
                "related_knowledge_point_ids_json", sa.JSON(), nullable=False, server_default="[]"
            )
        )
        batch.add_column(sa.Column("response_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("resulting_version_number", sa.Integer(), nullable=True))
        batch.create_unique_constraint(
            "uq_courserag_kp_review_request", ["action", "idempotency_key"]
        )


def downgrade() -> None:
    with op.batch_alter_table("courserag_knowledge_point_reviews") as batch:
        batch.drop_constraint("uq_courserag_kp_review_request", type_="unique")
        for column in (
            "resulting_version_number",
            "response_json",
            "related_knowledge_point_ids_json",
            "after_json",
            "before_json",
            "request_sha256",
            "idempotency_key",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("courserag_knowledge_point_chunks") as batch:
        for column in (
            "created_at",
            "derivation_sha256",
            "use_for_ranking",
            "use_for_filtering",
            "strength",
            "role",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("courserag_knowledge_point_evidence") as batch:
        batch.drop_constraint("fk_courserag_kp_evidence_batch", type_="foreignkey")
        for column in (
            "created_at",
            "review_status",
            "extraction_batch_id",
            "is_primary",
            "strength",
            "role",
        ):
            batch.drop_column(column)
    op.drop_index("ix_courserag_kp_window_cache", table_name="courserag_kp_window_runs")
    op.drop_index("ix_courserag_kp_window_runs_window_id", table_name="courserag_kp_window_runs")
    op.drop_table("courserag_kp_window_runs")
    op.drop_index("ix_courserag_kp_windows_batch_id", table_name="courserag_kp_windows")
    op.drop_table("courserag_kp_windows")
    op.drop_index(
        "ix_courserag_knowledge_point_aliases_knowledge_point_id",
        table_name="courserag_knowledge_point_aliases",
    )
    op.drop_table("courserag_knowledge_point_aliases")
    with op.batch_alter_table("courserag_knowledge_points") as batch:
        batch.drop_index("ix_courserag_kp_status_score")
        batch.drop_index("ix_courserag_knowledge_points_parent_knowledge_point_id")
        batch.drop_constraint("knowledge_point_status", type_="check")
        batch.drop_constraint("fk_courserag_kp_parent", type_="foreignkey")
        for column in (
            "updated_at",
            "version_number",
            "extractor_profile_sha256",
            "extractor_version",
            "origin",
            "auto_published",
            "publish_score_components_json",
            "publish_score",
            "parent_knowledge_point_id",
            "normalized_name",
        ):
            batch.drop_column(column)
    op.execute(
        sa.text(
            "UPDATE courserag_knowledge_points SET status='candidate' WHERE status='unreviewed'"
        )
    )
    op.drop_index(
        "ix_courserag_kp_extraction_batches_build_job_id",
        table_name="courserag_kp_extraction_batches",
    )
    op.drop_index(
        "ix_courserag_kp_extraction_batches_knowledge_base_id",
        table_name="courserag_kp_extraction_batches",
    )
    op.drop_table("courserag_kp_extraction_batches")
