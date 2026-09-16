from __future__ import annotations

from typing import TypedDict

from coursepilot.application.exam_workflow_service import (
    ExamWorkflowService,
    QuestionGenerator,
    QuestionRepairer,
)
from coursepilot.domain.exam import ExamArtifact, ExamBlueprintV2


class ExamV2GraphState(TypedDict, total=False):
    task_id: str
    phase: str
    blueprint: ExamBlueprintV2
    artifact: ExamArtifact
    global_report: dict[str, object]
    blueprint_review_approved: bool
    global_review_approved: bool
    warnings: list[str]


class ExamV2Graph:
    """Small runtime seam; P12 persists the surrounding state/checkpoint."""

    def __init__(self, *, max_concurrency: int = 3) -> None:
        self.workflow = ExamWorkflowService(max_concurrency=max_concurrency)

    async def run(
        self,
        blueprint: ExamBlueprintV2,
        generator: QuestionGenerator,
        *,
        blueprint_review_approved: bool = False,
        global_review_approved: bool = False,
        repairer: QuestionRepairer | None = None,
    ) -> ExamV2GraphState:
        if not blueprint.content_hash:
            blueprint = blueprint.with_hash()
        if not blueprint_review_approved:
            return {
                "task_id": blueprint.task_id,
                "phase": "blueprint_review",
                "blueprint": blueprint,
                "blueprint_review_approved": False,
                "global_review_approved": False,
                "warnings": ["BLUEPRINT_REVIEW_REQUIRED"],
            }
        artifact, report, _ = await self.workflow.build_artifact(blueprint, generator)
        if repairer is not None and not report.passed:
            artifact, report, _ = await self.workflow.repair_global_issues(
                blueprint,
                artifact,
                report,
                repairer,
                max_repairs=4,
                resolvable_evidence_ids=set(blueprint.evidence_ids),
            )
        artifact = artifact.model_copy(
            update={"blueprint_approved": True, "global_review_approved": global_review_approved}
        )
        return {
            "task_id": blueprint.task_id,
            "phase": "global_review",
            "blueprint": blueprint,
            "artifact": artifact,
            "global_report": report.model_dump(mode="json"),
            "blueprint_review_approved": True,
            "global_review_approved": global_review_approved,
            "warnings": list(report.errors),
        }


def build_exam_v2_graph(*, max_concurrency: int = 3) -> ExamV2Graph:
    return ExamV2Graph(max_concurrency=max_concurrency)
