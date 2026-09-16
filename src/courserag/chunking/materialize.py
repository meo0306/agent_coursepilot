"""Idempotent materialization of versioned Parent/Child Chunk artifacts."""

from __future__ import annotations

from courserag.domain.chunk import ChunkArtifact
from courserag.domain.document import stable_ir_id
from courserag.persistence.models import (
    ChunkEvidenceRecord,
    ChunkProfileRecord,
    ChunkRecord,
    ChunkSetRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class ChunkMaterializationConflict(RuntimeError):
    pass


def materialize_chunk_artifact(
    repository: CourseRAGRepository,
    *,
    parsed_document_id: str,
    artifact: ChunkArtifact,
) -> tuple[ChunkSetRecord, tuple[ChunkRecord, ...]]:
    profile = repository.get_chunk_profile_by_sha256(artifact.profile.profile_sha256)
    profile_payload = artifact.profile.model_dump(mode="json")
    if profile is None:
        profile = ChunkProfileRecord(
            id=stable_ir_id("chunkprofile", artifact.profile.profile_sha256),
            name=artifact.profile.name,
            version=artifact.profile.version,
            profile_sha256=artifact.profile.profile_sha256,
            tokenizer_id=artifact.profile.tokenizer_id,
            tokenizer_sha256=artifact.profile.tokenizer_sha256,
            configuration_json=profile_payload,
        )
        repository.add(profile)
        repository.flush()
    elif profile.configuration_json != profile_payload:
        raise ChunkMaterializationConflict("Chunk Profile hash has different configuration")

    existing = repository.get_chunk_set_by_content_sha256(artifact.content_sha256)
    if existing is not None:
        chunks = tuple(repository.list_chunks_by_set(existing.id))
        if len(chunks) != len(artifact.chunks):
            raise ChunkMaterializationConflict("Chunk Set is incomplete")
        return existing, chunks

    chunk_set = ChunkSetRecord(
        id=stable_ir_id("chunkset", artifact.chunk_set_id),
        parsed_document_id=parsed_document_id,
        profile_id=profile.id,
        evidence_artifact_sha256=artifact.evidence_artifact_sha256,
        content_sha256=artifact.content_sha256,
        status="ready_with_warnings" if artifact.warning_codes else "ready",
        warnings_json=list(artifact.warning_codes),
    )
    repository.add(chunk_set)
    repository.flush()
    internal_chunk_ids = {
        chunk.chunk_id: stable_ir_id("chunk", chunk.chunk_id) for chunk in artifact.chunks
    }
    persisted: list[ChunkRecord] = []
    for chunk in artifact.chunks:
        record = ChunkRecord(
            id=internal_chunk_ids[chunk.chunk_id],
            index_version_id=None,
            chunk_set_id=chunk_set.id,
            parent_chunk_id=(
                internal_chunk_ids[chunk.parent_chunk_id]
                if chunk.parent_chunk_id is not None
                else None
            ),
            document_version_id=chunk.document_version_id,
            chunk_key=chunk.chunk_id,
            text=chunk.text,
            content_sha256=chunk.content_sha256,
            ordinal=chunk.ordinal,
            chunk_kind=chunk.kind,
            token_count=chunk.token_count,
            profile_sha256=chunk.profile_sha256,
            warning_codes_json=list(chunk.warning_codes),
            metadata_json={"section_id": chunk.section_id},
        )
        repository.add(record)
        persisted.append(record)
    repository.flush()
    for chunk, record in zip(artifact.chunks, persisted, strict=True):
        for link in chunk.evidence_links:
            evidence = repository.get_evidence_by_parsed_document_and_key(
                parsed_document_id, link.evidence_id
            )
            if evidence is None:
                raise ChunkMaterializationConflict(
                    f"Chunk references missing Evidence: {link.evidence_id}"
                )
            repository.add(
                ChunkEvidenceRecord(
                    chunk_id=record.id,
                    evidence_id=evidence.id,
                    ordinal=link.ordinal,
                    evidence_char_start=link.evidence_char_start,
                    evidence_char_end=link.evidence_char_end,
                    coverage_sha256=link.coverage_sha256,
                )
            )
    repository.flush()
    return chunk_set, tuple(persisted)
