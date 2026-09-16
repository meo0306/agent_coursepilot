from sqlalchemy import select
from sqlalchemy.orm import Session

from courserag.contracts import RequestContext, RetrievalMode
from courserag.contracts.retrieval import (
    RetrievalOptions,
    SearchFilters,
    SearchRequest,
    SourceTier,
)
from courserag.indexing.verified_overlay import VerifiedOverlayHit, retrieval_snapshot_id
from courserag.persistence.models import (
    BuildJobRecord,
    IndexVersionRecord,
    KnowledgeBaseRecord,
    RetrievalRunRecord,
    VerifiedIndexVersionRecord,
)
from courserag.persistence.repositories import CourseRAGRepository
from courserag.providers.reranker import RerankResult
from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter
from courserag.retrieval.service import VersionedSearchService


class FakePipeline:
    def __init__(self) -> None:
        self.filters: RetrievalFilter | None = None

    def search(self, query: str, *, filters: RetrievalFilter, **_: object):
        assert query == "special query"
        self.filters = filters
        return (
            RerankResult(
                candidates=[
                    RetrievalCandidate(
                        chunk_id="chunk",
                        document_id="doc",
                        document_version_id="dv",
                        section_id="section",
                        source_tier="primary_source",
                        text="repository hydrated text",
                        evidence_ids=("evidence",),
                        dense_score=0.9,
                        dense_rank=1,
                    )
                ],
                provider="disabled",
                model="disabled",
            ),
            {"dense": 1, "hydrate": 1},
        )


class FakeOverlaySearch:
    def search(self, **kwargs):
        assert kwargs["query"] == "special query"
        assert kwargs["knowledge_point_ids"] == ()
        return [
            VerifiedOverlayHit(
                verified_content_id="verified-1",
                title="Teacher note",
                text="verified special query explanation",
                evidence_ids=("evidence",),
                knowledge_point_ids=("kp",),
                sparse_score=1.0,
                dense_score=0.95,
            )
        ]


def test_versioned_search_pins_active_index_and_persists_trace(p03_session: Session) -> None:
    kb = KnowledgeBaseRecord(course_id="course", name="Course")
    p03_session.add(kb)
    p03_session.flush()
    job = BuildJobRecord(knowledge_base_id=kb.id, request_hash="a" * 64, status="succeeded")
    p03_session.add(job)
    p03_session.flush()
    index = IndexVersionRecord(
        knowledge_base_id=kb.id,
        build_job_id=job.id,
        version_number=1,
        status="active",
        sparse_status="ready",
        manifest_sha256="b" * 64,
    )
    p03_session.add(index)
    p03_session.flush()
    kb.active_index_version_id = index.id
    p03_session.flush()
    pipeline = FakePipeline()
    service = VersionedSearchService(
        repository=CourseRAGRepository(p03_session),
        pipeline_factory=lambda _: pipeline,
        retrieval_config_version="p08-v1",
        manifest_sha256="b" * 64,
        production=False,
    )
    response = service.search(
        SearchRequest(
            context=RequestContext(request_id="req", trace_id="trace"),
            course_id="course",
            query="  special   query ",
            filters=SearchFilters(
                document_ids=["doc"],
                document_version_ids=["dv"],
                knowledge_point_ids=["kp"],
                index_version=index.id,
                section_paths=[["chapter", "section"]],
            ),
            retrieval=RetrievalOptions(
                mode=RetrievalMode.HYBRID,
                candidate_k=30,
                rerank_top_n=8,
                return_top_n=8,
            ),
        )
    )
    assert response.retrieval.index_version == index.id
    assert response.hits[0].text == "repository hydrated text"
    assert response.hits[0].ranks.dense == 1
    assert pipeline.filters is not None
    assert pipeline.filters.document_ids == ("doc",)
    assert pipeline.filters.knowledge_point_ids == ("kp",)
    run = p03_session.scalar(select(RetrievalRunRecord))
    assert run is not None
    assert run.status == "succeeded"
    assert run.index_version_id == index.id
    assert run.debug_trace_json == {"index_version_id": index.id}


def test_versioned_search_fuses_active_verified_overlay(p03_session: Session) -> None:
    kb = KnowledgeBaseRecord(course_id="course", name="Course")
    p03_session.add(kb)
    p03_session.flush()
    job = BuildJobRecord(knowledge_base_id=kb.id, request_hash="c" * 64, status="succeeded")
    p03_session.add(job)
    p03_session.flush()
    index = IndexVersionRecord(
        knowledge_base_id=kb.id,
        build_job_id=job.id,
        version_number=1,
        status="active",
        sparse_status="ready",
        manifest_sha256="d" * 64,
    )
    p03_session.add(index)
    overlay = VerifiedIndexVersionRecord(
        knowledge_base_id=kb.id,
        version_number=1,
        status="active",
        manifest_sha256="e" * 64,
        active_item_count=1,
        validated=True,
    )
    p03_session.add(overlay)
    p03_session.flush()
    kb.active_index_version_id = index.id
    kb.active_verified_index_version_id = overlay.id
    p03_session.flush()
    service = VersionedSearchService(
        repository=CourseRAGRepository(p03_session),
        pipeline_factory=lambda _: FakePipeline(),
        retrieval_config_version="p17-v1",
        manifest_sha256="d" * 64,
        production=False,
        overlay_search=FakeOverlaySearch(),
    )

    response = service.search(
        SearchRequest(
            course_id="course",
            query="special query",
            filters=SearchFilters(
                index_version=index.id,
                source_tiers=[SourceTier.PRIMARY_SOURCE, SourceTier.TEACHER_VERIFIED],
            ),
            retrieval=RetrievalOptions(return_top_n=2),
        )
    )

    assert {hit.source_tier for hit in response.hits} == {
        SourceTier.PRIMARY_SOURCE,
        SourceTier.TEACHER_VERIFIED,
    }
    verified = next(hit for hit in response.hits if hit.source_tier == SourceTier.TEACHER_VERIFIED)
    assert verified.evidence_ids == ["evidence"]
    assert response.retrieval.verified_overlay_version == overlay.id
    assert response.retrieval.retrieval_snapshot_id == retrieval_snapshot_id(index.id, overlay.id)
