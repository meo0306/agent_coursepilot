"""create ppt and review tables

Revision ID: 0005_create_ppt_review_tables
Revises: 0004_create_exam_tables
Create Date: 2026-07-02 00:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_create_ppt_review_tables"
down_revision: str | None = "0004_create_exam_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coursepilot_slide_outlines",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("lesson_design_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("outline_json", sa.JSON(), nullable=False),
        sa.Column("validation_report_json", sa.JSON(), nullable=False),
        sa.Column("pptx_file_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_slide_outlines_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lesson_design_id"],
            ["coursepilot_lesson_designs.id"],
            name=op.f("fk_coursepilot_slide_outlines_lesson_design_id_coursepilot_lesson_designs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["pptx_file_id"],
            ["coursepilot_export_files.id"],
            name=op.f("fk_coursepilot_slide_outlines_pptx_file_id_coursepilot_export_files"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["coursepilot_generation_tasks.id"],
            name=op.f("fk_coursepilot_slide_outlines_task_id_coursepilot_generation_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_slide_outlines")),
    )
    op.create_table(
        "coursepilot_review_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.String(length=36), nullable=False),
        sa.Column("review_status", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("write_back_status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_review_records_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_review_records")),
    )
    op.create_index(
        "ix_coursepilot_review_records_target",
        "coursepilot_review_records",
        ["target_type", "target_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_coursepilot_review_records_target", table_name="coursepilot_review_records")
    op.drop_table("coursepilot_review_records")
    op.drop_table("coursepilot_slide_outlines")
