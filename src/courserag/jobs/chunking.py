"""P06 Parent/Child Chunk Stage and versioned ChunkSet projection."""

from __future__ import annotations

from dataclasses import dataclass

from courserag.chunking.materialize import materialize_chunk_artifact
from courserag.chunking.splitter import ParentChildChunker
from courserag.chunking.tokenizer import TokenCounter
from courserag.domain.chunk import ChunkArtifact, ChunkProfile
from courserag.domain.document import canonical_json_bytes, sha256_bytes
from courserag.domain.evidence import EvidenceArtifact
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput
from courserag.persistence.models import ChunkRecord, ChunkSetRecord
from courserag.persistence.repositories import CourseRAGRepository


@dataclass(frozen=True)
class ParentChildChunkStage:
    evidence_artifact: bytes
    document_version_id: str
    profile: ChunkProfile
    tokenizer: TokenCounter
    name: str = "build_parent_child_chunks"
    version: str = "1.0"

    def execute(self, context: StageContext) -> StageOutput:
        digest = sha256_bytes(self.evidence_artifact)
        if context.input_hashes != (digest,):
            raise ValueError("Chunk Stage input hash differs from Evidence Artifact")
        if context.input_identities != (f"{self.document_version_id}:evidence",):
            raise ValueError("Chunk Stage input identity differs from document version")
        expected_config = chunk_stage_config(self.profile)
        if context.config != expected_config:
            raise ValueError("Chunk Stage config differs from frozen Profile")
        artifact = EvidenceArtifact.model_validate_json(self.evidence_artifact)
        if artifact.document_version_id != self.document_version_id:
            raise ValueError("Evidence Artifact document version differs from Chunk Stage")
        chunks = ParentChildChunker(self.profile, self.tokenizer).build(artifact)
        return StageOutput(
            content=canonical_json_bytes(chunks),
            media_type="application/vnd.courserag.parent-child-chunks+json",
            counts={
                "parents": sum(chunk.kind == "parent" for chunk in chunks.chunks),
                "children": sum(chunk.kind == "child" for chunk in chunks.chunks),
                "warnings": len(chunks.warning_codes),
            },
            warnings=chunks.warning_codes,
        )


def chunk_stage_config(profile: ChunkProfile) -> dict[str, object]:
    return {
        "chunk_profile_sha256": profile.profile_sha256,
        "tokenizer_id": profile.tokenizer_id,
        "tokenizer_sha256": profile.tokenizer_sha256,
        "parent_target_tokens": profile.parent_target_tokens,
        "parent_max_tokens": profile.parent_max_tokens,
        "child_target_tokens": profile.child_target_tokens,
        "child_max_tokens": profile.child_max_tokens,
        "child_overlap_tokens": profile.child_overlap_tokens,
    }


class ParentChildChunkCoordinator:
    def __init__(
        self,
        repository: CourseRAGRepository,
        stage_runner: BuildStageRunner,
        artifact_store: FileArtifactStore,
    ) -> None:
        self.repository = repository
        self.stage_runner = stage_runner
        self.artifact_store = artifact_store

    def run(
        self,
        stage: ParentChildChunkStage,
        context: StageContext,
        *,
        force: bool = False,
    ) -> tuple[ChunkSetRecord, tuple[ChunkRecord, ...]]:
        stage_run = self.stage_runner.run(stage, context, force=force)
        if stage_run.artifact_id is None:
            raise RuntimeError("Chunk Stage completed without an Artifact")
        stored = self.repository.get_artifact(stage_run.artifact_id)
        if stored is None:
            raise RuntimeError("Chunk Stage Artifact record disappeared")
        content = self.artifact_store.read(stored.uri, expected_sha256=stored.sha256)
        artifact = ChunkArtifact.model_validate_json(content)
        parsed = self.repository.get_parsed_document_by_version(stage.document_version_id)
        if parsed is None:
            raise RuntimeError("Chunk Stage requires a materialized ParsedDocument")
        return materialize_chunk_artifact(
            self.repository, parsed_document_id=parsed.id, artifact=artifact
        )
