"""Add versioned hybrid retrieval persistence without changing legacy indexes."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0013_hybrid_retrieval"
down_revision: str | None = "0012_knowledge_point_assets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("courserag_source_documents") as batch:
        batch.add_column(
            sa.Column(
                "source_tier",
                sa.String(32),
                nullable=False,
                server_default="primary_source",
            )
        )
        batch.create_check_constraint(
            "source_document_tier",
            "source_tier IN ('primary_source','teacher_verified','external_reference','generated_draft')",
        )
        batch.create_index(
            "ix_courserag_source_documents_tier", ["knowledge_base_id", "source_tier"]
        )

    op.create_table(
        "courserag_index_chunks",
        sa.Column("index_version_id", sa.String(36), nullable=False),
        sa.Column("chunk_id", sa.String(36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["index_version_id"], ["courserag_index_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["chunk_id"], ["courserag_chunks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("index_version_id", "chunk_id"),
        sa.UniqueConstraint("index_version_id", "ordinal", name="uq_courserag_index_chunk_ordinal"),
    )
    op.create_index("ix_courserag_index_chunks_chunk_id", "courserag_index_chunks", ["chunk_id"])

    with op.batch_alter_table("courserag_retrieval_runs") as batch:
        batch.add_column(
            sa.Column("status", sa.String(32), nullable=False, server_default="running")
        )
        batch.add_column(sa.Column("request_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("config_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("result_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("reranker_provider", sa.String(80), nullable=True))
        batch.add_column(sa.Column("reranker_model", sa.String(240), nullable=True))
        batch.add_column(sa.Column("candidate_k", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("top_n", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("dense_latency_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("sparse_latency_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("fusion_latency_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("rerank_latency_ms", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("usage_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("cost_json", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(
            sa.Column("fallback_applied", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch.add_column(sa.Column("warnings_json", sa.JSON(), nullable=False, server_default="[]"))
        batch.add_column(
            sa.Column("debug_trace_json", sa.JSON(), nullable=False, server_default="{}")
        )
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint(
            "retrieval_run_status", "status IN ('running','succeeded','failed')"
        )

    op.create_table(
        "courserag_rerank_cache",
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model_name", sa.String(240), nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("cache_key"),
    )
    op.create_index(
        "ix_courserag_rerank_cache_provider_model",
        "courserag_rerank_cache",
        ["provider", "model_name"],
    )


def downgrade() -> None:
    op.drop_index("ix_courserag_rerank_cache_provider_model", table_name="courserag_rerank_cache")
    op.drop_table("courserag_rerank_cache")
    with op.batch_alter_table("courserag_retrieval_runs") as batch:
        batch.drop_constraint("retrieval_run_status", type_="check")
        for column in (
            "completed_at",
            "debug_trace_json",
            "warnings_json",
            "fallback_applied",
            "cost_json",
            "usage_json",
            "rerank_latency_ms",
            "fusion_latency_ms",
            "sparse_latency_ms",
            "dense_latency_ms",
            "top_n",
            "candidate_k",
            "reranker_model",
            "reranker_provider",
            "result_sha256",
            "config_sha256",
            "request_sha256",
            "status",
        ):
            batch.drop_column(column)
    op.drop_index("ix_courserag_index_chunks_chunk_id", table_name="courserag_index_chunks")
    op.drop_table("courserag_index_chunks")
    with op.batch_alter_table("courserag_source_documents") as batch:
        batch.drop_index("ix_courserag_source_documents_tier")
        batch.drop_constraint("source_document_tier", type_="check")
        batch.drop_column("source_tier")
