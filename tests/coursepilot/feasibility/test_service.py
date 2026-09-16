from pathlib import Path

import pytest

from coursepilot.application.feasibility_service import (
    DemandBuildError,
    ExamDemandBuilder,
    FeasibilityEvaluator,
    LessonDemandBuilder,
    PPTDemandBuilder,
)
from coursepilot.domain import (
    AdequacySnapshot,
    AdequacyStatus,
    DemandBuildContext,
    FeasibilityAction,
    FeasibilityReasonCode,
    FeasibilityStatus,
    MaterialType,
    PPTLessonDemandContext,
    SemanticUnitRequirement,
)
from coursepilot.schemas.exam_schema import ExamGenerationParams
from coursepilot.schemas.lesson_schema import LessonGenerationParams
from coursepilot.schemas.ppt_schema import PPTGenerationParams


def _rich_snapshot(demand, *, low_character_warning: bool = False) -> AdequacySnapshot:
    return AdequacySnapshot(
        status=AdequacyStatus.ADEQUATE,
        knowledge_point_unit_counts={
            item: demand.minimum_units_per_knowledge_point
            for item in reversed(demand.knowledge_point_ids)
        },
        requirement_unit_counts={
            item.requirement_id: item.minimum_count
            for item in reversed(demand.semantic_requirements)
        },
        distinct_sources=demand.minimum_distinct_sources,
        distinct_semantic_units=demand.minimum_semantic_units,
        supported_target_unit_count=demand.target_unit_count,
        low_character_count_warning=low_character_warning,
    )


def test_lesson_builder_is_deterministic_and_uses_balanced_capacity() -> None:
    params = LessonGenerationParams(
        chapter_range="Chapter 2",
        total_sessions=2,
        student_level="undergraduate",
        student_background="introductory course completed",
        teaching_focus="causal reasoning",
        additional_requirements="Please include a table",  # deliberately not parsed
    )
    context = DemandBuildContext(
        knowledge_point_ids=["kp-1", "kp-2"],
        additional_requirements=[
            SemanticUnitRequirement(
                requirement_id="lesson.requested_table",
                minimum_count=1,
                material_types=[MaterialType.TABLE],
            )
        ],
    )

    first = LessonDemandBuilder.build(course_id="course-1", params=params, context=context)
    second = LessonDemandBuilder.build(course_id="course-1", params=params, context=context)

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.scope_label == "Chapter 2 | focus: causal reasoning"
    assert first.audience == "undergraduate; background: introductory course completed"
    assert first.minimum_semantic_units == 6
    assert first.minimum_distinct_sources == 2
    assert {item.requirement_id for item in first.semantic_requirements} == {
        "lesson.application_context",
        "lesson.definition",
        "lesson.example",
        "lesson.process",
        "lesson.requested_table",
    }


def test_lesson_builder_does_not_infer_materials_from_free_text() -> None:
    demand = LessonDemandBuilder.build(
        course_id="course-1",
        params=LessonGenerationParams(
            chapter_range="Chapter 1",
            additional_requirements="Use formula, numeric table and case study",
        ),
    )
    materials = {
        material
        for requirement in demand.semantic_requirements
        for material in requirement.material_types
    }
    assert materials == set()


def test_exam_builder_normalizes_difficulty_with_stable_largest_remainder() -> None:
    demand = ExamDemandBuilder.build(
        course_id="course-1",
        params=ExamGenerationParams(
            chapter_range="Chapter 3",
            difficulty_distribution={"easy": 3, "medium": 5, "hard": 2},
        ),
    )

    assert demand.target_unit_count == 12
    assert demand.difficulty_profile == {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    assert demand.minimum_semantic_units == 14
    requirements = {
        item.requirement_id: item.minimum_count for item in demand.semantic_requirements
    }
    assert requirements == {
        "exam.application_context": 4,
        "exam.comparison": 1,
        "exam.definition": 3,
        "exam.principle": 3,
        "exam.process": 1,
    }


def test_exam_builder_rejects_unknown_difficulty_without_touching_request_schema() -> None:
    params = ExamGenerationParams(
        chapter_range="Chapter 3",
        difficulty_distribution={"easy": 0.5, "advanced": 0.5},
    )
    with pytest.raises(DemandBuildError, match="unsupported difficulty key"):
        ExamDemandBuilder.build(course_id="course-1", params=params)


def test_ppt_builder_reuses_existing_default_slide_count_rule() -> None:
    lesson = PPTLessonDemandContext(
        lesson_id="lesson-1",
        chapter_scope="Chapter 4",
        total_sessions=2,
        knowledge_point_ids=["kp-1"],
    )
    default_demand = PPTDemandBuilder.build(
        course_id="course-1",
        params=PPTGenerationParams(),
        lesson=lesson,
    )
    explicit_demand = PPTDemandBuilder.build(
        course_id="course-1",
        params=PPTGenerationParams(slide_count=3),
        lesson=lesson,
    )

    assert default_demand.target_unit_count == 6
    assert default_demand.minimum_semantic_units == 6
    assert default_demand.source_artifact_id == "lesson-1"
    assert explicit_demand.target_unit_count == 3


def test_builder_rejects_additional_requirement_id_collision() -> None:
    context = DemandBuildContext(
        additional_requirements=[
            SemanticUnitRequirement(
                requirement_id="lesson.definition",
                minimum_count=1,
                roles=["definition"],
            )
        ]
    )
    with pytest.raises(DemandBuildError, match="duplicate semantic requirement ID"):
        LessonDemandBuilder.build(
            course_id="course-1",
            params=LessonGenerationParams(chapter_range="Chapter 1"),
            context=context,
        )


def test_feasibility_evaluator_covers_all_four_coursepilot_states() -> None:
    demand = LessonDemandBuilder.build(
        course_id="course-1",
        params=LessonGenerationParams(chapter_range="Chapter 1", total_sessions=2),
        context=DemandBuildContext(knowledge_point_ids=["kp-1"]),
    )

    feasible = FeasibilityEvaluator.evaluate(demand, _rich_snapshot(demand))
    thin = FeasibilityEvaluator.evaluate(
        demand,
        AdequacySnapshot(
            status=AdequacyStatus.NEEDS_MORE_EVIDENCE,
            distinct_sources=0,
            distinct_semantic_units=1,
            supplement_allowed=True,
        ),
    )
    reduced = FeasibilityEvaluator.evaluate(
        demand,
        AdequacySnapshot(
            status=AdequacyStatus.UNRESOLVABLE,
            distinct_sources=1,
            distinct_semantic_units=2,
            supported_target_unit_count=1,
        ),
    )
    human = FeasibilityEvaluator.evaluate(
        demand,
        AdequacySnapshot(
            status=AdequacyStatus.UNRESOLVABLE,
            distinct_sources=0,
            distinct_semantic_units=0,
            supported_target_unit_count=0,
        ),
    )

    assert (feasible.status, feasible.action, feasible.generation_allowed) == (
        FeasibilityStatus.FEASIBLE,
        FeasibilityAction.PROCEED_GENERATION,
        True,
    )
    assert thin.status is FeasibilityStatus.NEEDS_MORE_EVIDENCE
    assert reduced.status is FeasibilityStatus.SCOPE_REDUCTION_REQUIRED
    assert reduced.suggested_target_unit_count == 1
    assert human.status is FeasibilityStatus.NEEDS_HUMAN_REVIEW


def test_adequate_with_missing_capacity_is_a_contract_inconsistency() -> None:
    demand = LessonDemandBuilder.build(
        course_id="course-1",
        params=LessonGenerationParams(chapter_range="Chapter 1"),
    )
    decision = FeasibilityEvaluator.evaluate(
        demand,
        AdequacySnapshot(
            status=AdequacyStatus.ADEQUATE,
            distinct_sources=0,
            distinct_semantic_units=0,
        ),
    )
    assert decision.status is FeasibilityStatus.NEEDS_HUMAN_REVIEW
    assert FeasibilityReasonCode.ADEQUACY_CONTRACT_INCONSISTENT in decision.reason_codes


def test_character_count_is_warning_only_and_reason_order_is_deterministic() -> None:
    demand = LessonDemandBuilder.build(
        course_id="course-1",
        params=LessonGenerationParams(chapter_range="Chapter 1"),
        context=DemandBuildContext(knowledge_point_ids=["kp-1", "kp-2"]),
    )
    first = FeasibilityEvaluator.evaluate(
        demand,
        _rich_snapshot(demand, low_character_warning=True),
    )
    second_snapshot = _rich_snapshot(demand, low_character_warning=True)
    second = FeasibilityEvaluator.evaluate(
        demand,
        second_snapshot.model_copy(
            update={
                "knowledge_point_unit_counts": dict(
                    reversed(list(second_snapshot.knowledge_point_unit_counts.items()))
                ),
                "requirement_unit_counts": dict(
                    reversed(list(second_snapshot.requirement_unit_counts.items()))
                ),
            }
        ),
    )

    assert first.status is FeasibilityStatus.FEASIBLE
    assert first.reason_codes == [FeasibilityReasonCode.LOW_CHARACTER_COUNT_WARNING]
    assert first == second


def test_production_feasibility_modules_do_not_import_evaluation_package() -> None:
    root = Path(__file__).resolve().parents[3] / "src/coursepilot"
    paths = [
        root / "domain/feasibility.py",
        root / "application/feasibility_service.py",
    ]
    assert all("evaluation.system_optimization" not in path.read_text("utf-8") for path in paths)
