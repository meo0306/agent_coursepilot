import json
from decimal import Decimal
from pathlib import Path

from coursepilot.domain.exam import ExamBlueprintV2, QuestionBatchPlan, QuestionSlotPlan
from evaluation.p18_case_adapters import _compact_batch_generation_plan
from evaluation.p18_pre_freeze_closure import (
    PPT_THREAD_ID,
    closure_budget,
    verify_ppt_retry_source,
)
from evaluation.p18_runner import P18Ledger


def test_closure_budget_is_the_approved_off_peak_cap() -> None:
    budget = closure_budget()
    assert budget.max_cost_cny == Decimal("2.00")
    assert budget.max_input_tokens == 900_000
    assert budget.max_output_tokens == 600_000
    assert budget.max_requests == 100
    assert budget.cache_miss_input_cny_per_million == Decimal("0.5")
    assert budget.output_cny_per_million == Decimal("1.0")


def test_ppt_retry_accepts_only_one_zero_output_connection_failure(tmp_path: Path) -> None:
    request_id = "a" * 64
    source = {
        "requests": {
            request_id: {
                "status": "failed_billable_or_unknown",
                "invocation": {
                    "thread_id": PPT_THREAD_ID,
                    "prompt_name": "ppt/p16_generate_slide",
                    "error_category": "llm_provider_error",
                    "usage": {"output_tokens": 0},
                },
            }
        }
    }
    path = tmp_path / "source.json"
    path.write_text(json.dumps(source), encoding="utf-8")
    assert verify_ppt_retry_source(path) == request_id


def test_carried_ppt_responses_do_not_consume_closure_budget(tmp_path: Path) -> None:
    source_path = tmp_path / "source.json"
    source_path.write_text(
        json.dumps(
            {
                "requests": {
                    "b" * 64: {
                        "status": "succeeded",
                        "response": {"parsed": {"ok": True}},
                        "input_tokens": 100,
                        "output_tokens": 50,
                        "invocation": {"thread_id": PPT_THREAD_ID},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    ledger = P18Ledger(tmp_path / "target.json", closure_budget(), resume=False)
    assert ledger.seed_successful_responses(source_path, thread_id=PPT_THREAD_ID) == 1
    assert ledger.load("b" * 64) == {"parsed": {"ok": True}}
    assert ledger.totals() == {
        "requests": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cost_cny": "0.0",
    }


def test_compact_batch_plan_does_not_repeat_quadratic_exclusion_lists() -> None:
    slots = [
        QuestionSlotPlan(
            slot_id=f"slot-{index}",
            question_type="short_answer",
            score=5,
            target_id=f"target-{index}",
            knowledge_point_ids=["kp-1"],
            evidence_ids=["ev-1"],
            assessment_target=f"assessment-{index}",
            fact_signature=f"fact-{index}",
            answer_signature=f"answer-{index}",
        )
        for index in range(1, 4)
    ]
    batch = QuestionBatchPlan(
        batch_id="batch-1", ordinal=0, question_type="short_answer", slot_ids=["slot-1"]
    )
    blueprint = ExamBlueprintV2(
        blueprint_id="bp-1",
        task_id="task-1",
        course_id="course-1",
        template_id="exam-unit",
        chapter_range="1",
        context_package_id="ctx-1",
        knowledge_point_ids=["kp-1"],
        evidence_ids=["ev-1"],
        slots=slots,
        batches=[
            batch,
            QuestionBatchPlan(
                batch_id="batch-2",
                ordinal=1,
                question_type="short_answer",
                slot_ids=["slot-2", "slot-3"],
            ),
        ],
    ).with_hash()
    plan = _compact_batch_generation_plan(blueprint, batch)
    assert [item["slot_id"] for item in plan["batch_constraints"]] == ["slot-1"]
    assert len(plan["reserved_assessment_targets"]) == 2
    assert len(plan["reserved_fact_signatures"]) == 2
    assert len(plan["reserved_answer_signatures"]) == 2
    assert "excluded_fact_signatures" not in plan["batch_constraints"][0]
