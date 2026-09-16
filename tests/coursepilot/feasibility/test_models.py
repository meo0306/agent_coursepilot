import pytest
from pydantic import ValidationError

from coursepilot.domain import (
    ArtifactDemand,
    ArtifactTargetUnit,
    FeasibilityAction,
    FeasibilityDecision,
    FeasibilityStatus,
    SemanticUnitRequirement,
    SemanticUnitRole,
    WorkflowType,
)


def _lesson_demand(**updates: object) -> ArtifactDemand:
    values: dict[str, object] = {
        "course_id": "course-1",
        "artifact_type": WorkflowType.LESSON,
        "scope_label": "Chapter 1",
        "target_unit": ArtifactTargetUnit.SESSIONS,
        "target_unit_count": 2,
        "minimum_viable_unit_count": 1,
        "minimum_distinct_sources": 1,
        "minimum_semantic_units": 2,
        "semantic_requirements": [
            SemanticUnitRequirement(
                requirement_id="lesson.definition",
                minimum_count=2,
                roles=[SemanticUnitRole.DEFINITION],
            )
        ],
    }
    values.update(updates)
    return ArtifactDemand.model_validate(values)


def test_artifact_demand_enforces_unit_scope_and_extra_field_boundaries() -> None:
    demand = _lesson_demand()
    assert demand.target_unit is ArtifactTargetUnit.SESSIONS

    with pytest.raises(ValidationError, match="target unit must match"):
        _lesson_demand(target_unit=ArtifactTargetUnit.QUESTIONS)
    with pytest.raises(ValidationError, match="minimum viable unit count exceeds"):
        _lesson_demand(minimum_viable_unit_count=3)
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        _lesson_demand(chunk_ids=["chunk-1"])


def test_semantic_requirement_requires_a_role_or_material_and_canonical_ids() -> None:
    with pytest.raises(ValidationError, match="needs a role or material"):
        SemanticUnitRequirement(requirement_id="empty", minimum_count=1)
    with pytest.raises(ValidationError, match="knowledge_point_ids must be sorted"):
        SemanticUnitRequirement(
            requirement_id="definition",
            minimum_count=1,
            roles=[SemanticUnitRole.DEFINITION],
            knowledge_point_ids=["kp-2", "kp-1"],
        )


def test_exam_demand_requires_normalized_complete_difficulty_profile() -> None:
    with pytest.raises(ValidationError, match="requires easy, medium and hard"):
        ArtifactDemand(
            course_id="course-1",
            artifact_type=WorkflowType.EXAM,
            scope_label="Chapter 1",
            target_unit=ArtifactTargetUnit.QUESTIONS,
            target_unit_count=2,
            minimum_viable_unit_count=1,
            minimum_distinct_sources=1,
            minimum_semantic_units=2,
            semantic_requirements=[
                SemanticUnitRequirement(
                    requirement_id="exam.definition",
                    minimum_count=1,
                    roles=[SemanticUnitRole.DEFINITION],
                )
            ],
            difficulty_profile={"easy": 1.0},
        )


def test_feasibility_decision_enforces_status_action_contract() -> None:
    with pytest.raises(ValidationError, match="status and action are inconsistent"):
        FeasibilityDecision(
            status=FeasibilityStatus.FEASIBLE,
            action=FeasibilityAction.REQUEST_HUMAN_REVIEW,
        )
    with pytest.raises(ValidationError, match="requires a suggested target"):
        FeasibilityDecision(
            status=FeasibilityStatus.SCOPE_REDUCTION_REQUIRED,
            action=FeasibilityAction.OFFER_SCOPE_REDUCTION,
        )

    decision = FeasibilityDecision(
        status=FeasibilityStatus.FEASIBLE,
        action=FeasibilityAction.PROCEED_GENERATION,
    )
    assert decision.generation_allowed
