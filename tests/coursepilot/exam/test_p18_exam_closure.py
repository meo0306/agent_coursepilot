from __future__ import annotations

import asyncio

import pytest

from coursepilot.application.exam_workflow_service import ExamWorkflowService
from coursepilot.domain.exam import (
    ExamArtifact,
    ExamBlueprintV2,
    ExamQuestion,
    QuestionBatchPlan,
    QuestionSlotPlan,
)
from coursepilot.llm import CoursePilotLLMBudgetExceeded
from coursepilot.validation.exam import validate_exam_global
from evaluation.p18_case_adapters import _completed_exam_batches, _repair_issue_contract


def _blueprint() -> ExamBlueprintV2:
    slots = [
        QuestionSlotPlan(
            slot_id=f"slot-{index}",
            question_type="short_answer",
            score=5,
            difficulty="medium",
            content_role=role,
            target_id="target-shared",
            knowledge_point_ids=["kp-1"],
            evidence_ids=["ev-1"],
            assessment_target=f"target-{index}-{role}",
            fact_signature=f"fact-{index}",
            answer_signature=f"answer-{index}",
        )
        for index, role in ((1, "definition"), (2, "application"), (3, "comparison"))
    ]
    return ExamBlueprintV2(
        blueprint_id="bp-p18",
        task_id="task-p18",
        course_id="course-1",
        template_id="exam_unit_quiz_v1",
        chapter_range="1",
        context_package_id="ctx-1",
        knowledge_point_ids=["kp-1"],
        evidence_ids=["ev-1"],
        slots=slots,
        batches=[
            QuestionBatchPlan(
                batch_id="batch-1",
                ordinal=0,
                question_type="short_answer",
                slot_ids=[slot.slot_id for slot in slots],
            )
        ],
    ).with_hash()


def _question(slot: QuestionSlotPlan, stem: str) -> ExamQuestion:
    return ExamQuestion(
        question_id=f"question-{slot.slot_id}",
        slot_id=slot.slot_id,
        question_number=int(slot.slot_id[-1]),
        question_type=slot.question_type,
        score=slot.score,
        difficulty=slot.difficulty,
        content_role=slot.content_role,
        stem=stem,
        answer=f"answer for {slot.slot_id}",
        explanation="Supported by the bound evidence.",
        knowledge_point_ids=slot.knowledge_point_ids,
        evidence_ids=slot.evidence_ids,
    )


def test_generation_plan_exposes_unique_targets_and_global_exclusions() -> None:
    plan = _blueprint().generation_plan()
    assert len({item.assessment_target for item in plan.constraints}) == 3
    assert all(len(item.excluded_fact_signatures) == 2 for item in plan.constraints)
    assert all(len(item.excluded_answer_signatures) == 2 for item in plan.constraints)


def test_conflict_round_regenerates_each_later_target_once() -> None:
    blueprint = _blueprint()
    questions = [
        _question(blueprint.slots[0], "Explain the shared concept."),
        _question(blueprint.slots[1], "Explain the shared concept."),
        _question(blueprint.slots[2], "Explain the shared concept."),
    ]
    artifact = ExamArtifact(
        task_id=blueprint.task_id,
        course_id=blueprint.course_id,
        blueprint=blueprint,
        questions=questions,
        blueprint_approved=True,
    )
    report = validate_exam_global(blueprint, questions)
    calls: list[str] = []

    async def regenerate(
        original: ExamQuestion,
        issue_ids: list[str],
        _: list[ExamQuestion],
        __: ExamBlueprintV2,
    ) -> ExamQuestion:
        calls.append(original.question_id)
        assert issue_ids
        replacements = {
            "slot-2": (
                "Apply the principle to diagnose a sensor failure scenario.",
                "Use the observed signal boundary to isolate the failed component.",
            ),
            "slot-3": (
                "Compare the two approved methods by their stated operational constraints.",
                "The first method optimizes latency while the second preserves accuracy.",
            ),
        }
        stem, answer = replacements[original.slot_id]
        return original.model_copy(
            update={
                "stem": stem,
                "answer": answer,
                "explanation": f"Distinct evidence path for {original.slot_id}.",
            }
        )

    repaired, final_report, events = asyncio.run(
        ExamWorkflowService().regenerate_conflicts(
            blueprint,
            artifact,
            report,
            regenerate,
            max_regenerations=3,
        )
    )
    assert calls == ["question-slot-2", "question-slot-3"]
    assert events == [
        "REGENERATED:question-slot-2",
        "REGENERATED:question-slot-3",
    ]
    assert repaired.questions[0] == questions[0]
    assert final_report.duplicate_valid


def test_provider_budget_abort_is_not_downgraded_to_a_failed_batch() -> None:
    blueprint = _blueprint()

    async def blocked(*_: object) -> list[ExamQuestion]:
        raise CoursePilotLLMBudgetExceeded("budget")

    with pytest.raises(CoursePilotLLMBudgetExceeded, match="budget"):
        asyncio.run(ExamWorkflowService().build_artifact(blueprint, blocked))


def test_partial_checkpoint_reuses_only_batches_with_every_slot() -> None:
    blueprint = (
        _blueprint()
        .model_copy(
            update={
                "batches": [
                    QuestionBatchPlan(
                        batch_id="batch-1",
                        ordinal=0,
                        question_type="short_answer",
                        slot_ids=["slot-1", "slot-2"],
                    ),
                    QuestionBatchPlan(
                        batch_id="batch-2",
                        ordinal=1,
                        question_type="short_answer",
                        slot_ids=["slot-3"],
                    ),
                ]
            }
        )
        .with_hash()
    )
    prior = ExamArtifact(
        task_id=blueprint.task_id,
        course_id=blueprint.course_id,
        blueprint=blueprint,
        questions=[_question(blueprint.slots[0], "First")],
        blueprint_approved=True,
    )
    assert _completed_exam_batches(blueprint, {"artifact": prior.model_dump(mode="json")}) == {}
    prior = prior.model_copy(
        update={
            "questions": [
                _question(blueprint.slots[0], "First"),
                _question(blueprint.slots[1], "Second"),
            ]
        }
    )
    completed = _completed_exam_batches(blueprint, {"artifact": prior.model_dump(mode="json")})
    assert list(completed) == ["batch-1"]
    assert [item.slot_id for item in completed["batch-1"].questions] == ["slot-1", "slot-2"]


def test_single_question_repair_contract_is_issue_specific() -> None:
    contract = _repair_issue_contract(
        "multiple_choice",
        "required",
        ["EXAM_MULTIPLE_CHOICE_CARDINALITY", "CROSS_ANSWER_LEAKAGE"],
    )
    assert contract["return_one_question_object_not_a_list"] is True
    assert contract["minimum_correct_options"] == 2
    assert contract["answer_must_equal_exact_correct_option_key_set"] is True
    assert contract["stimulus_must_be_non_empty"] is True
    assert contract["avoid_forbidden_question_stems_and_answers"] is True
