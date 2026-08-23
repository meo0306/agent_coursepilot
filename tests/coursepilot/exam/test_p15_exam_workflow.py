from __future__ import annotations

import asyncio

from coursepilot.application.exam_workflow_service import ExamWorkflowService
from coursepilot.domain.exam import (
    ExamBlueprintV2,
    ExamQuestion,
    OptionAssessment,
    QuestionBatchPlan,
    QuestionSlotPlan,
)
from coursepilot.repair.exam import ExamRepairPlanner
from coursepilot.validation.exam import validate_exam_global


def blueprint() -> ExamBlueprintV2:
    slots = [
        QuestionSlotPlan(
            slot_id="slot-1",
            question_type="single_choice",
            score=2,
            difficulty="easy",
            content_role="definition",
            target_id="target-1",
            knowledge_point_ids=["kp-1"],
            evidence_ids=["ev-1"],
        ),
        QuestionSlotPlan(
            slot_id="slot-2",
            question_type="short_answer",
            score=3,
            difficulty="medium",
            content_role="application",
            target_id="target-2",
            knowledge_point_ids=["kp-2"],
            evidence_ids=["ev-2"],
        ),
    ]
    return ExamBlueprintV2(
        blueprint_id="bp-1",
        task_id="task-1",
        course_id="course-1",
        template_id="exam_unit_quiz_v1",
        chapter_range="1",
        context_package_id="ctx-1",
        knowledge_point_ids=["kp-1", "kp-2"],
        evidence_ids=["ev-1", "ev-2"],
        slots=slots,
        batches=[
            QuestionBatchPlan(
                batch_id="b-1", ordinal=0, question_type="single_choice", slot_ids=["slot-1"]
            ),
            QuestionBatchPlan(
                batch_id="b-2", ordinal=1, question_type="short_answer", slot_ids=["slot-2"]
            ),
        ],
    )


def question(slot: QuestionSlotPlan) -> ExamQuestion:
    return ExamQuestion(
        question_id=f"q-{slot.slot_id}",
        slot_id=slot.slot_id,
        question_number=1,
        question_type=slot.question_type,
        score=slot.score,
        difficulty=slot.difficulty,
        content_role=slot.content_role,
        stem=(
            f"Select the formal definition for {slot.slot_id}."
            if slot.question_type == "single_choice"
            else f"Apply the procedure to a new scenario for {slot.slot_id}."
        ),
        options={"A": "alpha", "B": "beta"} if slot.question_type == "single_choice" else {},
        answer="A" if slot.question_type == "single_choice" else "A grounded answer",
        explanation="The evidence supports this answer.",
        knowledge_point_ids=slot.knowledge_point_ids,
        evidence_ids=slot.evidence_ids,
    )


def test_fan_in_is_blueprint_order_and_respects_concurrency() -> None:
    bp = blueprint()
    active = 0
    maximum = 0

    async def generate(batch: QuestionBatchPlan, _: ExamBlueprintV2) -> list[ExamQuestion]:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.001 if batch.ordinal == 0 else 0.01)
        active -= 1
        return [question(next(slot for slot in bp.slots if slot.slot_id == batch.slot_ids[0]))]

    artifact, report, _ = asyncio.run(
        ExamWorkflowService(max_concurrency=2).build_artifact(bp, generate)
    )
    assert maximum <= 2
    assert [item.slot_id for item in artifact.questions] == ["slot-1", "slot-2"]
    assert [item.question_number for item in artifact.questions] == [1, 2]
    assert report.passed


def test_global_validator_catches_duplicate_and_answer_leakage() -> None:
    bp = blueprint()
    first = question(bp.slots[0])
    second = question(bp.slots[1]).model_copy(
        update={"stem": f"{first.stem} alpha", "answer": "alpha"}
    )
    report = validate_exam_global(bp, [first, second])
    assert not report.passed
    assert not report.duplicate_valid
    assert not report.answer_leakage_valid


def test_global_validator_requires_real_multi_select_and_consistent_assessments() -> None:
    bp = blueprint()
    multi_slot = bp.slots[0].model_copy(update={"question_type": "multiple_choice"})
    bp = bp.model_copy(
        update={
            "slots": [multi_slot, bp.slots[1]],
            "batches": [
                bp.batches[0].model_copy(update={"question_type": "multiple_choice"}),
                bp.batches[1],
            ],
        }
    )
    first = question(multi_slot).model_copy(
        update={
            "question_type": "multiple_choice",
            "options": {"A": "alpha", "B": "beta", "C": "gamma"},
            "answer": "A",
        }
    )
    report = validate_exam_global(bp, [first, question(bp.slots[1])])
    assert not report.choice_contract_valid
    assert report.question_issue_codes[first.question_id] == ["EXAM_MULTIPLE_CHOICE_CARDINALITY"]

    inconsistent = first.model_copy(
        update={
            "answer": "A,B",
            "option_assessments": {
                "A": OptionAssessment(
                    is_correct=True, rationale="Supported", evidence_ids=["ev-1"]
                ),
                "B": OptionAssessment(
                    is_correct=False, rationale="Not supported", evidence_ids=["ev-1"]
                ),
                "C": OptionAssessment(
                    is_correct=False, rationale="Not supported", evidence_ids=["ev-1"]
                ),
            },
        }
    )
    report = validate_exam_global(bp, [inconsistent, question(bp.slots[1])])
    assert not report.answer_set_valid
    assert "EXAM_ANSWER_SET_INCONSISTENT" in report.question_issue_codes[first.question_id]


def test_global_validator_requires_inline_stimulus_for_table_reference() -> None:
    bp = blueprint()
    first = question(bp.slots[0]).model_copy(update={"stem": "According to the table, choose."})
    report = validate_exam_global(bp, [first, question(bp.slots[1])])
    assert not report.stimulus_valid
    assert report.stimulus_question_ids == [first.question_id]

    supplied = first.model_copy(update={"stimulus": "Model | Parameters\nA | 10M"})
    report = validate_exam_global(bp, [supplied, question(bp.slots[1])])
    assert report.stimulus_valid

    chinese_reference = first.model_copy(update={"stem": "根据表中数据选择正确答案。"})
    report = validate_exam_global(bp, [chinese_reference, question(bp.slots[1])])
    assert not report.stimulus_valid

    ordinary_wording = first.model_copy(update={"stem": "下列表述中正确的是哪一项？"})
    report = validate_exam_global(bp, [ordinary_wording, question(bp.slots[1])])
    assert report.stimulus_valid


def test_batch_failure_is_isolated_and_preserves_other_batch() -> None:
    bp = blueprint()

    async def generate(batch: QuestionBatchPlan, _: ExamBlueprintV2) -> list[ExamQuestion]:
        if batch.batch_id == "b-2":
            raise ValueError("invalid structured provider output")
        slot = next(item for item in bp.slots if item.slot_id == batch.slot_ids[0])
        return [question(slot)]

    artifact, report, executions = asyncio.run(
        ExamWorkflowService(max_concurrency=2).build_artifact(bp, generate)
    )
    assert [item.slot_id for item in artifact.questions] == ["slot-1"]
    assert not report.question_count_valid
    assert [item.result.status for item in executions] == ["succeeded", "failed"]
    assert executions[1].result.issue_codes == ["BATCH_GENERATION_FAILED:ValueError"]


def test_repair_planner_targets_only_later_duplicate_and_leaking_question() -> None:
    bp = blueprint()
    first = question(bp.slots[0]).model_copy(update={"question_id": "q:case:slot-1"})
    second = question(bp.slots[1]).model_copy(
        update={
            "question_id": "q:case:slot-2",
            "stem": f"{first.stem} alpha",
            "answer": "alpha",
        }
    )
    report = validate_exam_global(bp, [first, second])
    plan = ExamRepairPlanner(max_model_calls=4).plan(
        artifact_id="task-1",
        artifact_version=1,
        report=report,
        questions=[first, second],
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].target_scope == "$.questions[1]"
    assert plan.actions[0].allowed_paths == [
        "$.questions[1].stimulus",
        "$.questions[1].stem",
        "$.questions[1].options",
        "$.questions[1].option_assessments",
        "$.questions[1].answer",
        "$.questions[1].explanation",
    ]
    alternate_plan = ExamRepairPlanner(max_model_calls=4).plan(
        artifact_id="task-1",
        artifact_version=1,
        report=report,
        questions=[first, second],
        excluded_question_ids={second.question_id},
    )
    assert alternate_plan.actions[0].target_scope == "$.questions[0]"


def test_global_repair_changes_only_allowed_question_fields() -> None:
    bp = blueprint()
    first = question(bp.slots[0])
    second = question(bp.slots[1]).model_copy(
        update={"stem": first.stem, "answer": "A grounded answer"}
    )
    artifact, report, _ = asyncio.run(
        ExamWorkflowService().build_artifact(
            bp,
            lambda batch, _: _return_question(first if batch.batch_id == "b-1" else second),
        )
    )

    async def repair(
        original: ExamQuestion,
        issue_ids: list[str],
        all_questions: list[ExamQuestion],
        _: ExamBlueprintV2,
    ) -> ExamQuestion:
        assert issue_ids
        assert len(all_questions) == 2
        return original.model_copy(
            update={
                "question_id": "forbidden-change",
                "stem": "Apply the concept to an independent practical scenario.",
                "answer": "A grounded answer",
            }
        )

    repaired, final_report, events = asyncio.run(
        ExamWorkflowService().repair_global_issues(bp, artifact, report, repair)
    )
    assert events == ["REPAIRED:q-slot-2"]
    assert repaired.questions[1].question_id == "q-slot-2"
    assert repaired.questions[1].slot_id == "slot-2"
    assert repaired.questions[1].stem == "Apply the concept to an independent practical scenario."
    assert final_report.passed


async def _return_question(value: ExamQuestion) -> list[ExamQuestion]:
    return [value]
