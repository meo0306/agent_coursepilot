from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from coursepilot.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


def _uuid() -> str:
    return str(uuid4())


class TemplateSnapshotRecord(Base):
    __tablename__ = "coursepilot_template_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    template_id: Mapped[str] = mapped_column(String(160), nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    definition_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_hashes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prompt_hashes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    model_profile_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_versions_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validator_profile: Mapped[str] = mapped_column(String(160), nullable=False)
    repair_profile: Mapped[str] = mapped_column(String(160), nullable=False)
    exporter_profile: Mapped[str] = mapped_column(String(160), nullable=False)
    user_overrides_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class WorkflowRunRecord(Base):
    __tablename__ = "coursepilot_workflow_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    graph_version: Mapped[str] = mapped_column(String(100), nullable=False)
    template_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_template_snapshots.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(160), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    context_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("task_id", "run_number"),)


class ArtifactRecord(Base):
    __tablename__ = "coursepilot_artifacts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    course_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_courses.id", ondelete="CASCADE"), nullable=False
    )
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    active_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ArtifactVersionRecord(Base):
    __tablename__ = "coursepilot_artifact_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_artifacts.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(100), nullable=False)
    content_json: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    storage_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    source_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("coursepilot_workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    __table_args__ = (UniqueConstraint("artifact_id", "version"),)


class NodeRunRecord(Base):
    __tablename__ = "coursepilot_node_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_workflow_runs.id", ondelete="CASCADE"), nullable=False
    )
    node_name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    output_artifact_refs_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model_invocation_ids_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRecord(Base):
    __tablename__ = "coursepilot_approval_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("coursepilot_artifact_versions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(160), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    interrupt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    checkpoint_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decision_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_paths_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    request_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class InterruptRecord(Base):
    __tablename__ = "coursepilot_interrupts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    interrupt_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    checkpoint_id: Mapped[str] = mapped_column(String(255), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    context_identity_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_by_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class ResumeCommandRecord(Base):
    __tablename__ = "coursepilot_resume_commands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    interrupt_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("coursepilot_interrupts.id", ondelete="RESTRICT"), nullable=False
    )
    decision_id: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False)
    command_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SideEffectRunRecord(Base):
    __tablename__ = "coursepilot_side_effect_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_generation_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("coursepilot_artifact_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_key: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (UniqueConstraint("task_id", "artifact_version_id", "scope", "operation_key"),)


class ModelInvocationRecord(Base):
    __tablename__ = "coursepilot_model_invocations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("coursepilot_workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    node_run_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("coursepilot_node_runs.id", ondelete="SET NULL"), nullable=True
    )
    requested_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    resolved_profile: Mapped[str] = mapped_column(String(100), nullable=False)
    escalation_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    capability_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_name: Mapped[str] = mapped_column(String(255), nullable=False)
    prompt_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    response_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_known: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
