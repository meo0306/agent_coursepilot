"""Add P11 CoursePilot runtime, Artifact, Template and invocation facts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_coursepilot_runtime_foundation"
down_revision: str | None = "0015_incremental_writeback_security"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coursepilot_template_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("template_id", sa.String(160), nullable=False),
        sa.Column("template_version", sa.String(80), nullable=False),
        sa.Column("definition_sha256", sa.String(64), nullable=False),
        sa.Column("resource_hashes_json", sa.JSON(), nullable=False),
        sa.Column("prompt_hashes_json", sa.JSON(), nullable=False),
        sa.Column("model_profile_sha256", sa.String(64), nullable=False),
        sa.Column("schema_versions_json", sa.JSON(), nullable=False),
        sa.Column("validator_profile", sa.String(160), nullable=False),
        sa.Column("repair_profile", sa.String(160), nullable=False),
        sa.Column("exporter_profile", sa.String(160), nullable=False),
        sa.Column("user_overrides_json", sa.JSON(), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "coursepilot_workflow_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("run_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("graph_version", sa.String(100), nullable=False),
        sa.Column("template_snapshot_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(160), nullable=False),
        sa.Column("trace_id", sa.String(160), nullable=False),
        sa.Column("input_sha256", sa.String(64), nullable=False),
        sa.Column("context_refs_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["coursepilot_generation_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["template_snapshot_id"], ["coursepilot_template_snapshots.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("task_id", "run_number"),
    )
    with op.batch_alter_table("coursepilot_generation_tasks") as batch:
        batch.add_column(sa.Column("workflow_type", sa.String(32), nullable=True))
        batch.add_column(sa.Column("current_stage", sa.String(100), nullable=True))
        batch.add_column(sa.Column("thread_id", sa.String(255), nullable=True))
        batch.add_column(sa.Column("template_snapshot_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("active_run_id", sa.String(36), nullable=True))
        batch.add_column(
            sa.Column("input_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch.add_column(sa.Column("active_artifact_version", sa.Integer(), nullable=True))
        batch.create_unique_constraint("uq_coursepilot_generation_tasks_thread_id", ["thread_id"])
        batch.create_foreign_key(
            "fk_coursepilot_task_template_snapshot",
            "coursepilot_template_snapshots",
            ["template_snapshot_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_coursepilot_task_active_run",
            "coursepilot_workflow_runs",
            ["active_run_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_table(
        "coursepilot_artifacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("course_id", sa.String(36), nullable=False),
        sa.Column("artifact_type", sa.String(100), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["coursepilot_generation_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["course_id"], ["coursepilot_courses.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "coursepilot_artifact_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("artifact_id", sa.String(36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(100), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=True),
        sa.Column("storage_kind", sa.String(32), nullable=False),
        sa.Column("storage_uri", sa.Text(), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(160), nullable=False),
        sa.Column("source_run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["artifact_id"], ["coursepilot_artifacts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_run_id"], ["coursepilot_workflow_runs.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("artifact_id", "version"),
    )
    op.create_table(
        "coursepilot_node_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("node_name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_fingerprint", sa.String(64), nullable=False),
        sa.Column("output_artifact_refs_json", sa.JSON(), nullable=False),
        sa.Column("model_invocation_ids_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["coursepilot_workflow_runs.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "coursepilot_approval_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("artifact_version_id", sa.String(36), nullable=True),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer_id", sa.String(160), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("decision_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["task_id"], ["coursepilot_generation_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["coursepilot_artifact_versions.id"], ondelete="RESTRICT"
        ),
    )
    op.create_table(
        "coursepilot_model_invocations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("node_run_id", sa.String(36), nullable=True),
        sa.Column("requested_profile", sa.String(100), nullable=False),
        sa.Column("resolved_profile", sa.String(100), nullable=False),
        sa.Column("escalation_reason", sa.String(160), nullable=True),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("capability_sha256", sa.String(64), nullable=False),
        sa.Column("prompt_name", sa.String(255), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("request_sha256", sa.String(64), nullable=False),
        sa.Column("response_sha256", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_category", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("total_tokens", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("usage_known", sa.Boolean(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["coursepilot_workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_run_id"], ["coursepilot_node_runs.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("coursepilot_model_invocations")
    op.drop_table("coursepilot_approval_records")
    op.drop_table("coursepilot_node_runs")
    op.drop_table("coursepilot_artifact_versions")
    op.drop_table("coursepilot_artifacts")
    with op.batch_alter_table("coursepilot_generation_tasks") as batch:
        batch.drop_constraint("fk_coursepilot_task_active_run", type_="foreignkey")
        batch.drop_constraint("fk_coursepilot_task_template_snapshot", type_="foreignkey")
        batch.drop_constraint("uq_coursepilot_generation_tasks_thread_id", type_="unique")
        for column in (
            "active_artifact_version",
            "input_version",
            "active_run_id",
            "template_snapshot_id",
            "thread_id",
            "current_stage",
            "workflow_type",
        ):
            batch.drop_column(column)
    op.drop_table("coursepilot_workflow_runs")
    op.drop_table("coursepilot_template_snapshots")
