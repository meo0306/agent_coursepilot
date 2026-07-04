"""create lesson generation tables

Revision ID: 0003_create_lesson_tables
Revises: 0002_create_phase1_tables
Create Date: 2026-06-22 00:03:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_create_lesson_tables"
down_revision: str | None = "0002_create_phase1_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coursepilot_generation_tasks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_params_json", sa.JSON(), nullable=False),
        sa.Column("intermediate_outputs_json", sa.JSON(), nullable=False),
        sa.Column("validation_report_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_generation_tasks_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_generation_tasks")),
    )
    op.create_table(
        "coursepilot_lesson_designs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("chapter", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("total_sessions", sa.Integer(), nullable=False),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("validation_report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_lesson_designs_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["coursepilot_generation_tasks.id"],
            name=op.f("fk_coursepilot_lesson_designs_task_id_coursepilot_generation_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_lesson_designs")),
    )
    op.create_table(
        "coursepilot_export_files",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=True),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_role", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_export_files_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["coursepilot_generation_tasks.id"],
            name=op.f("fk_coursepilot_export_files_task_id_coursepilot_generation_tasks"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_export_files")),
    )


def downgrade() -> None:
    op.drop_table("coursepilot_export_files")
    op.drop_table("coursepilot_lesson_designs")
    op.drop_table("coursepilot_generation_tasks")

