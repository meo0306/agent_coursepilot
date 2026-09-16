from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    KnowledgePointEvidenceRef,
    ProviderUsage,
    WindowProfile,
)
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.knowledge_points import KnowledgePointPipelineCoordinator
from courserag.knowledge_points.cache import DatabaseExtractionCache
from courserag.knowledge_points.materialize import materialize_knowledge_points
from courserag.knowledge_points.normalize import consolidate_candidates
from courserag.knowledge_points.profile import KnowledgePointPipelineProfile
from courserag.knowledge_points.provider import (
    KnowledgePointExtractionRunner,
    ProviderExtraction,
)
from courserag.knowledge_points.scoring import KnowledgePointScorer, ScoringProfile
from courserag.persistence.models import (
    BlockRecord,
    ChunkEvidenceRecord,
    ChunkProfileRecord,
    ChunkRecord,
    ChunkSetRecord,
    DocumentVersionRecord,
    EvidenceBlockLinkRecord,
    EvidenceRecord,
    KnowledgeBaseRecord,
    KnowledgePointExtractionBatchRecord,
    KnowledgePointWindowRecord,
    ParsedDocumentRecord,
    SectionRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository
from tests.courserag.knowledge_points.conftest import CharacterTokenizer, evidence, windows


class FakeProvider:
    provider_name = "fake"
    model_name = "fake-v1"
    structured_output_method = "fake-structured"

    def __init__(self) -> None:
        self.calls = 0

    def extract(self, window, prompt: str) -> ProviderExtraction:
        del prompt
        self.calls += 1
        return ProviderExtraction(
            candidates=(
                KnowledgePointCandidate(
                    canonical_name="人工智能",
                    aliases=("AI",),
                    summary="研究智能系统的课程概念",
                    evidence_refs=(
                        KnowledgePointEvidenceRef(
                            evidence_id=window.evidence[0].evidence_id,
                            role="definition",
                            is_primary=True,
                        ),
                    ),
                    model_confidence=0.01,
                ),
            ),
            usage=ProviderUsage(input_tokens=10, output_tokens=5, total_tokens=15),
        )


def _facts(session: Session):
    repository = CourseRAGRepository(session)
    source_evidence = evidence(1, "人工智能研究机器表现出的智能行为。")
    repository.add(KnowledgeBaseRecord(id="kb-1", course_id="course-1", name="Course"))
    repository.add(
        SourceDocumentRecord(
            id="doc-1", knowledge_base_id="kb-1", filename="a.pdf", document_type="pdf"
        )
    )
    repository.add(
        DocumentVersionRecord(
            id="version-1",
            source_document_id="doc-1",
            version_number=1,
            content_sha256="a" * 64,
            object_uri="fixture://a.pdf",
            mime_type="application/pdf",
            size_bytes=1,
        )
    )
    repository.add(
        ParsedDocumentRecord(
            id="parsed-1",
            document_version_id="version-1",
            parser_profile="test",
            parser_version="v1",
            status="ready",
        )
    )
    repository.add(
        SectionRecord(
            id="section-1",
            parsed_document_id="parsed-1",
            stable_path="section-1",
            heading="第一节",
            level=1,
            ordinal=0,
        )
    )
    repository.add(
        BlockRecord(
            id="block-1",
            parsed_document_id="parsed-1",
            section_id="section-1",
            stable_path="section-1/block-1",
            block_type="paragraph",
            ordinal=0,
            text=source_evidence.text,
            content_sha256=source_evidence.content_sha256,
        )
    )
    repository.add(
        EvidenceRecord(
            id="evidence-db-1",
            parsed_document_id="parsed-1",
            block_id="block-1",
            stable_key=source_evidence.evidence_id,
            evidence_type="definition",
            text=source_evidence.text,
            content_sha256=source_evidence.content_sha256,
        )
    )
    repository.add(
        EvidenceBlockLinkRecord(
            evidence_id="evidence-db-1",
            block_id="block-1",
            ordinal=0,
            char_start=0,
            char_end=len(source_evidence.text),
            text_sha256=source_evidence.content_sha256,
        )
    )
    repository.add(
        ChunkProfileRecord(
            id="profile-1",
            name="test",
            version="v1",
            profile_sha256="c" * 64,
            tokenizer_id="test",
            tokenizer_sha256="d" * 64,
            configuration_json={},
        )
    )
    repository.add(
        ChunkSetRecord(
            id="chunk-set-1",
            parsed_document_id="parsed-1",
            profile_id="profile-1",
            evidence_artifact_sha256="e" * 64,
            content_sha256="f" * 64,
            status="ready",
        )
    )
    repository.add(
        ChunkRecord(
            id="chunk-1",
            chunk_set_id="chunk-set-1",
            document_version_id="version-1",
            chunk_key="chunk-1",
            text=source_evidence.text,
            content_sha256=source_evidence.content_sha256,
            ordinal=0,
            chunk_kind="parent",
            token_count=10,
            profile_sha256="c" * 64,
        )
    )
    repository.add(ChunkEvidenceRecord(chunk_id="chunk-1", evidence_id="evidence-db-1"))
    batch = KnowledgePointExtractionBatchRecord(
        id="batch-1",
        knowledge_base_id="kb-1",
        identity_sha256="1" * 64,
        provider="fake",
        model_name="fake-v1",
        prompt_sha256="2" * 64,
        extractor_profile_sha256="3" * 64,
        scoring_profile_sha256="4" * 64,
        status="running",
    )
    repository.add(batch)
    repository.flush()
    source_windows = windows(source_evidence, maximum=200)
    repository.add(
        KnowledgePointWindowRecord(
            id="window-db-1",
            batch_id=batch.id,
            section_id="section-1",
            window_key=source_windows[0].window_id,
            ordinal=0,
            content_sha256=source_windows[0].content_sha256,
            profile_sha256=source_windows[0].profile_sha256,
            token_count=source_windows[0].token_count,
            evidence_ids_json=[source_evidence.evidence_id],
        )
    )
    repository.flush()
    return repository, batch, source_windows


def test_database_cache_reuses_result_and_recovers_stale_attempt(
    p03_session: Session, tmp_path: Path
) -> None:
    repository, batch, source_windows = _facts(p03_session)
    store = FileArtifactStore(tmp_path / "artifacts")
    provider = FakeProvider()
    cache = DatabaseExtractionCache(
        repository,
        store,
        batch_id=batch.id,
        provider=provider.provider_name,
        model=provider.model_name,
        prompt_sha256="2" * 64,
        extractor_profile_sha256="3" * 64,
        worker_id="worker-1",
    )
    runner = KnowledgePointExtractionRunner(
        provider,
        cache,
        prompt="prompt",
        prompt_sha256="2" * 64,
        extractor_profile_sha256="3" * 64,
        retry_base_seconds=0,
    )

    first = runner.run(source_windows)
    second = runner.run(source_windows)

    assert first == second
    assert provider.calls == 1
    cached_run = repository.find_cached_kp_window_run(runner._cache_key(source_windows[0]))
    assert cached_run is not None and cached_run.status == "succeeded"


def test_materialize_builds_explicit_evidence_and_chunk_links_idempotently(
    p03_session: Session,
) -> None:
    repository, batch, source_windows = _facts(p03_session)
    provider = FakeProvider()
    result = KnowledgePointExtractionRunner(
        provider,
        cache=_MemoryCache(),
        prompt="prompt",
        prompt_sha256="2" * 64,
        extractor_profile_sha256="3" * 64,
        retry_base_seconds=0,
    ).run(source_windows)
    drafts = consolidate_candidates(source_windows, result)
    scorer = KnowledgePointScorer(ScoringProfile(name="default", version="v1", threshold=0.1))
    scores = {draft.stable_key: scorer.score(draft) for draft in drafts}

    first = materialize_knowledge_points(
        repository,
        extraction_batch_id=batch.id,
        extractor_version="v1",
        extractor_profile_sha256="3" * 64,
        drafts=drafts,
        scores=scores,
    )
    second = materialize_knowledge_points(
        repository,
        extraction_batch_id=batch.id,
        extractor_version="v1",
        extractor_profile_sha256="3" * 64,
        drafts=drafts,
        scores=scores,
    )

    assert [item.id for item in first] == [item.id for item in second]
    assert first[0].status == "unreviewed"
    assert len(repository.list_knowledge_point_evidence(first[0].id)) == 1
    assert repository.get_knowledge_point_chunk_link(first[0].id, "chunk-1") is not None
    assert [item.alias for item in repository.list_knowledge_point_aliases(first[0].id)] == ["AI"]


class _MemoryCache:
    def __init__(self) -> None:
        self.value = None

    def get(self, cache_key):
        del cache_key
        return self.value

    def begin(self, window, cache_key):
        del window, cache_key

    def put(self, cache_key, result):
        del cache_key
        self.value = result

    def fail(self, window, cache_key, error_code):
        del window, cache_key, error_code


def test_pipeline_coordinator_reuses_window_cache(p03_session: Session, tmp_path: Path) -> None:
    repository, _, _ = _facts(p03_session)
    provider = FakeProvider()
    profile = KnowledgePointPipelineProfile(
        name="test",
        version="v1",
        window=WindowProfile(
            name="test",
            version="v1",
            tokenizer_id="test-character-v1",
            tokenizer_sha256="c" * 64,
            min_tokens=1,
            max_tokens=200,
        ),
        scoring=ScoringProfile(name="test", version="v1", threshold=0.1),
        prompt_relative_path="resources/prompts/courserag/extract_knowledge_points_v1.md",
    )
    coordinator = KnowledgePointPipelineCoordinator(
        repository,
        FileArtifactStore(tmp_path / "pipeline-artifacts"),
        provider,
        CharacterTokenizer(),
        profile,
        prompt="prompt",
        prompt_sha256="2" * 64,
        retry_base_seconds=0,
    )

    first = coordinator.run(knowledge_base_id="kb-1", document_version_ids=("version-1",))
    second = coordinator.run(knowledge_base_id="kb-1", document_version_ids=("version-1",))

    assert first.batch.id == second.batch.id
    assert [item.id for item in first.knowledge_points] == [
        item.id for item in second.knowledge_points
    ]
    assert provider.calls == 1
    assert second.batch.cache_hit_count == 1
    (BlockRecord,)
