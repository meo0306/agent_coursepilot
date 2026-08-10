from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from courserag.persistence.base import CourseRAGBase, new_id, utc_now


class QueryProcessingRunRecord(CourseRAGBase):
    __tablename__ = "courserag_query_processing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_knowledge_bases.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="succeeded")
    raw_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_query: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    output_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    step_trace_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    filters_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    knowledge_points_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    expansions_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    routes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RetrievalRunRecord(CourseRAGBase):
    __tablename__ = "courserag_retrieval_runs"
    __table_args__ = (
        CheckConstraint("status IN ('running','succeeded','failed')", name="retrieval_run_status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_query_processing_runs.id", ondelete="CASCADE"), index=True
    )
    index_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_index_versions.id", ondelete="RESTRICT"), index=True
    )
    retrieval_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    result_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reranker_provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    reranker_model: Mapped[str | None] = mapped_column(String(240), nullable=True)
    candidate_k: Mapped[int | None] = mapped_column(Integer, nullable=True)
    top_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dense_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sparse_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fusion_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rerank_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cost_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    fallback_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    debug_trace_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IndexChunkRecord(CourseRAGBase):
    __tablename__ = "courserag_index_chunks"
    __table_args__ = (
        UniqueConstraint("index_version_id", "ordinal", name="uq_courserag_index_chunk_ordinal"),
    )

    index_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_index_versions.id", ondelete="CASCADE"), primary_key=True
    )
    chunk_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_chunks.id", ondelete="CASCADE"), primary_key=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)


class RerankCacheRecord(CourseRAGBase):
    __tablename__ = "courserag_rerank_cache"
    __table_args__ = (Index("ix_courserag_rerank_cache_provider_model", "provider", "model_name"),)

    cache_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(240), nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ContextPackageRecord(CourseRAGBase):
    __tablename__ = "courserag_context_packages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running','succeeded','failed')", name="context_package_status"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    query_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_query_processing_runs.id", ondelete="CASCADE"), index=True
    )
    retrieval_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_retrieval_runs.id", ondelete="CASCADE"), index=True
    )
    index_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_index_versions.id", ondelete="RESTRICT"), index=True
    )
    purpose: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    items_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    citation_map_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    packing_report_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QARunRecord(CourseRAGBase):
    __tablename__ = "courserag_qa_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    retrieval_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_retrieval_runs.id", ondelete="CASCADE"), index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    validation_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    context_package_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("courserag_context_packages.id", ondelete="RESTRICT"), nullable=True
    )
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    abstention_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    prompt_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profile_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    structured_output_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    usage_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    cost_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    repair_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnswerClaimRecord(CourseRAGBase):
    __tablename__ = "courserag_answer_claims"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    qa_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_qa_runs.id", ondelete="CASCADE"), index=True
    )
    claim_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    external_claim_id: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
    validation_status: Mapped[str | None] = mapped_column(String(32), nullable=True)


class AnswerClaimEvidenceRecord(CourseRAGBase):
    __tablename__ = "courserag_answer_claim_evidence"

    claim_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_answer_claims.id", ondelete="CASCADE"), primary_key=True
    )
    evidence_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("courserag_evidence.id", ondelete="RESTRICT"), primary_key=True
    )
