"""Add stable Evidence links and versioned parent-child Chunk Sets."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_stable_evidence_chunks"
down_revision: str | None = "0010_expand_ocr_results"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "courserag_evidence_block_links",
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("block_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("char_start", sa.Integer(), nullable=False),
        sa.Column("char_end", sa.Integer(), nullable=False),
        sa.Column("text_sha256", sa.String(64), nullable=False),
        sa.ForeignKeyConstraint(["evidence_id"], ["courserag_evidence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["block_id"], ["courserag_blocks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_id", "block_id"),
    )
    op.create_table(
        "courserag_evidence_page_bboxes",
        sa.Column("evidence_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("page_id", sa.String(36), nullable=False),
        sa.Column("bbox_json", sa.JSON(), nullable=False),
        sa.Column("coordinate_space", sa.String(80), nullable=False),
        sa.Column("physical_page_index", sa.Integer(), nullable=True),
        sa.Column("display_page_label", sa.String(64), nullable=True),
        sa.Column("page_width", sa.Float(), nullable=False),
        sa.Column("page_height", sa.Float(), nullable=False),
        sa.Column("source_region_id", sa.String(160), nullable=True),
        sa.ForeignKeyConstraint(["evidence_id"], ["courserag_evidence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["page_id"], ["courserag_pages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_id", "ordinal"),
    )
    op.create_table(
        "courserag_evidence_relations",
        sa.Column("source_evidence_id", sa.String(36), nullable=False),
        sa.Column("target_evidence_id", sa.String(36), nullable=False),
        sa.Column("relation_type", sa.String(16), nullable=False),
        sa.CheckConstraint("relation_type IN ('previous','next')", name="evidence_relation_type"),
        sa.ForeignKeyConstraint(
            ["source_evidence_id"], ["courserag_evidence.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_evidence_id"], ["courserag_evidence.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("source_evidence_id", "target_evidence_id", "relation_type"),
    )
    op.create_table(
        "courserag_chunk_profiles",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("version", sa.String(80), nullable=False),
        sa.Column("profile_sha256", sa.String(64), nullable=False),
        sa.Column("tokenizer_id", sa.String(160), nullable=False),
        sa.Column("tokenizer_sha256", sa.String(64), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_sha256"),
    )
    op.create_index(
        "ix_courserag_chunk_profiles_profile_sha256",
        "courserag_chunk_profiles",
        ["profile_sha256"],
    )
    op.create_table(
        "courserag_chunk_sets",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("parsed_document_id", sa.String(36), nullable=False),
        sa.Column("profile_id", sa.String(36), nullable=False),
        sa.Column("evidence_artifact_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('ready','ready_with_warnings','failed')", name="chunk_set_status"
        ),
        sa.ForeignKeyConstraint(
            ["parsed_document_id"], ["courserag_parsed_documents.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"], ["courserag_chunk_profiles.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "parsed_document_id",
            "profile_id",
            "evidence_artifact_sha256",
            name="uq_courserag_chunk_set_identity",
        ),
        sa.UniqueConstraint("content_sha256"),
    )
    op.create_index(
        "ix_courserag_chunk_sets_parsed_document_id",
        "courserag_chunk_sets",
        ["parsed_document_id"],
    )
    op.create_index("ix_courserag_chunk_sets_profile_id", "courserag_chunk_sets", ["profile_id"])
    op.create_index(
        "ix_courserag_chunk_sets_content_sha256",
        "courserag_chunk_sets",
        ["content_sha256"],
    )
    with op.batch_alter_table("courserag_chunks") as batch:
        batch.drop_constraint(
            "fk_courserag_chunks_index_version_id_courserag_index_versions",
            type_="foreignkey",
        )
        batch.alter_column("index_version_id", existing_type=sa.String(36), nullable=True)
        batch.add_column(sa.Column("chunk_set_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("parent_chunk_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("chunk_kind", sa.String(16), nullable=True))
        batch.add_column(sa.Column("token_count", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("profile_sha256", sa.String(64), nullable=True))
        batch.add_column(
            sa.Column("warning_codes_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch.create_foreign_key(
            "fk_courserag_chunks_index_version_id_courserag_index_versions",
            "courserag_index_versions",
            ["index_version_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_foreign_key(
            "fk_courserag_chunks_chunk_set_id_courserag_chunk_sets",
            "courserag_chunk_sets",
            ["chunk_set_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch.create_foreign_key(
            "fk_courserag_chunks_parent_chunk_id_courserag_chunks",
            "courserag_chunks",
            ["parent_chunk_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_check_constraint(
            "chunk_owner", "index_version_id IS NOT NULL OR chunk_set_id IS NOT NULL"
        )
        batch.create_check_constraint(
            "chunk_kind", "chunk_kind IS NULL OR chunk_kind IN ('parent','child')"
        )
        batch.create_unique_constraint("uq_courserag_chunk_set_key", ["chunk_set_id", "chunk_key"])
        batch.create_index("ix_courserag_chunks_chunk_set_id", ["chunk_set_id"])
        batch.create_index("ix_courserag_chunks_parent_chunk_id", ["parent_chunk_id"])
    with op.batch_alter_table("courserag_chunk_evidence") as batch:
        batch.add_column(sa.Column("ordinal", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("evidence_char_start", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("evidence_char_end", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("coverage_sha256", sa.String(64), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("courserag_chunk_evidence") as batch:
        for column in (
            "coverage_sha256",
            "evidence_char_end",
            "evidence_char_start",
            "ordinal",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("courserag_chunks") as batch:
        batch.drop_index("ix_courserag_chunks_parent_chunk_id")
        batch.drop_index("ix_courserag_chunks_chunk_set_id")
        batch.drop_constraint("uq_courserag_chunk_set_key", type_="unique")
        batch.drop_constraint("chunk_kind", type_="check")
        batch.drop_constraint("chunk_owner", type_="check")
        batch.drop_constraint(
            "fk_courserag_chunks_parent_chunk_id_courserag_chunks", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_courserag_chunks_chunk_set_id_courserag_chunk_sets", type_="foreignkey"
        )
        batch.drop_constraint(
            "fk_courserag_chunks_index_version_id_courserag_index_versions",
            type_="foreignkey",
        )
        for column in (
            "warning_codes_json",
            "profile_sha256",
            "token_count",
            "chunk_kind",
            "parent_chunk_id",
            "chunk_set_id",
        ):
            batch.drop_column(column)
        batch.alter_column("index_version_id", existing_type=sa.String(36), nullable=False)
        batch.create_foreign_key(
            "fk_courserag_chunks_index_version_id_courserag_index_versions",
            "courserag_index_versions",
            ["index_version_id"],
            ["id"],
            ondelete="CASCADE",
        )
    op.drop_index("ix_courserag_chunk_sets_content_sha256", table_name="courserag_chunk_sets")
    op.drop_index("ix_courserag_chunk_sets_profile_id", table_name="courserag_chunk_sets")
    op.drop_index("ix_courserag_chunk_sets_parsed_document_id", table_name="courserag_chunk_sets")
    op.drop_table("courserag_chunk_sets")
    op.drop_index(
        "ix_courserag_chunk_profiles_profile_sha256", table_name="courserag_chunk_profiles"
    )
    op.drop_table("courserag_chunk_profiles")
    op.drop_table("courserag_evidence_relations")
    op.drop_table("courserag_evidence_page_bboxes")
    op.drop_table("courserag_evidence_block_links")
