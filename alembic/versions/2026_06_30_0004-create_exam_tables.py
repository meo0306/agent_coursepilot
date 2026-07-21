"""create exam generation tables

Revision ID: 0004_create_exam_tables
Revises: 0003_create_lesson_tables
Create Date: 2026-06-30 00:04:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_create_exam_tables"
down_revision: str | None = "0003_create_lesson_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "coursepilot_exam_blueprints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("chapter_range", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("blueprint_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_exam_blueprints_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["task_id"],
            ["coursepilot_generation_tasks.id"],
            name=op.f("fk_coursepilot_exam_blueprints_task_id_coursepilot_generation_tasks"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_exam_blueprints")),
    )
    op.create_table(
        "coursepilot_questions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("exam_blueprint_id", sa.String(length=36), nullable=False),
        sa.Column("question_type", sa.String(length=50), nullable=False),
        sa.Column("knowledge_point", sa.String(length=255), nullable=False),
        sa.Column("difficulty", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options_json", sa.JSON(), nullable=True),
        sa.Column("correct_answer", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("references_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_questions_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["exam_blueprint_id"],
            ["coursepilot_exam_blueprints.id"],
            name=op.f("fk_coursepilot_questions_exam_blueprint_id_coursepilot_exam_blueprints"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_questions")),
    )
    op.create_index(
        "ix_coursepilot_questions_blueprint_type",
        "coursepilot_questions",
        ["exam_blueprint_id", "question_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_coursepilot_questions_blueprint_type", table_name="coursepilot_questions")
    op.drop_table("coursepilot_questions")
    op.drop_table("coursepilot_exam_blueprints")
