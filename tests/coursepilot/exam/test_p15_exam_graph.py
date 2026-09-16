from __future__ import annotations

import asyncio

from agents.coursepilot.exam.graph import build_exam_v2_graph
from coursepilot.domain.exam import (
    ExamBlueprintV2,
    ExamQuestion,
    QuestionBatchPlan,
    QuestionSlotPlan,
)


def _blueprint() -> ExamBlueprintV2:
    return ExamBlueprintV2(
        blueprint_id="bp-1",
        task_id="task-1",
        course_id="course-1",
        template_id="exam_unit_quiz_v1",
        chapter_range="1",
        context_package_id="ctx-1",
        knowledge_point_ids=["kp-1"],
        evidence_ids=["ev-1"],
        slots=[
            QuestionSlotPlan(
                slot_id="slot-1",
                question_type="single_choice",
                score=1,
                target_id="kp-1",
                knowledge_point_ids=["kp-1"],
                evidence_ids=["ev-1"],
            )
        ],
        batches=[
            QuestionBatchPlan(
                batch_id="batch-1", ordinal=0, question_type="single_choice", slot_ids=["slot-1"]
            )
        ],
    )


def test_exam_graph_requires_blueprint_approval_before_generation() -> None:
    calls = 0

    async def generator(batch: QuestionBatchPlan, blueprint: ExamBlueprintV2) -> list[ExamQuestion]:
        nonlocal calls
        calls += 1
        return [
            ExamQuestion(
                question_id="q-1",
                slot_id=batch.slot_ids[0],
                question_number=1,
                question_type="single_choice",
                score=1,
                difficulty="medium",
                content_role="definition",
                stem="What?",
                options={"A": "yes", "B": "no"},
                answer="A",
                explanation="Evidence supports A.",
                knowledge_point_ids=["kp-1"],
                evidence_ids=["ev-1"],
            )
        ]

    graph = build_exam_v2_graph()
    pending = asyncio.run(graph.run(_blueprint(), generator))
    assert pending["phase"] == "blueprint_review"
    assert pending["warnings"] == ["BLUEPRINT_REVIEW_REQUIRED"]
    assert calls == 0

    approved = asyncio.run(graph.run(_blueprint(), generator, blueprint_review_approved=True))
    assert approved["phase"] == "global_review"
    assert approved["blueprint_review_approved"] is True
    assert approved["global_review_approved"] is False
    assert calls == 1
