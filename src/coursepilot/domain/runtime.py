from __future__ import annotations

from enum import StrEnum
from typing import NotRequired, TypedDict

from pydantic import Field

from coursepilot.domain.artifact import ArtifactRef
from coursepilot.domain.common import DomainModel, UTCDateTime
from coursepilot.domain.context import ContextPackageRef


class NodeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    WAITING_HUMAN = "waiting_human"


class NodeResult(DomainModel):
    node_name: str = Field(min_length=1)
    status: NodeStatus
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_artifacts: list[ArtifactRef] = Field(default_factory=list)
    model_run_ids: list[str] = Field(default_factory=list)
    warnings: list[dict[str, object]] = Field(default_factory=list)
    started_at: UTCDateTime
    ended_at: UTCDateTime

    @property
    def reusable(self) -> bool:
        return self.status == NodeStatus.SUCCEEDED


class RunContext(DomainModel):
    run_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    git_commit: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    template_snapshot_id: str = Field(min_length=1)
    template_snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_profile_manifest_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    courserag_index_version: str | None = None
    courserag_context_id: str | None = None
    request_id: str = Field(min_length=1)
    trace_id: str = Field(min_length=1)


class CommonGraphState(TypedDict):
    run_context: RunContext
    request: dict[str, object]
    artifacts: dict[str, ArtifactRef]
    context_packages: dict[str, ContextPackageRef]
    node_results: list[NodeResult]
    warnings: list[dict[str, object]]
    summaries: dict[str, str]
    error: NotRequired[dict[str, object] | None]
