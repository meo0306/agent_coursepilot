"""Constrained, versioned targeted repair for CoursePilot artifacts."""

from coursepilot.repair.models import PatchOperation, RepairAction, RepairPlan, RepairResult
from coursepilot.repair.patch import PatchApplyError, apply_patch
from coursepilot.repair.planner import RepairPlanner
from coursepilot.repair.ppt import repair_slide_deterministic
from coursepilot.repair.service import TargetedRepairService

__all__ = [
    "PatchApplyError",
    "PatchOperation",
    "RepairAction",
    "RepairPlan",
    "RepairPlanner",
    "RepairResult",
    "TargetedRepairService",
    "apply_patch",
    "ExamRepairPlanner",
    "repair_slide_deterministic",
]
from coursepilot.repair.exam import ExamRepairPlanner
