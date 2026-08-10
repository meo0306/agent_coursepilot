from courserag.contracts.common import ResponseMeta
from courserag.contracts.retrieval import (
    QueryProcessingOptions,
    QueryTrace,
    RetrievalTrace,
    ScoreBreakdown,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceTier,
)
from courserag.query import QueryAwareSearchService, QueryPipeline, QueryPipelineProfile


class Rewriter:
    def rewrite(self, query: str, *, max_rewrites: int) -> tuple[str, ...]:
        return (f"{query} 扩展",)[:max_rewrites]


def _search(request: SearchRequest) -> SearchResponse:
    chunk_id = "base" if "扩展" not in request.query else "expanded"
    return SearchResponse(
        meta=ResponseMeta.from_context(request.context),
        query=QueryTrace(original=request.query, normalized=request.query),
        hits=[
            SearchHit(
                rank=1,
                chunk_id=chunk_id,
                document_version="v1",
                text=request.query,
                scores=ScoreBreakdown(rerank=0.9),
                evidence_ids=[f"ev-{chunk_id}"],
                source_tier=SourceTier.PRIMARY_SOURCE,
            )
        ],
        retrieval=RetrievalTrace(
            retrieval_config_version="v1",
            index_version="index",
            candidate_count=1,
            returned_count=1,
        ),
    )


def test_query_service_uses_one_pipeline_and_aggregates_rewrites() -> None:
    service = QueryAwareSearchService(
        pipeline=QueryPipeline(
            profile=QueryPipelineProfile(multi_query=True), rewrite_provider=Rewriter()
        ),
        search=_search,
    )
    response = service.search(
        SearchRequest(
            course_id="course",
            query="什么是注意力",
            query_processing=QueryProcessingOptions(enabled=True),
            retrieval={"return_top_n": 2},
        )
    )
    assert {hit.chunk_id for hit in response.hits} == {"base", "expanded"}
    assert response.query.intent_route == "definition"
    assert response.retrieval.debug_trace["multi_query_count"] == 2
