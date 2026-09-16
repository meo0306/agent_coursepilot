from __future__ import annotations

from coursepilot.domain.feasibility import (
    AdequacySnapshot,
    AdequacyStatus,
    ArtifactDemand,
)
from courserag.contracts import (
    ContextAdequacyReport,
    GenerationArtifactType,
    GenerationContextBoundary,
    GenerationContextRequest,
    GenerationContextRequirements,
    GenerationMaterialType,
    GenerationSemanticRequirement,
    GenerationSemanticRole,
    KnowledgePointCoverageRequirement,
    RequestContext,
)


def artifact_demand_to_generation_context_request(
    demand: ArtifactDemand,
    *,
    context: RequestContext,
    max_context_tokens: int = 4000,
    max_context_items: int = 8,
    supplement_round: int = 0,
    max_supplement_rounds: int = 1,
    boundary: GenerationContextBoundary | None = None,
) -> GenerationContextRequest:
    requirements = GenerationContextRequirements(
        artifact_type=GenerationArtifactType(demand.artifact_type.value),
        target_unit_count=demand.target_unit_count,
        knowledge_point_requirements=[
            KnowledgePointCoverageRequirement(
                knowledge_point_id=knowledge_point_id,
                minimum_semantic_units=demand.minimum_units_per_knowledge_point,
            )
            for knowledge_point_id in demand.knowledge_point_ids
        ],
        semantic_requirements=[
            GenerationSemanticRequirement(
                requirement_id=requirement.requirement_id,
                minimum_count=requirement.minimum_count,
                roles=[GenerationSemanticRole(role.value) for role in requirement.roles],
                material_types=[
                    GenerationMaterialType(material.value)
                    for material in requirement.material_types
                ],
                knowledge_point_ids=requirement.knowledge_point_ids,
                required=requirement.required,
            )
            for requirement in sorted(
                demand.semantic_requirements, key=lambda item: item.requirement_id
            )
        ],
        minimum_distinct_sources=demand.minimum_distinct_sources,
        minimum_semantic_units=demand.minimum_semantic_units,
        max_context_tokens=max_context_tokens,
        max_context_items=max_context_items,
        supplement_round=supplement_round,
        max_supplement_rounds=max_supplement_rounds,
        boundary=boundary or GenerationContextBoundary(),
    )
    return GenerationContextRequest(
        context=context,
        course_id=demand.course_id,
        query=demand.scope_label,
        requirements=requirements,
    )


def adequacy_report_to_snapshot(report: ContextAdequacyReport) -> AdequacySnapshot:
    return AdequacySnapshot(
        status=AdequacyStatus(report.status.value),
        knowledge_point_unit_counts={
            item.requirement_id: item.available_count for item in report.knowledge_point_results
        },
        requirement_unit_counts={
            item.requirement_id: item.available_count for item in report.requirement_results
        },
        distinct_sources=report.distinct_sources,
        distinct_semantic_units=report.distinct_semantic_units,
        supplement_allowed=report.supplement_allowed,
        supported_target_unit_count=report.supported_target_unit_count,
        low_character_count_warning="low_character_count_warning" in report.warning_codes,
    )
