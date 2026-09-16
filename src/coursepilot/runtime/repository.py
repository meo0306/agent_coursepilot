from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from coursepilot.domain.artifact import ArtifactRef, StorageKind
from coursepilot.domain.common import canonical_sha256
from coursepilot.models import (
    ArtifactRecord,
    ArtifactVersionRecord,
    GenerationTask,
    ModelInvocationRecord,
    NodeRunRecord,
    TemplateSnapshotRecord,
    WorkflowRunRecord,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class RuntimeRepository:
    """Single SQLAlchemy boundary for the P11 CoursePilot runtime facts."""

    def __init__(self, session: Session):
        self.session = session

    def pin_template_snapshot(self, snapshot: Mapping[str, Any]) -> TemplateSnapshotRecord:
        snapshot_sha256 = canonical_sha256(snapshot)
        existing = self.session.scalar(
            select(TemplateSnapshotRecord).where(
                TemplateSnapshotRecord.snapshot_sha256 == snapshot_sha256
            )
        )
        if existing is not None:
            return existing
        record = TemplateSnapshotRecord(
            template_id=str(snapshot["template_id"]),
            template_version=str(snapshot["template_version"]),
            definition_sha256=str(snapshot["definition_sha256"]),
            resource_hashes_json=dict(snapshot.get("resource_hashes", {})),
            prompt_hashes_json=dict(snapshot.get("prompt_hashes", {})),
            model_profile_sha256=str(snapshot["model_profile_sha256"]),
            schema_versions_json=dict(snapshot.get("schema_versions", {})),
            validator_profile=str(snapshot["validator_profile"]),
            repair_profile=str(snapshot["repair_profile"]),
            exporter_profile=str(snapshot["exporter_profile"]),
            user_overrides_json=dict(snapshot.get("user_overrides", {})),
            snapshot_sha256=snapshot_sha256,
        )
        self.session.add(record)
        self.session.flush()
        return record

    def start_run(
        self,
        *,
        task: GenerationTask,
        template_snapshot: TemplateSnapshotRecord,
        graph_version: str,
        request_id: str,
        trace_id: str,
        input_payload: Mapping[str, Any],
    ) -> WorkflowRunRecord:
        run_number = (
            int(
                self.session.scalar(
                    select(func.count(WorkflowRunRecord.id)).where(
                        WorkflowRunRecord.task_id == task.id
                    )
                )
                or 0
            )
            + 1
        )
        if task.thread_id is None:
            raise ValueError("GenerationTask has no stable thread identity")
        run = WorkflowRunRecord(
            task_id=task.id,
            run_number=run_number,
            status="running",
            thread_id=task.thread_id,
            graph_version=graph_version,
            template_snapshot_id=template_snapshot.id,
            request_id=request_id,
            trace_id=trace_id,
            input_sha256=canonical_sha256(input_payload),
        )
        self.session.add(run)
        self.session.flush()
        task.active_run_id = run.id
        return run

    def append_artifact_version(
        self,
        *,
        task: GenerationTask,
        artifact_type: str,
        schema_version: str,
        content: dict[str, Any] | list[Any],
        created_by: str,
        source_run_id: str | None,
        artifact: ArtifactRecord | None = None,
    ) -> tuple[ArtifactRecord, ArtifactVersionRecord, ArtifactRef]:
        target = artifact or ArtifactRecord(
            id=str(uuid4()),
            task_id=task.id,
            course_id=task.course_id,
            artifact_type=artifact_type,
        )
        if artifact is None:
            self.session.add(target)
            self.session.flush()
        if target.task_id != task.id or target.course_id != task.course_id:
            raise ValueError("Artifact ownership does not match task")
        current = int(
            self.session.scalar(
                select(func.max(ArtifactVersionRecord.version)).where(
                    ArtifactVersionRecord.artifact_id == target.id
                )
            )
            or 0
        )
        version_number = current + 1
        content_sha256 = canonical_sha256(content)
        version = ArtifactVersionRecord(
            artifact_id=target.id,
            version=version_number,
            schema_version=schema_version,
            content_json=content,
            storage_kind=StorageKind.POSTGRES.value,
            storage_uri=None,
            content_sha256=content_sha256,
            created_by=created_by,
            source_run_id=source_run_id,
        )
        self.session.add(version)
        self.session.flush()
        target.active_version = version_number
        task.active_artifact_version = version_number
        return (
            target,
            version,
            ArtifactRef(
                artifact_id=target.id,
                artifact_type=artifact_type,
                artifact_version=version_number,
                storage_kind=StorageKind.POSTGRES,
                content_hash=content_sha256,
                schema_version=schema_version,
            ),
        )

    def find_artifact(self, *, task_id: str, artifact_type: str) -> ArtifactRecord | None:
        return self.session.scalar(
            select(ArtifactRecord).where(
                ArtifactRecord.task_id == task_id,
                ArtifactRecord.artifact_type == artifact_type,
            )
        )

    def find_active_artifact(
        self, *, artifact_id: str, course_id: str
    ) -> tuple[ArtifactRecord, ArtifactVersionRecord] | None:
        artifact = self.session.get(ArtifactRecord, artifact_id)
        if artifact is None or artifact.course_id != course_id or artifact.active_version is None:
            return None
        version = self.session.scalar(
            select(ArtifactVersionRecord).where(
                ArtifactVersionRecord.artifact_id == artifact.id,
                ArtifactVersionRecord.version == artifact.active_version,
            )
        )
        return (artifact, version) if version is not None else None

    def finish_run(self, run_id: str, *, status: str) -> WorkflowRunRecord:
        run = self.session.get(WorkflowRunRecord, run_id)
        if run is None:
            raise ValueError(f"Workflow run not found: {run_id}")
        run.status = status
        run.completed_at = utc_now()
        return run

    def record_legacy_node(
        self,
        *,
        run_id: str,
        node_name: str,
        input_fingerprint: str,
        artifact_refs: list[dict[str, Any]],
        invocations: list[dict[str, Any]],
        provider: str,
        model: str,
        capability_sha256: str,
    ) -> NodeRunRecord:
        node = NodeRunRecord(
            run_id=run_id,
            node_name=node_name,
            status="succeeded",
            input_fingerprint=input_fingerprint,
            output_artifact_refs_json=artifact_refs,
            warnings_json=[],
            ended_at=utc_now(),
        )
        self.session.add(node)
        self.session.flush()
        invocation_ids: list[str] = []
        for item in invocations:
            usage: dict[str, Any] = item["usage"] if isinstance(item.get("usage"), dict) else {}
            usage_known = bool(usage and not usage.get("usage_estimated", False))
            prompt_name = str(item.get("prompt_name", "legacy_unknown"))
            requested_profile = _legacy_prompt_profile(prompt_name)
            record = ModelInvocationRecord(
                run_id=run_id,
                node_run_id=node.id,
                requested_profile=requested_profile,
                resolved_profile=requested_profile,
                escalation_reason=None,
                provider=provider if item.get("attempt_count") else "deterministic",
                model=model if item.get("attempt_count") else "not-invoked",
                capability_sha256=capability_sha256,
                prompt_name=prompt_name,
                prompt_sha256=str(item.get("prompt_sha256", "0" * 64)),
                request_sha256=canonical_sha256(
                    {"prompt_name": prompt_name, "thread_id": item.get("thread_id")}
                ),
                response_sha256=None,
                status=str(item.get("status", "unknown")),
                error_category=item.get("error_category"),
                input_tokens=usage.get("input_tokens") if usage_known else None,
                output_tokens=usage.get("output_tokens") if usage_known else None,
                total_tokens=usage.get("total_tokens") if usage_known else None,
                cost=None,
                usage_known=usage_known,
                fallback_used=bool(item.get("fallback_used", False)),
                latency_ms=item.get("latency_ms"),
            )
            self.session.add(record)
            self.session.flush()
            invocation_ids.append(record.id)
        node.model_invocation_ids_json = invocation_ids
        return node


def _legacy_prompt_profile(prompt_name: str) -> str:
    if "repair" in prompt_name or "revise" in prompt_name:
        return "content_repair_main"
    if "extract" in prompt_name or "classif" in prompt_name:
        return "classifier_light"
    if "plan" in prompt_name:
        return "planner_main"
    return "generator_main"
