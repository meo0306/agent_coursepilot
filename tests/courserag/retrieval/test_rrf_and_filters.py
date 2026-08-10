from courserag.retrieval.filters import filter_candidates
from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter
from courserag.retrieval.rrf import reciprocal_rank_fusion


def candidate(chunk_id: str, score: float) -> RetrievalCandidate:
    return RetrievalCandidate(
        chunk_id=chunk_id,
        document_version_id="dv",
        dense_score=score,
        sparse_score=score,
    )


def test_rrf_preserves_stage_scores_and_uses_stable_tie_break() -> None:
    result = reciprocal_rank_fusion(
        [candidate("b", 0.9), candidate("a", 0.8)],
        [candidate("a", 9.0), candidate("b", 8.0)],
        k=60,
    )
    assert [item.chunk_id for item in result] == ["a", "b"]
    assert result[0].dense_rank == 2
    assert result[0].sparse_rank == 1
    assert result[0].dense_score == 0.8
    assert result[0].sparse_score == 9.0
    assert result[0].fusion_rank == 1


def test_rrf_deduplicates_each_source() -> None:
    result = reciprocal_rank_fusion([candidate("a", 1), candidate("a", 0)], [], k=60)
    assert len(result) == 1
    assert result[0].fusion_score == 1 / 61


def test_filter_isolation_includes_kp_document_section_and_tier() -> None:
    items = [
        RetrievalCandidate(
            chunk_id="allowed",
            document_version_id="dv-1",
            section_id="section-1",
            source_tier="primary_source",
        ),
        RetrievalCandidate(
            chunk_id="other",
            document_version_id="dv-2",
            section_id="section-2",
            source_tier="teacher_verified",
        ),
    ]
    filters = RetrievalFilter(
        course_id="course",
        index_version_id="index",
        document_ids=("doc-1",),
        document_version_ids=("dv-1",),
        section_ids=("section-1",),
        knowledge_point_ids=("kp-1",),
        source_tiers=("primary_source",),
    )
    assert [
        item.chunk_id
        for item in filter_candidates(
            items,
            filters,
            chunk_document_ids={"allowed": "doc-1", "other": "doc-2"},
            chunk_knowledge_point_ids={"allowed": {"kp-1"}, "other": {"kp-1"}},
        )
    ] == ["allowed"]
