"""create idempotency records

Revision ID: 0006_create_idempotency_records
Revises: 0005_create_ppt_review_tables
Create Date: 2026-07-15 00:06:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_create_idempotency_records"
down_revision: str | None = "0005_create_ppt_review_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coursepilot_idempotency_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("operation", sa.String(length=100), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_json", sa.JSON(), nullable=True),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_idempotency_records")),
        sa.UniqueConstraint(
            "operation",
            "idempotency_key",
            name="uq_coursepilot_idempotency_operation_key",
        ),
    )


def downgrade() -> None:
    op.drop_table("coursepilot_idempotency_records")
