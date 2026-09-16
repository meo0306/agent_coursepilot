from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from coursepilot.domain.common import DomainModel


class AllocationImportance(StrEnum):
    CORE = "core"
    SUPPORTING = "supporting"
    OPTIONAL = "optional"


class LessonEvidenceBinding(DomainModel):
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    requires_evidence: bool = True


class KnowledgePointAllocation(DomainModel):
    knowledge_point_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    importance: AllocationImportance = AllocationImportance.CORE
    evidence_ids: list[str] = Field(default_factory=list)
    session_indices: list[int] = Field(default_factory=list)


class LessonActivity(DomainModel):
    activity_id: str = Field(min_length=1)
    activity_type: str = Field(min_length=1)
    title: str = Field(min_length=1)
    minutes: int = Field(gt=0)
    objective_ids: list[str] = Field(default_factory=list)
    binding: LessonEvidenceBinding = Field(default_factory=LessonEvidenceBinding)
    instructions: str = ""


class LessonSessionBlueprint(DomainModel):
    session_id: str = Field(min_length=1)
    session_index: int = Field(ge=1)
    title: str = Field(min_length=1)
    duration_minutes: int = Field(gt=0)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    objective_types: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    difficult_points: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    required_activity_types: list[str] = Field(default_factory=list)
    activities: list[LessonActivity] = Field(default_factory=list)
    predecessor_session_ids: list[str] = Field(default_factory=list)


class LessonBlueprint(DomainModel):
    course_id: str = Field(min_length=1)
    chapter_scope: str = Field(min_length=1)
    total_sessions: int = Field(gt=0)
    session_duration: int = Field(gt=0)
    selected_knowledge_points: list[KnowledgePointAllocation] = Field(default_factory=list)
    session_plans: list[LessonSessionBlueprint] = Field(default_factory=list)
    coverage_policy: str = "all_core"
    template_snapshot_id: str = Field(min_length=1)
    context_package_id: str = Field(min_length=1)
    context_evidence_ids: list[str] = Field(default_factory=list)


class LessonFact(DomainModel):
    fact_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    binding: LessonEvidenceBinding


class LessonSessionArtifact(DomainModel):
    session_id: str = Field(min_length=1)
    session_index: int = Field(ge=1)
    title: str = Field(min_length=1)
    objectives: list[str] = Field(default_factory=list)
    activities: list[LessonActivity] = Field(default_factory=list)
    key_points: list[LessonFact] = Field(default_factory=list)
    difficult_points: list[LessonFact] = Field(default_factory=list)
    homework: list[str] = Field(default_factory=list)
    terminology: list[str] = Field(default_factory=list)


class LessonArtifact(DomainModel):
    course_id: str = Field(min_length=1)
    chapter_scope: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    blueprint: LessonBlueprint
    sessions: list[LessonSessionArtifact] = Field(default_factory=list)
