from __future__ import annotations

from typing import NotRequired, TypedDict

from coursepilot.domain.context import ContextPackageRef
from coursepilot.domain.lesson import LessonArtifact, LessonBlueprint, LessonSessionArtifact
from courserag.contracts.knowledge_points import KnowledgePointSnapshot


class LessonWorkflowState(TypedDict):
    legacy: NotRequired[bool]
    task_id: str
    course_id: str
    request: dict[str, object]
    template_snapshot_id: str
    knowledge_points: NotRequired[KnowledgePointSnapshot]
    context_ref: NotRequired[ContextPackageRef]
    blueprint: NotRequired[LessonBlueprint]
    sessions: NotRequired[list[LessonSessionArtifact]]
    artifact: NotRequired[LessonArtifact]
    validation_report: NotRequired[dict[str, object]]
    warnings: NotRequired[list[dict[str, object]]]
    decision: NotRequired[dict[str, object]]
