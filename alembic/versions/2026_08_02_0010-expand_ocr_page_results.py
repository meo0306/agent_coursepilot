"""Expand OCR page results for provider identity, coordinates, and resource evidence."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_expand_ocr_results"
down_revision: str | None = "0009_courserag_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "courserag_ocr_page_results"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.add_column(
            sa.Column(
                "status",
                sa.String(32),
                nullable=False,
                server_default="legacy_incomplete",
            )
        )
        batch.add_column(sa.Column("model_name", sa.String(240), nullable=True))
        batch.add_column(sa.Column("model_manifest_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("profile_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("dpi", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("image_width", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("image_height", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("text_content", sa.Text(), nullable=True))
        batch.add_column(sa.Column("regions_json", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("result_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("peak_memory_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=True,
                server_default=sa.func.now(),
            )
        )
        batch.create_check_constraint(
            "ocr_page_result_status",
            "status IN ('legacy_incomplete','ready','ready_with_warnings','failed')",
        )
        batch.create_check_constraint(
            "ocr_page_result_complete",
            "status NOT IN ('ready','ready_with_warnings') OR ("
            "model_name IS NOT NULL AND model_manifest_sha256 IS NOT NULL AND "
            "profile_sha256 IS NOT NULL AND dpi IS NOT NULL AND image_width IS NOT NULL AND "
            "image_height IS NOT NULL AND text_content IS NOT NULL AND regions_json IS NOT NULL "
            "AND result_sha256 IS NOT NULL AND duration_ms IS NOT NULL AND "
            "peak_memory_bytes IS NOT NULL AND created_at IS NOT NULL)",
        )
        batch.create_index("ix_courserag_ocr_page_results_result_sha256", ["result_sha256"])


def downgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_index("ix_courserag_ocr_page_results_result_sha256")
        batch.drop_constraint("ocr_page_result_complete", type_="check")
        batch.drop_constraint("ocr_page_result_status", type_="check")
        for column in (
            "created_at",
            "peak_memory_bytes",
            "duration_ms",
            "result_sha256",
            "regions_json",
            "text_content",
            "image_height",
            "image_width",
            "dpi",
            "profile_sha256",
            "model_manifest_sha256",
            "model_name",
            "status",
        ):
            batch.drop_column(column)
