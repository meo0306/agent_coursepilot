from __future__ import annotations

from sqlalchemy import select

from courserag.application.generation_context_service import GenerationEvidenceMetadata
from courserag.contracts import (
    GenerationMaterialType,
    GenerationSemanticRole,
    SourceTier,
)
from courserag.evidence.resolver import EvidenceResolver
from courserag.persistence.models import (
    EvidenceRecord as EvidenceORMRecord,
)
from courserag.persistence.models import (
    KnowledgePointEvidenceRecord,
    KnowledgePointRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository

_KP_ROLE_MAP = {
    "definition": GenerationSemanticRole.DEFINITION,
    "principle": GenerationSemanticRole.PRINCIPLE,
    "procedure": GenerationSemanticRole.PROCESS,
    "example": GenerationSemanticRole.EXAMPLE,
    "comparison": GenerationSemanticRole.COMPARISON,
    "application": GenerationSemanticRole.APPLICATION_CONTEXT,
    "limitation": GenerationSemanticRole.BOUNDARY,
}
_EVIDENCE_ROLE_MAP = {
    "definition": GenerationSemanticRole.DEFINITION,
    "steps": GenerationSemanticRole.PROCESS,
    "example": GenerationSemanticRole.EXAMPLE,
}
_EVIDENCE_MATERIAL_MAP = {
    "formula": GenerationMaterialType.FORMULA,
    "table": GenerationMaterialType.TABLE,
}


class RepositoryGenerationEvidenceMetadataProvider:
    """Read-only adapter over the existing PostgreSQL-backed Evidence/KP facts."""

    def __init__(self, repository: CourseRAGRepository) -> None:
        self.repository = repository
        self.resolver = EvidenceResolver(repository)

    def batch_resolve(
        self, course_id: str, evidence_ids: list[str]
    ) -> list[GenerationEvidenceMetadata]:
        knowledge_base = self.repository.get_knowledge_base_by_course(course_id)
        if knowledge_base is None:
            return []
        resolved = self.resolver.batch_resolve(course_id, evidence_ids)
        metadata: list[GenerationEvidenceMetadata] = []
        for evidence in resolved.records:
            orm = self.repository.get_evidence_by_stable_key(course_id, evidence.evidence_id)
            if orm is None:
                continue
            source = self._source_document(evidence.document_version_id)
            if source is None:
                continue
            roles, materials, knowledge_point_ids = self._semantic_metadata(orm, knowledge_base.id)
            metadata.append(
                GenerationEvidenceMetadata(
                    evidence_id=evidence.evidence_id,
                    course_id=course_id,
                    document_id=evidence.document_id,
                    document_version_id=evidence.document_version_id,
                    source_tier=SourceTier(source.source_tier),
                    roles=frozenset(roles),
                    material_types=frozenset(materials),
                    knowledge_point_ids=frozenset(knowledge_point_ids),
                    previous_evidence_id=evidence.previous_evidence_id,
                    next_evidence_id=evidence.next_evidence_id,
                )
            )
        return sorted(metadata, key=lambda item: item.evidence_id)

    def known_knowledge_point_ids(self, course_id: str) -> set[str]:
        knowledge_base = self.repository.get_knowledge_base_by_course(course_id)
        if knowledge_base is None:
            return set()
        return set(
            self.repository.session.scalars(
                select(KnowledgePointRecord.id).where(
                    KnowledgePointRecord.knowledge_base_id == knowledge_base.id,
                    KnowledgePointRecord.status.notin_(("rejected", "deprecated")),
                )
            )
        )

    def _source_document(self, document_version_id: str) -> SourceDocumentRecord | None:
        version = self.repository.get_document_version(document_version_id)
        if version is None:
            return None
        return self.repository.session.get(SourceDocumentRecord, version.source_document_id)

    def _semantic_metadata(
        self, evidence: EvidenceORMRecord, knowledge_base_id: str
    ) -> tuple[set[GenerationSemanticRole], set[GenerationMaterialType], set[str]]:
        roles: set[GenerationSemanticRole] = set()
        materials: set[GenerationMaterialType] = set()
        knowledge_point_ids: set[str] = set()
        evidence_role = _EVIDENCE_ROLE_MAP.get(evidence.evidence_type)
        if evidence_role is not None:
            roles.add(evidence_role)
        evidence_material = _EVIDENCE_MATERIAL_MAP.get(evidence.evidence_type)
        if evidence_material is not None:
            materials.add(evidence_material)

        knowledge_base_ids = select(KnowledgePointRecord.id).where(
            KnowledgePointRecord.knowledge_base_id == knowledge_base_id,
            KnowledgePointRecord.status.notin_(("rejected", "deprecated")),
        )
        links = self.repository.session.execute(
            select(KnowledgePointEvidenceRecord).where(
                KnowledgePointEvidenceRecord.evidence_id == evidence.id,
                KnowledgePointEvidenceRecord.knowledge_point_id.in_(knowledge_base_ids),
                KnowledgePointEvidenceRecord.review_status != "rejected",
            )
        ).scalars()
        for link in links:
            knowledge_point_ids.add(link.knowledge_point_id)
            role = _KP_ROLE_MAP.get(link.role)
            if role is not None:
                roles.add(role)
            if link.role == "formula":
                materials.add(GenerationMaterialType.FORMULA)

        for value in evidence.metadata_json.get("semantic_roles", []):
            try:
                roles.add(GenerationSemanticRole(str(value)))
            except ValueError:
                continue
        for value in evidence.metadata_json.get("material_types", []):
            try:
                materials.add(GenerationMaterialType(str(value)))
            except ValueError:
                continue
        return roles, materials, knowledge_point_ids
