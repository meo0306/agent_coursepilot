from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class IssueLayer(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class IssueScope(StrictModel):
    artifact_type: Literal["lesson", "exam", "ppt"]
    item_id: str | None = None
    json_path: str = Field(pattern=r"^\$")


class ValidationIssue(StrictModel):
    issue_id: str
    code: str = Field(min_length=1, max_length=160)
    severity: Severity
    layer: IssueLayer
    scope: IssueScope
    allowed_parent_paths: list[str] = Field(default_factory=list)
    auto_repairable: bool = False
    message: str = ""
    expected: Any | None = None
    actual: Any | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    repair_strategy: str = "deterministic_patch"

    @field_validator("severity", mode="before")
    @classmethod
    def normalize_legacy_severity(cls, value: object) -> object:
        return "critical" if value == "blocking" else value


class ValidationReport(StrictModel):
    artifact_id: str
    artifact_version: int | str
    artifact_type: Literal["lesson", "exam", "ppt"]
    validator_profile: str
    issues: list[ValidationIssue] = Field(default_factory=list)
    passed: bool = False
    critical_count: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    coverage_metrics: dict[str, float] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def finalize(self) -> ValidationReport:
        counts = {severity: 0 for severity in Severity}
        for issue in self.issues:
            counts[issue.severity] += 1
        self.critical_count = counts[Severity.CRITICAL]
        self.error_count = counts[Severity.ERROR]
        self.warning_count = counts[Severity.WARNING]
        self.info_count = counts[Severity.INFO]
        self.passed = self.critical_count == 0 and self.error_count == 0
        return self

    def issue_codes(self) -> set[str]:
        return {issue.code for issue in self.issues}
