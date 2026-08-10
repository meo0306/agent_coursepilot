"""Idempotently materialize Knowledge Point drafts and derived N:N links."""

from __future__ import annotations

from courserag.domain.document import stable_ir_id
from courserag.domain.knowledge_point import (
    KnowledgePointDraft,
    PublishScore,
    canonical_json_bytes,
    normalized_knowledge_point_name,
    sha256_bytes,
)
from courserag.persistence.base import utc_now
from courserag.persistence.models import (
    KnowledgePointAliasRecord,
    KnowledgePointChunkRecord,
    KnowledgePointEvidenceRecord,
    KnowledgePointRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class KnowledgePointMaterializationConflict(RuntimeError):
    pass


def materialize_knowledge_points(
    repository: CourseRAGRepository,
    *,
    extraction_batch_id: str,
    extractor_version: str,
    extractor_profile_sha256: str,
    drafts: tuple[KnowledgePointDraft, ...],
    scores: dict[str, PublishScore],
) -> tuple[KnowledgePointRecord, ...]:
    materialized: list[KnowledgePointRecord] = []
    for draft in drafts:
        score = scores.get(draft.stable_key)
        if score is None:
            raise KnowledgePointMaterializationConflict("Knowledge Point Draft has no score")
        record = repository.get_knowledge_point_by_key(draft.knowledge_base_id, draft.stable_key)
        metadata_json = {
            "section_ids": list(draft.section_ids),
            "window_ids": list(draft.window_ids),
            "parent_name_suggestion": draft.parent_name,
            "ambiguity_flags": list(draft.ambiguity_flags),
        }
        if record is None:
            record = KnowledgePointRecord(
                id=stable_ir_id("kp", draft.stable_key),
                knowledge_base_id=draft.knowledge_base_id,
                stable_key=draft.stable_key,
                title=draft.canonical_name,
                normalized_name=draft.normalized_name,
                description=draft.summary,
                parent_knowledge_point_id=None,
                publish_score=score.total,
                publish_score_components_json=score.components.model_dump(mode="json"),
                auto_published=score.status == "unreviewed",
                origin="auto_extracted",
                extractor_version=extractor_version,
                extractor_profile_sha256=extractor_profile_sha256,
                version_number=1,
                status=score.status,
                metadata_json=metadata_json,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            repository.add(record)
            repository.flush()
        else:
            changed = any(
                (
                    record.title != draft.canonical_name,
                    record.normalized_name != draft.normalized_name,
                    record.description != draft.summary,
                    record.publish_score != score.total,
                    record.publish_score_components_json
                    != score.components.model_dump(mode="json"),
                    record.extractor_version != extractor_version,
                    record.extractor_profile_sha256 != extractor_profile_sha256,
                    record.metadata_json != metadata_json,
                )
            )
            if changed:
                record.title = draft.canonical_name
                record.normalized_name = draft.normalized_name
                record.description = draft.summary
                record.publish_score = score.total
                record.publish_score_components_json = score.components.model_dump(mode="json")
                record.extractor_version = extractor_version
                record.extractor_profile_sha256 = extractor_profile_sha256
                record.metadata_json = metadata_json
                record.version_number += 1
                record.updated_at = utc_now()
            if record.status in {"unreviewed", "needs_review"}:
                record.status = score.status
                record.auto_published = score.status == "unreviewed"
        _materialize_aliases(repository, record, draft)
        _materialize_evidence_links(
            repository,
            record,
            draft,
            extraction_batch_id=extraction_batch_id,
        )
        repository.flush()
        rebuild_knowledge_point_chunk_links(repository, record)
        materialized.append(record)
    repository.flush()
    return tuple(materialized)


def _materialize_aliases(
    repository: CourseRAGRepository,
    record: KnowledgePointRecord,
    draft: KnowledgePointDraft,
) -> None:
    for alias in draft.aliases:
        normalized = normalized_knowledge_point_name(alias)
        if repository.get_knowledge_point_alias(record.id, normalized) is None:
            repository.add(
                KnowledgePointAliasRecord(
                    id=stable_ir_id("kpa", record.id, normalized),
                    knowledge_point_id=record.id,
                    alias=alias,
                    normalized_alias=normalized,
                    basis="provider",
                    created_at=utc_now(),
                )
            )


def _materialize_evidence_links(
    repository: CourseRAGRepository,
    record: KnowledgePointRecord,
    draft: KnowledgePointDraft,
    *,
    extraction_batch_id: str,
) -> None:
    for ref in draft.evidence_refs:
        evidence = repository.get_evidence_by_stable_key(draft.course_id, ref.evidence_id)
        if evidence is None:
            raise KnowledgePointMaterializationConflict(
                f"Knowledge Point references missing Evidence: {ref.evidence_id}"
            )
        link = repository.get_knowledge_point_evidence_link(record.id, evidence.id)
        if link is None:
            repository.add(
                KnowledgePointEvidenceRecord(
                    knowledge_point_id=record.id,
                    evidence_id=evidence.id,
                    role=ref.role,
                    strength=ref.strength,
                    is_primary=ref.is_primary,
                    extraction_batch_id=extraction_batch_id,
                    review_status="unreviewed",
                    created_at=utc_now(),
                )
            )
        elif link.review_status != "approved":
            link.role = ref.role
            link.strength = ref.strength
            link.is_primary = ref.is_primary
            link.extraction_batch_id = extraction_batch_id


def rebuild_knowledge_point_chunk_links(
    repository: CourseRAGRepository, record: KnowledgePointRecord
) -> None:
    evidence_links = repository.list_knowledge_point_evidence(record.id)
    repository.delete_knowledge_point_chunk_links(record.id)
    repository.flush()
    by_chunk: dict[str, tuple[str, float]] = {}
    for link in evidence_links:
        for chunk in repository.list_chunks_for_evidence(link.evidence_id):
            existing = by_chunk.get(chunk.id)
            if existing is None or link.strength > existing[1]:
                by_chunk[chunk.id] = (link.role, link.strength)
    for chunk_id, (role, strength) in by_chunk.items():
        derivation = sha256_bytes(
            canonical_json_bytes(
                {
                    "knowledge_point_id": record.id,
                    "chunk_id": chunk_id,
                    "evidence_ids": sorted(item.evidence_id for item in evidence_links),
                }
            )
        )
        repository.add(
            KnowledgePointChunkRecord(
                knowledge_point_id=record.id,
                chunk_id=chunk_id,
                role=role,
                strength=strength,
                use_for_filtering=record.status in {"unreviewed", "approved"},
                use_for_ranking=True,
                derivation_sha256=derivation,
                created_at=utc_now(),
            )
        )
    repository.flush()
