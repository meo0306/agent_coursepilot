from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PatchOperation(StrictModel):
    op: Literal["add", "replace", "remove"]
    path: str = Field(pattern=r"^\$")
    value: Any | None = None
    expected_value: Any | None = None
    issue_id: str | None = None


class RepairAction(StrictModel):
    issue_ids: list[str] = Field(min_length=1)
    strategy: Literal[
        "deterministic_patch",
        "regenerate_component",
        "retrieve_more_evidence",
        "model_patch",
        "human_review",
    ]
    target_scope: str
    allowed_paths: list[str] = Field(min_length=1)
    validator_layers: list[str] = Field(default_factory=list)
    model_profile: str | None = None


class RepairPlan(StrictModel):
    artifact_id: str
    artifact_version: int | str
    actions: list[RepairAction] = Field(default_factory=list)
    max_model_calls: int = Field(default=1, ge=0)
    allowed_json_paths: list[str] = Field(default_factory=list)
    forbidden_json_paths: list[str] = Field(default_factory=list)
    requires_full_regeneration: bool = False


class RepairResult(StrictModel):
    status: Literal["accepted", "needs_review", "rejected"]
    source_artifact_version: int | str
    output_artifact_version: int | str | None = None
    applied_operations: list[PatchOperation] = Field(default_factory=list)
    resolved_issue_ids: list[str] = Field(default_factory=list)
    unauthorized_paths: list[str] = Field(default_factory=list)
    regression_issue_ids: list[str] = Field(default_factory=list)
    preserved: bool = True
    reason: str | None = None
