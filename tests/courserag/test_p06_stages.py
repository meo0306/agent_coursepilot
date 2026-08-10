from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from courserag.chunking.tokenizer import TokenCounter
from courserag.domain.chunk import ChunkProfile
from courserag.domain.document import ParsePreview, ParseQualityReport, sha256_bytes
from courserag.evidence.builder import EvidenceBuilderProfile
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.chunking import (
    ParentChildChunkCoordinator,
    ParentChildChunkStage,
    chunk_stage_config,
)
from courserag.jobs.evidence import (
    EvidenceBuildCoordinator,
    EvidenceBuildStage,
    evidence_stage_config,
)
from courserag.jobs.stages import BuildStageRunner, StageContext
from courserag.parsers.artifact_bundle import build_parsed_artifact_bundle
from courserag.persistence.materialize import materialize_parsed_document
from courserag.persistence.models import (
    ArtifactRecord,
    BuildJobRecord,
    BuildStageRunRecord,
    ChunkRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository
from tests.courserag.evidence.test_builder import _document


class CharacterTokenizer(TokenCounter):
    tokenizer_id = "test-char-v1"
    tokenizer_sha256 = "c" * 64

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))

    def count(self, text: str) -> int:
        return len(text)

    def token_ids(self, text: str) -> tuple[int | str, ...]:
        return tuple(text)


def _profile() -> ChunkProfile:
    return ChunkProfile(
        name="test",
        version="v1",
        tokenizer_id="test-char-v1",
        tokenizer_sha256="c" * 64,
        parent_min_tokens=1,
        parent_target_tokens=80,
        parent_max_tokens=100,
        child_min_tokens=1,
        child_target_tokens=30,
        child_max_tokens=45,
        child_overlap_tokens=10,
    )


def test_p06_stages_cache_and_materialize_idempotently(
    p03_session: Session, tmp_path: Path
) -> None:
    repository = CourseRAGRepository(p03_session)
    repository.add(KnowledgeBaseRecord(id="kb-1", course_id="course-1", name="Course"))
    repository.add(
        SourceDocumentRecord(
            id="doc-1", knowledge_base_id="kb-1", filename="fixture.pdf", document_type="pdf"
        )
    )
    repository.add(
        DocumentVersionRecord(
            id="version-1",
            source_document_id="doc-1",
            version_number=1,
            content_sha256="a" * 64,
            object_uri="fixture://source",
            mime_type="application/pdf",
            size_bytes=1,
        )
    )
    repository.add(
        BuildJobRecord(
            id="job-1", knowledge_base_id="kb-1", request_hash="d" * 64, status="running"
        )
    )
    repository.flush()
    document = _document()
    quality = ParseQualityReport(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        parser_profile=document.parser_profile,
        page_count=1,
        native_page_count=1,
        logical_docx_page_count=0,
        ocr_pending_page_count=0,
        heading_count=1,
        paragraph_count=1,
        table_count=0,
        image_count=0,
        noise_block_count=1,
        low_confidence_alignment_count=0,
        unresolved_block_count=0,
        warning_count=0,
        recommend_human_review=False,
    )
    preview = ParsePreview(
        document_id=document.document_id,
        document_version_id=document.document_version_id,
        section_tree=(),
        page_summaries=(),
        warnings=(),
    )
    parsed_bundle = build_parsed_artifact_bundle(document, quality, preview)
    store = FileArtifactStore(tmp_path / "artifacts")
    stored = store.put(parsed_bundle.content, media_type="application/zip")
    parsed_artifact = repository.get_or_create_artifact(
        ArtifactRecord(
            uri=stored.uri,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            media_type=stored.media_type,
            status="available",
        )
    )
    materialize_parsed_document(repository, document=document, artifact=parsed_artifact)
    runner = BuildStageRunner(repository, store)
    evidence_profile = EvidenceBuilderProfile()
    evidence_stage = EvidenceBuildStage(
        parsed_artifact=parsed_bundle.content,
        document_version_id="version-1",
        profile=evidence_profile,
    )
    evidence_context = StageContext(
        build_job_id="job-1",
        knowledge_base_id="kb-1",
        input_hashes=(sha256_bytes(parsed_bundle.content),),
        input_identities=("version-1:parsed_document",),
        config=evidence_stage_config(evidence_profile),
    )
    evidence_coordinator = EvidenceBuildCoordinator(repository, runner, store)
    first_evidence = evidence_coordinator.run(evidence_stage, evidence_context)
    second_evidence = evidence_coordinator.run(evidence_stage, evidence_context)
    assert [record.id for record in first_evidence] == [record.id for record in second_evidence]

    evidence_run = (
        p03_session.query(BuildStageRunRecord)
        .filter_by(build_job_id="job-1", stage_name="build_evidence")
        .one()
    )
    assert evidence_run.artifact_id is not None
    evidence_artifact_record = repository.get_artifact(evidence_run.artifact_id)
    assert evidence_artifact_record is not None
    evidence_bytes = store.read(
        evidence_artifact_record.uri, expected_sha256=evidence_artifact_record.sha256
    )
    profile = _profile()
    chunk_stage = ParentChildChunkStage(
        evidence_artifact=evidence_bytes,
        document_version_id="version-1",
        profile=profile,
        tokenizer=CharacterTokenizer(),
    )
    chunk_context = StageContext(
        build_job_id="job-1",
        knowledge_base_id="kb-1",
        input_hashes=(sha256_bytes(evidence_bytes),),
        input_identities=("version-1:evidence",),
        config=chunk_stage_config(profile),
    )
    chunk_coordinator = ParentChildChunkCoordinator(repository, runner, store)
    first_set, first_chunks = chunk_coordinator.run(chunk_stage, chunk_context)
    second_set, second_chunks = chunk_coordinator.run(chunk_stage, chunk_context)

    assert second_set.id == first_set.id
    assert [chunk.id for chunk in second_chunks] == [chunk.id for chunk in first_chunks]
    assert p03_session.query(ChunkRecord).filter_by(chunk_set_id=first_set.id).count() == len(
        first_chunks
    )
    assert all(
        chunk.parent_chunk_id is not None for chunk in first_chunks if chunk.chunk_kind == "child"
    )
