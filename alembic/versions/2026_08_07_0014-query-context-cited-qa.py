"""Add P09 query, context package, and cited QA run persistence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0014_query_context_qa"
down_revision: str | None = "0013_hybrid_retrieval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("courserag_query_processing_runs") as batch:
        batch.add_column(
            sa.Column("status", sa.String(32), nullable=False, server_default="succeeded")
        )
        batch.add_column(sa.Column("raw_query", sa.Text(), nullable=True))
        batch.add_column(sa.Column("current_query", sa.Text(), nullable=True))
        batch.add_column(sa.Column("config_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("profile_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("output_sha256", sa.String(64), nullable=True))
        for name, default in (
            ("step_trace_json", "[]"),
            ("filters_json", "{}"),
            ("knowledge_points_json", "[]"),
            ("expansions_json", "[]"),
            ("routes_json", "{}"),
            ("warnings_json", "[]"),
            ("usage_json", "{}"),
        ):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=False, server_default=default))
        batch.add_column(sa.Column("provider", sa.String(80), nullable=True))
        batch.add_column(sa.Column("model_name", sa.String(240), nullable=True))
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "courserag_context_packages",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("query_run_id", sa.String(36), nullable=False),
        sa.Column("retrieval_run_id", sa.String(36), nullable=False),
        sa.Column("index_version_id", sa.String(36), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("result_sha256", sa.String(64), nullable=True),
        sa.Column("items_json", sa.JSON(), nullable=False),
        sa.Column("citation_map_json", sa.JSON(), nullable=False),
        sa.Column("packing_report_json", sa.JSON(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('running','succeeded','failed')", name="context_package_status"
        ),
        sa.ForeignKeyConstraint(
            ["query_run_id"], ["courserag_query_processing_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["retrieval_run_id"], ["courserag_retrieval_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["courserag_index_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("query_run_id", "retrieval_run_id", "index_version_id"):
        op.create_index(
            f"ix_courserag_context_packages_{column}", "courserag_context_packages", [column]
        )

    with op.batch_alter_table("courserag_qa_runs") as batch:
        batch.add_column(sa.Column("context_package_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("question", sa.Text(), nullable=True))
        batch.add_column(sa.Column("answer_status", sa.String(64), nullable=True))
        batch.add_column(sa.Column("abstention_reason", sa.String(160), nullable=True))
        batch.add_column(sa.Column("provider", sa.String(80), nullable=True))
        batch.add_column(sa.Column("model_name", sa.String(240), nullable=True))
        for name in ("prompt_sha256", "profile_sha256", "request_sha256", "result_sha256"):
            batch.add_column(sa.Column(name, sa.String(64), nullable=True))
        for name, default in (
            ("structured_output_json", "{}"),
            ("usage_json", "{}"),
            ("cost_json", "{}"),
            ("warnings_json", "[]"),
        ):
            batch.add_column(sa.Column(name, sa.JSON(), nullable=False, server_default=default))
        batch.add_column(
            sa.Column("repair_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_foreign_key(
            "fk_courserag_qa_context",
            "courserag_context_packages",
            ["context_package_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("courserag_answer_claims") as batch:
        batch.add_column(sa.Column("external_claim_id", sa.String(160), nullable=True))
        batch.add_column(sa.Column("validation_status", sa.String(32), nullable=True))
        batch.create_unique_constraint("uq_courserag_answer_claim_external", ["external_claim_id"])


def downgrade() -> None:
    with op.batch_alter_table("courserag_answer_claims") as batch:
        batch.drop_constraint("uq_courserag_answer_claim_external", type_="unique")
        batch.drop_column("validation_status")
        batch.drop_column("external_claim_id")
    with op.batch_alter_table("courserag_qa_runs") as batch:
        batch.drop_constraint("fk_courserag_qa_context", type_="foreignkey")
        for column in (
            "completed_at",
            "duration_ms",
            "warnings_json",
            "repair_count",
            "cost_json",
            "usage_json",
            "structured_output_json",
            "result_sha256",
            "request_sha256",
            "profile_sha256",
            "prompt_sha256",
            "model_name",
            "provider",
            "abstention_reason",
            "answer_status",
            "question",
            "context_package_id",
        ):
            batch.drop_column(column)
    for column in ("index_version_id", "retrieval_run_id", "query_run_id"):
        op.drop_index(
            f"ix_courserag_context_packages_{column}", table_name="courserag_context_packages"
        )
    op.drop_table("courserag_context_packages")
    with op.batch_alter_table("courserag_query_processing_runs") as batch:
        for column in (
            "completed_at",
            "duration_ms",
            "model_name",
            "provider",
            "usage_json",
            "warnings_json",
            "routes_json",
            "expansions_json",
            "knowledge_points_json",
            "filters_json",
            "step_trace_json",
            "output_sha256",
            "profile_sha256",
            "config_sha256",
            "current_query",
            "raw_query",
            "status",
        ):
            batch.drop_column(column)
