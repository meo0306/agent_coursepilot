from __future__ import annotations

from math import ceil, floor

from coursepilot.domain.feasibility import (
    AdequacySnapshot,
    AdequacyStatus,
    ArtifactDemand,
    ArtifactTargetUnit,
    DemandBuildContext,
    FeasibilityAction,
    FeasibilityDecision,
    FeasibilityReasonCode,
    FeasibilityStatus,
    MaterialType,
    PPTLessonDemandContext,
    SemanticUnitRequirement,
    SemanticUnitRole,
)
from coursepilot.domain.task import WorkflowType
from coursepilot.schemas.exam_schema import ExamGenerationParams
from coursepilot.schemas.lesson_schema import LessonGenerationParams
from coursepilot.schemas.ppt_schema import PPTGenerationParams


class DemandBuildError(ValueError):
    pass


class LessonDemandBuilder:
    @staticmethod
    def build(
        *,
        course_id: str,
        params: LessonGenerationParams,
        context: DemandBuildContext | None = None,
    ) -> ArtifactDemand:
        build_context = context or DemandBuildContext()
        sessions = params.total_sessions
        half_sessions = ceil(sessions / 2)
        requirements = [
            _role_requirement("lesson.definition", sessions, SemanticUnitRole.DEFINITION),
            _role_requirement("lesson.example", sessions, SemanticUnitRole.EXAMPLE),
            _role_requirement("lesson.process", half_sessions, SemanticUnitRole.PROCESS),
        ]
        if params.include_interaction or params.include_homework:
            requirements.append(
                _role_requirement(
                    "lesson.application_context",
                    half_sessions,
                    SemanticUnitRole.APPLICATION_CONTEXT,
                )
            )
        requirements = _merge_requirements(requirements, build_context.additional_requirements)
        base_requirement_ids = {
            "lesson.definition",
            "lesson.example",
            "lesson.process",
            "lesson.application_context",
        }
        minimum_semantic_units = sum(
            item.minimum_count
            for item in requirements
            if item.required and item.requirement_id in base_requirement_ids
        )
        scope_label = params.chapter_range.strip()
        if params.teaching_focus and params.teaching_focus.strip():
            scope_label = f"{scope_label} | focus: {params.teaching_focus.strip()}"
        audience = _lesson_audience(params)
        return ArtifactDemand(
            course_id=course_id,
            artifact_type=WorkflowType.LESSON,
            scope_label=scope_label,
            target_unit=ArtifactTargetUnit.SESSIONS,
            target_unit_count=sessions,
            minimum_viable_unit_count=1,
            knowledge_point_ids=build_context.knowledge_point_ids,
            minimum_units_per_knowledge_point=1 if build_context.knowledge_point_ids else 0,
            minimum_distinct_sources=_clamp(ceil(minimum_semantic_units / 4), 1, 3),
            minimum_semantic_units=minimum_semantic_units,
            semantic_requirements=requirements,
            audience=audience,
        )


class ExamDemandBuilder:
    @staticmethod
    def build(
        *,
        course_id: str,
        params: ExamGenerationParams,
        context: DemandBuildContext | None = None,
    ) -> ArtifactDemand:
        build_context = context or DemandBuildContext()
        question_count = sum(params.question_counts.values())
        difficulty_profile, difficulty_counts = _exam_difficulty(
            params.difficulty_distribution,
            question_count,
        )
        single_choice_count = params.question_counts.get("single_choice", 0)
        multiple_choice_count = params.question_counts.get("multiple_choice", 0)
        judgement_count = params.question_counts.get("judgement", 0)
        short_answer_count = params.question_counts.get("short_answer", 0)
        requirements = [
            _role_requirement(
                "exam.definition",
                max(1, ceil(single_choice_count / 2)),
                SemanticUnitRole.DEFINITION,
            ),
            _role_requirement(
                "exam.principle",
                max(judgement_count, ceil(difficulty_counts["medium"] / 2), 1),
                SemanticUnitRole.PRINCIPLE,
            ),
        ]
        if multiple_choice_count:
            requirements.append(
                _role_requirement(
                    "exam.comparison",
                    ceil(multiple_choice_count / 2),
                    SemanticUnitRole.COMPARISON,
                )
            )
        if short_answer_count:
            requirements.append(
                _role_requirement(
                    "exam.process",
                    ceil(short_answer_count / 2),
                    SemanticUnitRole.PROCESS,
                )
            )
        application_count = short_answer_count + difficulty_counts["hard"]
        if application_count:
            requirements.append(
                _role_requirement(
                    "exam.application_context",
                    application_count,
                    SemanticUnitRole.APPLICATION_CONTEXT,
                )
            )
        requirements = _merge_requirements(requirements, build_context.additional_requirements)
        minimum_semantic_units = question_count + difficulty_counts["hard"]
        return ArtifactDemand(
            course_id=course_id,
            artifact_type=WorkflowType.EXAM,
            scope_label=params.chapter_range.strip(),
            target_unit=ArtifactTargetUnit.QUESTIONS,
            target_unit_count=question_count,
            minimum_viable_unit_count=1,
            knowledge_point_ids=build_context.knowledge_point_ids,
            minimum_units_per_knowledge_point=1 if build_context.knowledge_point_ids else 0,
            minimum_distinct_sources=_clamp(ceil(question_count / 5), 1, 5),
            minimum_semantic_units=minimum_semantic_units,
            semantic_requirements=requirements,
            difficulty_profile=difficulty_profile,
        )


class PPTDemandBuilder:
    @staticmethod
    def build(
        *,
        course_id: str,
        params: PPTGenerationParams,
        lesson: PPTLessonDemandContext,
        context: DemandBuildContext | None = None,
    ) -> ArtifactDemand:
        build_context = context or DemandBuildContext()
        target_count = params.slide_count
        if target_count is None:
            target_count = 1 + (lesson.total_sessions * 2) + int(params.include_references)
        content_slide_count = max(1, target_count - 1 - int(params.include_references))
        role_count = max(1, ceil(content_slide_count / 3))
        requirements = [
            _role_requirement("ppt.definition", role_count, SemanticUnitRole.DEFINITION),
            _role_requirement("ppt.example", role_count, SemanticUnitRole.EXAMPLE),
            SemanticUnitRequirement(
                requirement_id="ppt.visual_relationship",
                minimum_count=role_count,
                material_types=[MaterialType.VISUAL_RELATIONSHIP],
            ),
        ]
        if content_slide_count >= 3:
            requirements.append(_role_requirement("ppt.process", 1, SemanticUnitRole.PROCESS))
        if content_slide_count >= 4:
            requirements.append(_role_requirement("ppt.comparison", 1, SemanticUnitRole.COMPARISON))
        if content_slide_count >= 5:
            requirements.append(
                _role_requirement(
                    "ppt.application_context",
                    1,
                    SemanticUnitRole.APPLICATION_CONTEXT,
                )
            )
        requirements = _merge_requirements(requirements, build_context.additional_requirements)
        role_minimum = sum(
            item.minimum_count for item in requirements if item.roles and item.required
        )
        knowledge_point_ids = sorted(
            set(lesson.knowledge_point_ids) | set(build_context.knowledge_point_ids)
        )
        return ArtifactDemand(
            course_id=course_id,
            artifact_type=WorkflowType.PPT,
            scope_label=lesson.chapter_scope.strip(),
            source_artifact_id=lesson.lesson_id,
            target_unit=ArtifactTargetUnit.SLIDES,
            target_unit_count=target_count,
            minimum_viable_unit_count=3,
            knowledge_point_ids=knowledge_point_ids,
            minimum_units_per_knowledge_point=1 if knowledge_point_ids else 0,
            minimum_distinct_sources=_clamp(ceil(content_slide_count / 4), 1, 4),
            minimum_semantic_units=max(content_slide_count, role_minimum),
            semantic_requirements=requirements,
        )


class FeasibilityEvaluator:
    @staticmethod
    def evaluate(demand: ArtifactDemand, adequacy: AdequacySnapshot) -> FeasibilityDecision:
        return evaluate_feasibility(demand, adequacy)


def evaluate_feasibility(
    demand: ArtifactDemand,
    adequacy: AdequacySnapshot,
) -> FeasibilityDecision:
    missing_kps = sorted(
        knowledge_point_id
        for knowledge_point_id in demand.knowledge_point_ids
        if adequacy.knowledge_point_unit_counts.get(knowledge_point_id, 0)
        < demand.minimum_units_per_knowledge_point
    )
    missing_requirements = sorted(
        requirement.requirement_id
        for requirement in demand.semantic_requirements
        if requirement.required
        and adequacy.requirement_unit_counts.get(requirement.requirement_id, 0)
        < requirement.minimum_count
    )
    source_gap = adequacy.distinct_sources < demand.minimum_distinct_sources
    semantic_gap = adequacy.distinct_semantic_units < demand.minimum_semantic_units
    has_gap = bool(missing_kps or missing_requirements or source_gap or semantic_gap)

    reasons: set[FeasibilityReasonCode] = set()
    if missing_kps:
        reasons.add(FeasibilityReasonCode.KNOWLEDGE_POINT_COVERAGE_MISSING)
    if missing_requirements:
        reasons.add(FeasibilityReasonCode.SEMANTIC_REQUIREMENT_MISSING)
    if source_gap:
        reasons.add(FeasibilityReasonCode.DISTINCT_SOURCE_CAPACITY_INSUFFICIENT)
    if semantic_gap:
        reasons.add(FeasibilityReasonCode.SEMANTIC_UNIT_CAPACITY_INSUFFICIENT)
    warnings: list[str] = []
    if adequacy.low_character_count_warning:
        reasons.add(FeasibilityReasonCode.LOW_CHARACTER_COUNT_WARNING)
        warnings.append(FeasibilityReasonCode.LOW_CHARACTER_COUNT_WARNING.value)

    supported = adequacy.supported_target_unit_count
    if adequacy.status is AdequacyStatus.ADEQUATE:
        if has_gap or (supported is not None and supported < demand.target_unit_count):
            reasons.add(FeasibilityReasonCode.ADEQUACY_CONTRACT_INCONSISTENT)
            return _decision(
                status=FeasibilityStatus.NEEDS_HUMAN_REVIEW,
                reasons=reasons,
                missing_requirements=missing_requirements,
                missing_kps=missing_kps,
                warnings=warnings,
            )
        return _decision(
            status=FeasibilityStatus.FEASIBLE,
            reasons=reasons,
            missing_requirements=[],
            missing_kps=[],
            warnings=warnings,
        )

    if adequacy.status is AdequacyStatus.NEEDS_MORE_EVIDENCE:
        reasons.add(FeasibilityReasonCode.ADEQUACY_NEEDS_MORE_EVIDENCE)
        if adequacy.supplement_allowed:
            return _decision(
                status=FeasibilityStatus.NEEDS_MORE_EVIDENCE,
                reasons=reasons,
                missing_requirements=missing_requirements,
                missing_kps=missing_kps,
                warnings=warnings,
            )
    else:
        reasons.add(FeasibilityReasonCode.ADEQUACY_UNRESOLVABLE)

    if (
        supported is not None
        and demand.minimum_viable_unit_count <= supported < demand.target_unit_count
    ):
        reasons.add(FeasibilityReasonCode.SCOPE_CAN_BE_REDUCED)
        return _decision(
            status=FeasibilityStatus.SCOPE_REDUCTION_REQUIRED,
            reasons=reasons,
            missing_requirements=missing_requirements,
            missing_kps=missing_kps,
            warnings=warnings,
            suggested_target=supported,
        )

    if supported is not None and supported >= demand.target_unit_count:
        reasons.add(FeasibilityReasonCode.ADEQUACY_CONTRACT_INCONSISTENT)
    else:
        reasons.add(FeasibilityReasonCode.MINIMUM_VIABLE_SCOPE_UNSUPPORTED)
    return _decision(
        status=FeasibilityStatus.NEEDS_HUMAN_REVIEW,
        reasons=reasons,
        missing_requirements=missing_requirements,
        missing_kps=missing_kps,
        warnings=warnings,
    )


_REASON_PRIORITY = {reason: index for index, reason in enumerate(FeasibilityReasonCode)}


def _decision(
    *,
    status: FeasibilityStatus,
    reasons: set[FeasibilityReasonCode],
    missing_requirements: list[str],
    missing_kps: list[str],
    warnings: list[str],
    suggested_target: int | None = None,
) -> FeasibilityDecision:
    action = {
        FeasibilityStatus.FEASIBLE: FeasibilityAction.PROCEED_GENERATION,
        FeasibilityStatus.NEEDS_MORE_EVIDENCE: FeasibilityAction.REQUEST_MORE_EVIDENCE,
        FeasibilityStatus.SCOPE_REDUCTION_REQUIRED: FeasibilityAction.OFFER_SCOPE_REDUCTION,
        FeasibilityStatus.NEEDS_HUMAN_REVIEW: FeasibilityAction.REQUEST_HUMAN_REVIEW,
    }[status]
    return FeasibilityDecision(
        status=status,
        action=action,
        reason_codes=sorted(reasons, key=_REASON_PRIORITY.__getitem__),
        missing_requirement_ids=sorted(missing_requirements),
        missing_knowledge_point_ids=sorted(missing_kps),
        suggested_target_unit_count=suggested_target,
        warnings=sorted(warnings),
    )


def _role_requirement(
    requirement_id: str,
    minimum_count: int,
    role: SemanticUnitRole,
) -> SemanticUnitRequirement:
    return SemanticUnitRequirement(
        requirement_id=requirement_id,
        minimum_count=minimum_count,
        roles=[role],
    )


def _merge_requirements(
    base: list[SemanticUnitRequirement],
    additional: list[SemanticUnitRequirement],
) -> list[SemanticUnitRequirement]:
    base_ids = {item.requirement_id for item in base}
    collisions = sorted(base_ids & {item.requirement_id for item in additional})
    if collisions:
        raise DemandBuildError(f"duplicate semantic requirement ID: {collisions[0]}")
    return sorted([*base, *additional], key=lambda item: item.requirement_id)


def _lesson_audience(params: LessonGenerationParams) -> str | None:
    level = params.student_level.strip() if params.student_level else ""
    background = params.student_background.strip() if params.student_background else ""
    if level and background:
        return f"{level}; background: {background}"
    return level or background or None


def _exam_difficulty(
    raw_profile: dict[str, float],
    question_count: int,
) -> tuple[dict[str, float], dict[str, int]]:
    order = ("easy", "medium", "hard")
    unknown = sorted(set(raw_profile) - set(order))
    if unknown:
        raise DemandBuildError(f"unsupported difficulty key: {unknown[0]}")
    weights = {key: float(raw_profile.get(key, 0.0)) for key in order}
    if any(value < 0 for value in weights.values()):
        raise DemandBuildError("difficulty weights cannot be negative")
    total = sum(weights.values())
    if total <= 0:
        raise DemandBuildError("difficulty weights must contain a positive value")
    profile = {key: weights[key] / total for key in order}
    exact = {key: profile[key] * question_count for key in order}
    counts = {key: floor(exact[key]) for key in order}
    remainder = question_count - sum(counts.values())
    ranked = sorted(order, key=lambda key: (-(exact[key] - counts[key]), order.index(key)))
    for key in ranked[:remainder]:
        counts[key] += 1
    return profile, counts


def _clamp(value: int, lower: int, upper: int) -> int:
    return max(lower, min(value, upper))
