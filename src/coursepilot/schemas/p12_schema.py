from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from coursepilot.domain import (
    ApprovalScope,
    ChangeMode,
    DecisionAction,
    InterruptStatus,
    InterruptType,
)


class RecoverableTaskCreate(BaseModel):
    workflow_type: Literal["lesson", "exam", "ppt"]
    task_type: str = Field(min_length=1)
    input_params: dict[str, Any] = Field(default_factory=dict)


class InterruptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str = Field(validation_alias="id")
    task_id: str
    interrupt_type: InterruptType
    status: InterruptStatus
    checkpoint_id: str
    thread_id: str
    artifact_version_id: str
    payload: dict[str, Any] = Field(validation_alias="payload_json")
    created_at: Any
    expires_at: Any
    superseded_by_id: str | None = None


class InterruptDecisionRequest(BaseModel):
    decision_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    action: DecisionAction
    feedback: str | None = None
    target_paths: list[str] = Field(default_factory=list)
    change_mode: ChangeMode | None = None
    approval_scopes: list[ApprovalScope] = Field(default_factory=list)
    patch: dict[str, object] = Field(default_factory=dict)


class ResumeCommandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    command_id: str = Field(validation_alias="id")
    task_id: str
    interrupt_id: str
    decision_id: str
    status: str
    result: dict[str, Any] | None = Field(default=None, validation_alias="result_json")
    error_category: str | None = None


class ScopeApprovalRequest(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    scope: ApprovalScope
    operation_key: str = Field(min_length=1)
    approved: bool = True
