from __future__ import annotations

import pytest
from pydantic import ValidationError

from courserag.application.generation_context_service import (
    GenerationContextService,
    GenerationEvidenceMetadata,
    assess_context_adequacy,
)
from courserag.contracts import (
    ContextAdequacyStatus,
    ContextItem,
    ContextPackage,
    CourseRAGError,
    ErrorCode,
    GenerationArtifactType,
    GenerationContextBoundary,
    GenerationContextRequest,
    GenerationContextRequirements,
    GenerationMaterialType,
    GenerationSemanticRequirement,
    GenerationSemanticRole,
    KnowledgePointCoverageRequirement,
    PackingReport,
    ResponseMeta,
    SourceTier,
)


def _request(*, supplement_round: int = 0, max_rounds: int = 1):
    return GenerationContextRequest(
        course_id="course-1",
        query="chapter one",
        requirements=GenerationContextRequirements(
            artifact_type=GenerationArtifactType.LESSON,
            target_unit_count=4,
            knowledge_point_requirements=[
                KnowledgePointCoverageRequirement(
                    knowledge_point_id="kp-1", minimum_semantic_units=1
                )
            ],
            semantic_requirements=[
                GenerationSemanticRequirement(
                    requirement_id="lesson.definition",
                    minimum_count=1,
                    roles=[GenerationSemanticRole.DEFINITION],
                )
            ],
            minimum_distinct_sources=2,
            minimum_semantic_units=2,
            supplement_round=supplement_round,
            max_supplement_rounds=max_rounds,
        ),
    )


def _context(request: GenerationContextRequest) -> ContextPackage:
    return ContextPackage(
        meta=ResponseMeta.from_context(request.context),
        query=request.query,
        purpose="generation:lesson",
        items=[
            ContextItem(
                context_item_id="ctx-1",
                text="first",
                document_id="doc-1",
                evidence_ids=["e-1"],
                token_count=1,
            ),
            ContextItem(
                context_item_id="ctx-2",
                text="second contains 123 case diagram words",
                document_id="doc-2",
                evidence_ids=["e-2"],
                token_count=6,
            ),
        ],
        token_count=7,
        retrieval_trace_id="trace-1",
        index_version="index-v1",
        packing_report=PackingReport(
            candidate_count=2,
            selected_count=2,
            selected_evidence_count=2,
            deduplicated_count=0,
            discarded_for_budget=0,
            token_budget=4000,
            token_count=7,
        ),
    )


def _facts() -> dict[str, GenerationEvidenceMetadata]:
    return {
        "e-1": GenerationEvidenceMetadata(
            evidence_id="e-1",
            course_id="course-1",
            document_id="doc-1",
            document_version_id="docv-1",
            source_tier=SourceTier.PRIMARY_SOURCE,
            roles=frozenset({GenerationSemanticRole.DEFINITION}),
            knowledge_point_ids=frozenset({"kp-1"}),
            next_evidence_id="e-2",
        ),
        "e-2": GenerationEvidenceMetadata(
            evidence_id="e-2",
            course_id="course-1",
            document_id="doc-2",
            document_version_id="docv-2",
            source_tier=SourceTier.PRIMARY_SOURCE,
            roles=frozenset({GenerationSemanticRole.EXAMPLE}),
            previous_evidence_id="e-1",
        ),
    }


def test_contract_rejects_unsorted_and_undeclared_knowledge_points() -> None:
    with pytest.raises(ValidationError):
        GenerationContextBoundary(document_ids=["z", "a"])
    with pytest.raises(ValidationError):
        GenerationContextRequirements(
            artifact_type="lesson",
            target_unit_count=1,
            semantic_requirements=[
                GenerationSemanticRequirement(
                    requirement_id="r1",
                    minimum_count=1,
                    roles=["definition"],
                    knowledge_point_ids=["kp-missing"],
                )
            ],
            minimum_distinct_sources=1,
            minimum_semantic_units=1,
        )


def test_rich_context_is_adequate_and_group_is_complete() -> None:
    request = _request()
    report = assess_context_adequacy(
        request=request,
        context=_context(request),
        facts=_facts(),
        known_knowledge_point_ids={"kp-1"},
    )

    assert report.status is ContextAdequacyStatus.ADEQUATE
    assert report.supported_target_unit_count == 4
    assert report.complete_evidence_group_count == 1
    assert report.incomplete_evidence_group_count == 0


def test_thin_context_needs_more_then_becomes_unresolvable() -> None:
    for supplement_round, expected in (
        (0, ContextAdequacyStatus.NEEDS_MORE_EVIDENCE),
        (1, ContextAdequacyStatus.UNRESOLVABLE),
    ):
        request = _request(supplement_round=supplement_round)
        facts = {"e-1": _facts()["e-1"]}
        context = _context(request).model_copy(
            update={
                "items": _context(request).items[:1],
                "token_count": 1,
                "packing_report": _context(request).packing_report.model_copy(
                    update={"selected_count": 1, "selected_evidence_count": 1}
                ),
            }
        )
        report = assess_context_adequacy(
            request=request,
            context=context,
            facts=facts,
            known_knowledge_point_ids={"kp-1"},
        )
        assert report.status is expected
        assert report.supported_target_unit_count == 2


def test_unknown_kp_is_unresolvable_even_when_supplement_is_available() -> None:
    request = _request()
    report = assess_context_adequacy(
        request=request,
        context=_context(request),
        facts=_facts(),
        known_knowledge_point_ids=set(),
    )
    assert report.status is ContextAdequacyStatus.UNRESOLVABLE
    assert report.supported_target_unit_count == 0
    assert report.missing_knowledge_point_ids == ["kp-1"]


def test_numeric_material_is_not_inferred_from_evidence_text() -> None:
    request = _request()
    requirements = request.requirements.model_copy(
        update={
            "semantic_requirements": [
                GenerationSemanticRequirement(
                    requirement_id="numeric",
                    minimum_count=1,
                    material_types=[GenerationMaterialType.NUMERIC],
                )
            ]
        }
    )
    request = request.model_copy(update={"requirements": requirements})
    report = assess_context_adequacy(
        request=request,
        context=_context(request),
        facts=_facts(),
        known_knowledge_point_ids={"kp-1"},
    )
    assert report.requirement_results[0].available_count == 0
    assert report.status is ContextAdequacyStatus.NEEDS_MORE_EVIDENCE


class _Provider:
    def batch_resolve(self, course_id: str, evidence_ids: list[str]):
        facts = _facts()
        return [facts[evidence_id] for evidence_id in evidence_ids]

    def known_knowledge_point_ids(self, course_id: str) -> set[str]:
        return {"kp-1"}


def test_service_rejects_index_and_course_boundary_mismatch() -> None:
    request = _request()
    request = request.model_copy(
        update={
            "requirements": request.requirements.model_copy(
                update={"boundary": GenerationContextBoundary(required_index_version="other")}
            )
        }
    )
    service = GenerationContextService(
        build_context=lambda _: _context(request), metadata_provider=_Provider()
    )
    with pytest.raises(CourseRAGError) as exc_info:
        service.build(request)
    assert exc_info.value.code is ErrorCode.VERSION_CONFLICT


@pytest.mark.parametrize("violation", ["course", "tier"])
def test_service_fails_closed_for_evidence_boundary_violations(violation: str) -> None:
    request = _request()
    if violation == "tier":
        request = request.model_copy(
            update={
                "requirements": request.requirements.model_copy(
                    update={
                        "boundary": GenerationContextBoundary(
                            allowed_source_tiers=[SourceTier.TEACHER_VERIFIED]
                        )
                    }
                )
            }
        )

    class ViolatingProvider(_Provider):
        def batch_resolve(self, course_id: str, evidence_ids: list[str]):
            facts = super().batch_resolve(course_id, evidence_ids)
            if violation == "course":
                facts[0] = GenerationEvidenceMetadata(
                    **{**facts[0].__dict__, "course_id": "course-2"}
                )
            return facts

    service = GenerationContextService(
        build_context=lambda _: _context(request), metadata_provider=ViolatingProvider()
    )
    with pytest.raises(CourseRAGError) as exc_info:
        service.build(request)
    assert exc_info.value.code is ErrorCode.FORBIDDEN


def test_service_is_deterministic_for_reordered_metadata() -> None:
    request = _request()

    class ReverseProvider(_Provider):
        def batch_resolve(self, course_id: str, evidence_ids: list[str]):
            return list(reversed(super().batch_resolve(course_id, evidence_ids)))

    first = GenerationContextService(
        build_context=lambda _: _context(request), metadata_provider=_Provider()
    ).build(request)
    second = GenerationContextService(
        build_context=lambda _: _context(request), metadata_provider=ReverseProvider()
    ).build(request)
    assert first.adequacy.model_dump(mode="json") == second.adequacy.model_dump(mode="json")
