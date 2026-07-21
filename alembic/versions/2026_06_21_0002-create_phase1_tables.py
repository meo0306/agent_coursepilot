"""create Phase 1 CoursePilot tables

Revision ID: 0002_create_phase1_tables
Revises: 0001_initial_coursepilot_base
Create Date: 2026-06-21 00:02:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_create_phase1_tables"
down_revision: str | None = "0001_initial_coursepilot_base"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 更新
def upgrade() -> None:
    op.create_table(
        "coursepilot_courses",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_name", sa.String(length=255), nullable=False),
        sa.Column("course_type", sa.String(length=100), nullable=True),
        sa.Column("student_level", sa.String(length=100), nullable=True),
        sa.Column("student_background", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_courses")),
    )
    op.create_table(
        "coursepilot_documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("parse_status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_documents_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_documents")),
    )
    op.create_table(
        "coursepilot_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("course_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=100), nullable=False),
        sa.Column("chapter", sa.String(length=255), nullable=True),
        sa.Column("section", sa.String(length=255), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=512), nullable=True),
        sa.Column("content_preview", sa.Text(), nullable=False),
        sa.Column("knowledge_points_json", sa.JSON(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False),
        sa.Column("chroma_collection", sa.String(length=255), nullable=False),
        sa.Column("chroma_doc_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["coursepilot_courses.id"],
            name=op.f("fk_coursepilot_chunks_course_id_coursepilot_courses"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["coursepilot_documents.id"],
            name=op.f("fk_coursepilot_chunks_document_id_coursepilot_documents"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_coursepilot_chunks")),
    )
    op.create_index(
        "ix_coursepilot_chunks_course_filters",
        "coursepilot_chunks",
        ["course_id", "source_type", "chapter", "verified"],
    )


def downgrade() -> None:
    op.drop_index("ix_coursepilot_chunks_course_filters", table_name="coursepilot_chunks")
    op.drop_table("coursepilot_chunks")
    op.drop_table("coursepilot_documents")
    op.drop_table("coursepilot_courses")
