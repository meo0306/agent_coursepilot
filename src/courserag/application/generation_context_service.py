from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from math import floor
from typing import Protocol

from courserag.contracts import (
    AdequacyCoverageResult,
    ContextAdequacyReport,
    ContextAdequacyStatus,
    ContextPackage,
    ContextPackingOptions,
    ContextRequest,
    CourseRAGError,
    ErrorCode,
    GenerationContextRequest,
    GenerationContextResponse,
    GenerationMaterialType,
    GenerationSemanticRequirement,
    GenerationSemanticRole,
    ResponseMeta,
    SearchFilters,
    SearchRequest,
    SourceTier,
    SupplementRetrievalSuggestion,
)


@dataclass(frozen=True)
class GenerationEvidenceMetadata:
    evidence_id: str
    course_id: str
    document_id: str
    document_version_id: str
    source_tier: SourceTier
    roles: frozenset[GenerationSemanticRole] = frozenset()
    material_types: frozenset[GenerationMaterialType] = frozenset()
    knowledge_point_ids: frozenset[str] = frozenset()
    previous_evidence_id: str | None = None
    next_evidence_id: str | None = None


class GenerationEvidenceMetadataProvider(Protocol):
    def batch_resolve(
        self, course_id: str, evidence_ids: list[str]
    ) -> list[GenerationEvidenceMetadata]: ...

    def known_knowledge_point_ids(self, course_id: str) -> set[str]: ...


class GenerationContextService:
    """Build one context package, then assess it without LLM or text heuristics."""

    def __init__(
        self,
        *,
        build_context: Callable[[ContextRequest], ContextPackage],
        metadata_provider: GenerationEvidenceMetadataProvider,
    ) -> None:
        self._build_context = build_context
        self._metadata_provider = metadata_provider

    def build(self, request: GenerationContextRequest) -> GenerationContextResponse:
        boundary = request.requirements.boundary
        context_request = ContextRequest(
            context=request.context,
            course_id=request.course_id,
            query=request.query,
            purpose=f"generation:{request.requirements.artifact_type.value}",
            search_request=SearchRequest(
                context=request.context,
                course_id=request.course_id,
                query=request.query,
                filters=SearchFilters(
                    document_ids=boundary.document_ids,
                    document_version_ids=boundary.document_version_ids,
                    knowledge_point_ids=[
                        item.knowledge_point_id
                        for item in request.requirements.knowledge_point_requirements
                    ],
                    index_version=boundary.required_index_version,
                    source_tiers=boundary.allowed_source_tiers,
                ),
            ),
            packing=ContextPackingOptions(
                max_tokens=request.requirements.max_context_tokens,
                max_items=request.requirements.max_context_items,
            ),
        )
        context = self._build_context(context_request)
        self._validate_context_boundary(request, context)
        evidence_ids = sorted(
            {evidence_id for item in context.items for evidence_id in item.evidence_ids}
            | set(context.evidence_map)
        )
        metadata = self._metadata_provider.batch_resolve(request.course_id, evidence_ids)
        facts = _validated_metadata(request, evidence_ids, metadata)
        report = assess_context_adequacy(
            request=request,
            context=context,
            facts=facts,
            known_knowledge_point_ids=self._metadata_provider.known_knowledge_point_ids(
                request.course_id
            ),
        )
        return GenerationContextResponse(
            meta=ResponseMeta.from_context(request.context),
            context=context,
            adequacy=report,
        )

    @staticmethod
    def _validate_context_boundary(
        request: GenerationContextRequest, context: ContextPackage
    ) -> None:
        requirements = request.requirements
        boundary = requirements.boundary
        if boundary.required_index_version and (
            context.index_version != boundary.required_index_version
        ):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.VERSION_CONFLICT,
                message="Generation Context index version differs from the requested boundary.",
                details={
                    "required_index_version": boundary.required_index_version,
                    "actual_index_version": context.index_version,
                },
            )
        if boundary.required_overlay_version and (
            context.verified_overlay_version != boundary.required_overlay_version
        ):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.VERSION_CONFLICT,
                message="Generation Context overlay version differs from the requested boundary.",
                details={
                    "required_overlay_version": boundary.required_overlay_version,
                    "actual_overlay_version": context.verified_overlay_version,
                },
            )
        if len(context.items) > requirements.max_context_items or (
            context.token_count > requirements.max_context_tokens
        ):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.INTERNAL_ERROR,
                message="Generation Context builder exceeded the requested packing budget.",
            )


def assess_context_adequacy(
    *,
    request: GenerationContextRequest,
    context: ContextPackage,
    facts: dict[str, GenerationEvidenceMetadata],
    known_knowledge_point_ids: set[str],
) -> ContextAdequacyReport:
    requirements = request.requirements
    selected_ids = set(facts)
    role_counts = {
        role: sum(role in fact.roles for fact in facts.values()) for role in GenerationSemanticRole
    }
    material_counts = {
        material: sum(material in fact.material_types for fact in facts.values())
        for material in GenerationMaterialType
    }

    kp_results: list[AdequacyCoverageResult] = []
    unknown_kps: list[str] = []
    for requirement in requirements.knowledge_point_requirements:
        evidence_ids = sorted(
            fact.evidence_id
            for fact in facts.values()
            if requirement.knowledge_point_id in fact.knowledge_point_ids
        )
        if requirement.knowledge_point_id not in known_knowledge_point_ids:
            unknown_kps.append(requirement.knowledge_point_id)
            evidence_ids = []
        kp_results.append(
            AdequacyCoverageResult(
                requirement_id=requirement.knowledge_point_id,
                required_count=requirement.minimum_semantic_units,
                available_count=len(evidence_ids),
                satisfied=len(evidence_ids) >= requirement.minimum_semantic_units,
                evidence_ids=evidence_ids,
            )
        )

    semantic_results = [
        _semantic_result(requirement, facts.values())
        for requirement in requirements.semantic_requirements
    ]
    required_semantic = {
        requirement.requirement_id: requirement.required
        for requirement in requirements.semantic_requirements
    }
    missing_kps = sorted(item.requirement_id for item in kp_results if not item.satisfied)
    missing_semantic = sorted(
        item.requirement_id
        for item in semantic_results
        if required_semantic[item.requirement_id] and not item.satisfied
    )
    distinct_sources = len(
        {(fact.document_id, fact.document_version_id) for fact in facts.values()}
    )
    distinct_units = len(facts)
    global_missing: list[str] = []
    if distinct_sources < requirements.minimum_distinct_sources:
        global_missing.append("minimum_distinct_sources")
    if distinct_units < requirements.minimum_semantic_units:
        global_missing.append("minimum_semantic_units")
    missing_requirement_ids = sorted(missing_semantic + global_missing)

    hard_gap = bool(missing_kps or missing_requirement_ids)
    supplement_allowed = (
        hard_gap and requirements.supplement_round < requirements.max_supplement_rounds
    )
    if not hard_gap:
        status = ContextAdequacyStatus.ADEQUATE
    elif unknown_kps or not supplement_allowed:
        status = ContextAdequacyStatus.UNRESOLVABLE
    else:
        status = ContextAdequacyStatus.NEEDS_MORE_EVIDENCE

    reason_codes: list[str] = []
    if unknown_kps:
        reason_codes.append("unknown_knowledge_point")
    if missing_kps:
        reason_codes.append("knowledge_point_coverage_missing")
    if missing_semantic:
        reason_codes.append("semantic_requirement_missing")
    if "minimum_distinct_sources" in global_missing:
        reason_codes.append("distinct_source_capacity_insufficient")
    if "minimum_semantic_units" in global_missing:
        reason_codes.append("semantic_unit_capacity_insufficient")
    if status is ContextAdequacyStatus.NEEDS_MORE_EVIDENCE:
        reason_codes.append("adequacy_needs_more_evidence")
    elif status is ContextAdequacyStatus.UNRESOLVABLE:
        reason_codes.append("adequacy_unresolvable")

    complete_groups, incomplete_groups = _group_counts(facts.values(), selected_ids)
    packing = context.packing_report
    warnings = sorted(set(context.meta.warnings + packing.warnings))
    return ContextAdequacyReport(
        status=status,
        reason_codes=reason_codes,
        warning_codes=warnings,
        knowledge_point_results=kp_results,
        requirement_results=semantic_results,
        semantic_role_counts=role_counts,
        material_type_counts=material_counts,
        evidence_count=len(facts),
        distinct_semantic_units=distinct_units,
        distinct_sources=distinct_sources,
        complete_evidence_group_count=complete_groups,
        incomplete_evidence_group_count=incomplete_groups,
        selected_item_count=len(context.items),
        selected_evidence_count=packing.selected_evidence_count or len(selected_ids),
        token_count=context.token_count,
        token_budget=min(
            requirements.max_context_tokens,
            packing.token_budget or requirements.max_context_tokens,
        ),
        discarded_for_budget=packing.discarded_for_budget,
        discarded_for_item_limit=packing.discarded_for_item_limit,
        discarded_for_token_limit=packing.discarded_for_token_limit,
        parent_expansion_count=packing.parent_expansion_count,
        neighbor_expansion_count=packing.neighbor_expansion_count,
        missing_requirement_ids=missing_requirement_ids,
        missing_knowledge_point_ids=missing_kps,
        supported_target_unit_count=_supported_target_units(
            request,
            kp_results,
            semantic_results,
            required_semantic,
            distinct_sources,
            distinct_units,
        ),
        supplement_allowed=supplement_allowed,
        supplement_suggestions=_supplement_suggestions(
            request,
            missing_kps,
            missing_semantic,
            global_missing,
        ),
    )


def _validated_metadata(
    request: GenerationContextRequest,
    evidence_ids: list[str],
    metadata: list[GenerationEvidenceMetadata],
) -> dict[str, GenerationEvidenceMetadata]:
    facts = {item.evidence_id: item for item in metadata}
    if len(facts) != len(metadata) or set(facts) != set(evidence_ids):
        raise CourseRAGError(
            context=request.context,
            code=ErrorCode.INTERNAL_ERROR,
            message="Generation Context Evidence metadata is incomplete or duplicated.",
        )
    boundary = request.requirements.boundary
    for fact in facts.values():
        if fact.course_id != request.course_id:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message="Generation Context contains Evidence from another course.",
            )
        if boundary.allowed_source_tiers and fact.source_tier not in set(
            boundary.allowed_source_tiers
        ):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message="Generation Context contains an Evidence tier outside the boundary.",
            )
        if boundary.document_ids and fact.document_id not in set(boundary.document_ids):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message="Generation Context contains a document outside the boundary.",
            )
        if boundary.document_version_ids and fact.document_version_id not in set(
            boundary.document_version_ids
        ):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.VERSION_CONFLICT,
                message="Generation Context contains a document version outside the boundary.",
            )
    return facts


def _semantic_result(
    requirement: GenerationSemanticRequirement,
    facts: Iterable[GenerationEvidenceMetadata],
) -> AdequacyCoverageResult:
    evidence_ids = sorted(
        fact.evidence_id
        for fact in facts
        if (not requirement.roles or set(requirement.roles) & fact.roles)
        and (
            not requirement.material_types or set(requirement.material_types) & fact.material_types
        )
        and (
            not requirement.knowledge_point_ids
            or set(requirement.knowledge_point_ids) & fact.knowledge_point_ids
        )
    )
    return AdequacyCoverageResult(
        requirement_id=requirement.requirement_id,
        required_count=requirement.minimum_count,
        available_count=len(evidence_ids),
        satisfied=len(evidence_ids) >= requirement.minimum_count,
        evidence_ids=evidence_ids,
    )


def _group_counts(
    facts: Iterable[GenerationEvidenceMetadata], selected_ids: set[str]
) -> tuple[int, int]:
    groups = {
        tuple(
            sorted(
                {
                    item
                    for item in (
                        fact.previous_evidence_id,
                        fact.evidence_id,
                        fact.next_evidence_id,
                    )
                    if item is not None
                }
            )
        )
        for fact in facts
    }
    complete = sum(set(group) <= selected_ids for group in groups)
    return complete, len(groups) - complete


def _supported_target_units(
    request: GenerationContextRequest,
    kp_results: list[AdequacyCoverageResult],
    semantic_results: list[AdequacyCoverageResult],
    required_semantic: dict[str, bool],
    distinct_sources: int,
    distinct_units: int,
) -> int:
    target = request.requirements.target_unit_count
    constraints = [(item.available_count, item.required_count) for item in kp_results] + [
        (item.available_count, item.required_count)
        for item in semantic_results
        if required_semantic[item.requirement_id]
    ]
    constraints.extend(
        [
            (distinct_sources, request.requirements.minimum_distinct_sources),
            (distinct_units, request.requirements.minimum_semantic_units),
        ]
    )
    return min(
        target,
        *(
            floor(target * min(available, required) / required)
            for available, required in constraints
        ),
    )


def _supplement_suggestions(
    request: GenerationContextRequest,
    missing_kps: list[str],
    missing_semantic: list[str],
    global_missing: list[str],
) -> list[SupplementRetrievalSuggestion]:
    semantic_by_id = {
        item.requirement_id: item for item in request.requirements.semantic_requirements
    }
    suggestions = [
        SupplementRetrievalSuggestion(
            suggestion_id=f"kp:{kp_id}",
            knowledge_point_ids=[kp_id],
            reason_code="knowledge_point_coverage_missing",
        )
        for kp_id in missing_kps
    ]
    suggestions.extend(
        SupplementRetrievalSuggestion(
            suggestion_id=f"requirement:{requirement_id}",
            requirement_ids=[requirement_id],
            knowledge_point_ids=semantic_by_id[requirement_id].knowledge_point_ids,
            roles=semantic_by_id[requirement_id].roles,
            material_types=semantic_by_id[requirement_id].material_types,
            reason_code="semantic_requirement_missing",
        )
        for requirement_id in missing_semantic
    )
    suggestions.extend(
        SupplementRetrievalSuggestion(
            suggestion_id=f"capacity:{requirement_id}",
            requirement_ids=[requirement_id],
            reason_code=f"{requirement_id}_insufficient",
        )
        for requirement_id in sorted(global_missing)
    )
    return sorted(suggestions, key=lambda item: item.suggestion_id)
