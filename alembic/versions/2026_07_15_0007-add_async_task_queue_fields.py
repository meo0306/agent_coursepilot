"""add async task queue fields

Revision ID: 0007_add_async_task_queue_fields
Revises: 0006_create_idempotency_records
Create Date: 2026-07-15 00:07:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_add_async_task_queue_fields"
down_revision: str | None = "0006_create_idempotency_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "coursepilot_generation_tasks",
        sa.Column("result_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "coursepilot_generation_tasks",
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "coursepilot_generation_tasks",
        sa.Column("worker_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "coursepilot_generation_tasks",
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "coursepilot_generation_tasks",
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "coursepilot_generation_tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_coursepilot_generation_tasks_queue",
        "coursepilot_generation_tasks",
        ["status", "locked_until", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coursepilot_generation_tasks_queue",
        table_name="coursepilot_generation_tasks",
    )
    op.drop_column("coursepilot_generation_tasks", "completed_at")
    op.drop_column("coursepilot_generation_tasks", "started_at")
    op.drop_column("coursepilot_generation_tasks", "locked_until")
    op.drop_column("coursepilot_generation_tasks", "worker_id")
    op.drop_column("coursepilot_generation_tasks", "attempt_count")
    op.drop_column("coursepilot_generation_tasks", "result_json")
