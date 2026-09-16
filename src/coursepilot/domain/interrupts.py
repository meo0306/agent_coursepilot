from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import Field, model_validator

from coursepilot.domain.artifact import ArtifactRef
from coursepilot.domain.common import DomainModel


class InterruptType(StrEnum):
    LESSON_SESSION_PLAN = "lesson_session_plan_review"
    LESSON_FINAL = "lesson_final_review"
    EXAM_BLUEPRINT = "exam_blueprint_review"
    EXAM_GLOBAL = "exam_global_review"
    PPT_ARCHITECTURE = "ppt_architecture_review"
    PPT_FINAL = "ppt_final_review"


class InterruptStatus(StrEnum):
    PENDING = "pending"
    RESUMING = "resuming"
    RESUMED = "resumed"
    EXPIRED = "expired"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DecisionAction(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    REJECT = "reject"
    CANCEL = "cancel"
    CONTINUE_WITHOUT_WRITEBACK = "continue_without_writeback"


class ChangeMode(StrEnum):
    EDIT_RESUME = "edit_resume"
    REPLAN = "replan"
    REGENERATE = "regenerate"


class ApprovalScope(StrEnum):
    CONTINUE_GENERATION = "continue_generation"
    EXPORT = "export"
    VERIFIED_WRITEBACK = "verified_writeback"


class InterruptPayload(DomainModel):
    interrupt_type: InterruptType
    task_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    artifact_ref: ArtifactRef
    artifact_summary: dict[str, object] = Field(default_factory=dict)
    validation_summary: dict[str, object] = Field(default_factory=dict)
    editable_paths: list[str] = Field(default_factory=list)
    allowed_actions: list[str] = Field(default_factory=list)
    export_requires_approval: bool = True
    writeback_requires_separate_approval: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime

    @model_validator(mode="after")
    def validate_expiry(self) -> InterruptPayload:
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")
        return self

    @classmethod
    def with_ttl(cls, *, ttl_seconds: int, **kwargs: object) -> InterruptPayload:
        created = datetime.now(UTC)
        return cls(
            created_at=created, expires_at=created + timedelta(seconds=ttl_seconds), **kwargs
        )


class HumanDecision(DomainModel):
    decision_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    checkpoint_id: str = Field(min_length=1)
    action: DecisionAction
    feedback: str | None = None
    target_paths: list[str] = Field(default_factory=list)
    actor_id: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    change_mode: ChangeMode | None = None
    approval_scopes: list[ApprovalScope] = Field(default_factory=list)
    idempotency_key: str = Field(min_length=1)
    patch: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_action(self) -> HumanDecision:
        if self.action == DecisionAction.REQUEST_CHANGES and self.change_mode is None:
            raise ValueError("request_changes requires change_mode")
        if self.change_mode == ChangeMode.EDIT_RESUME and not self.target_paths:
            raise ValueError("edit_resume requires target_paths")
        return self
