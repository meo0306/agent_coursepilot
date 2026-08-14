"""Typed contracts for the CoursePilot runtime foundation."""

from coursepilot.domain.artifact import ArtifactRef, ArtifactVersion, StorageKind
from coursepilot.domain.context import ContextPackageRef
from coursepilot.domain.interrupts import (
    ApprovalScope,
    ChangeMode,
    DecisionAction,
    HumanDecision,
    InterruptPayload,
    InterruptStatus,
    InterruptType,
)
from coursepilot.domain.runtime import CommonGraphState, NodeResult, NodeStatus, RunContext
from coursepilot.domain.task import BusinessTask, TaskStatus, WorkflowType

__all__ = [
    "ArtifactRef",
    "ArtifactVersion",
    "BusinessTask",
    "CommonGraphState",
    "ContextPackageRef",
    "NodeResult",
    "NodeStatus",
    "RunContext",
    "StorageKind",
    "TaskStatus",
    "WorkflowType",
    "ApprovalScope",
    "ChangeMode",
    "DecisionAction",
    "HumanDecision",
    "InterruptPayload",
    "InterruptStatus",
    "InterruptType",
]
