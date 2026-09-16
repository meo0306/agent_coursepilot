"""Add recoverable workflow interrupts, resume commands and side effects."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_coursepilot_checkpoint_interrupts"
down_revision: str | None = "0016_coursepilot_runtime_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("coursepilot_generation_tasks") as batch:
        batch.add_column(
            sa.Column("workflow_mode", sa.String(32), nullable=False, server_default="legacy")
        )
        batch.add_column(sa.Column("active_interrupt_id", sa.String(36), nullable=True))
    with op.batch_alter_table("coursepilot_approval_records") as batch:
        batch.add_column(sa.Column("interrupt_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("checkpoint_id", sa.String(255), nullable=True))
        batch.add_column(sa.Column("decision_id", sa.String(160), nullable=True))
        batch.add_column(sa.Column("scope", sa.String(64), nullable=True))
        batch.add_column(sa.Column("action", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("target_paths_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.add_column(sa.Column("idempotency_key", sa.String(255), nullable=True))
        batch.add_column(sa.Column("request_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("superseded_by_id", sa.String(36), nullable=True))

    op.create_table(
        "coursepilot_interrupts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("interrupt_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("checkpoint_id", sa.String(255), nullable=False),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("artifact_version_id", sa.String(36), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("context_identity_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("superseded_by_id", sa.String(36), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["coursepilot_generation_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["coursepilot_artifact_versions.id"], ondelete="RESTRICT"
        ),
    )
    op.create_table(
        "coursepilot_resume_commands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("interrupt_id", sa.String(36), nullable=False),
        sa.Column("decision_id", sa.String(160), nullable=False, unique=True),
        sa.Column("thread_id", sa.String(255), nullable=False),
        sa.Column("command_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_category", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["coursepilot_generation_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["interrupt_id"], ["coursepilot_interrupts.id"], ondelete="RESTRICT"
        ),
    )
    op.create_table(
        "coursepilot_side_effect_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("artifact_version_id", sa.String(36), nullable=False),
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("operation_key", sa.String(255), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_category", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["task_id"], ["coursepilot_generation_tasks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["artifact_version_id"], ["coursepilot_artifact_versions.id"], ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("task_id", "artifact_version_id", "scope", "operation_key"),
    )


def downgrade() -> None:
    op.drop_table("coursepilot_side_effect_runs")
    op.drop_table("coursepilot_resume_commands")
    op.drop_table("coursepilot_interrupts")
    with op.batch_alter_table("coursepilot_approval_records") as batch:
        for column in (
            "superseded_by_id",
            "expires_at",
            "request_sha256",
            "idempotency_key",
            "target_paths_json",
            "action",
            "scope",
            "decision_id",
            "checkpoint_id",
            "interrupt_id",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("coursepilot_generation_tasks") as batch:
        batch.drop_column("active_interrupt_id")
        batch.drop_column("workflow_mode")
