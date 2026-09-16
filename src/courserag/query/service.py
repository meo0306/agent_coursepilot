from __future__ import annotations

from collections.abc import Callable

from courserag.contracts.retrieval import QueryTrace, SearchRequest, SearchResponse
from courserag.query.models import QueryState
from courserag.query.pipeline import QueryPipeline, aggregate_query_candidates


class QueryAwareSearchService:
    def __init__(
        self,
        *,
        pipeline: QueryPipeline,
        search: Callable[[SearchRequest], SearchResponse],
        persist_query: Callable[[SearchRequest, QueryState], None] | None = None,
    ) -> None:
        self.pipeline = pipeline
        self.search_backend = search
        self.persist_query = persist_query

    def search(self, request: SearchRequest) -> SearchResponse:
        if not request.query_processing.enabled:
            return self.search_backend(request)
        state = self.pipeline.process(request.query)
        if self.persist_query is not None:
            self.persist_query(request, state)
        queries = (state.current_query, *state.rewrites)
        responses = [
            self.search_backend(request.model_copy(update={"query": query})) for query in queries
        ]
        response = responses[0]
        if len(responses) > 1:
            by_chunk = {hit.chunk_id: hit for item in responses for hit in item.hits}
            ranked = aggregate_query_candidates(
                tuple(tuple(hit.chunk_id for hit in item.hits) for item in responses)
            )
            limit = request.retrieval.return_top_n
            hits = []
            for rank, (chunk_id, score) in enumerate(ranked[:limit], start=1):
                hit = by_chunk[chunk_id].model_copy(deep=True)
                hit.rank = rank
                hit.scores.fusion = score
                hit.ranks.fusion = rank
                hits.append(hit)
            response.hits = hits
            response.retrieval.returned_count = len(hits)
            response.retrieval.debug_trace["multi_query_count"] = len(responses)
        reason = _retry_reason(response, state)
        if reason is not None:
            updated = self.pipeline.apply_low_recall_retry(state, reason=reason)
            if updated.retry_reason and state.raw_query not in queries:
                response = self.search_backend(
                    request.model_copy(update={"query": state.raw_query})
                )
            state = updated
        response.query = QueryTrace(
            original=state.raw_query,
            normalized=state.normalized_query,
            rewrites=list(state.rewrites),
            step_trace=[item.model_dump(mode="json") for item in state.traces],
            parsed_filters=state.explicit_filters.model_dump(mode="json"),
            linked_knowledge_points=[
                item.model_dump(mode="json") for item in state.linked_knowledge_points
            ],
            intent_route=state.intent_route.value,
            intent_rule_id=state.intent_rule_id,
            intent_reason=state.intent_reason,
            minimum_source_count=state.minimum_source_count,
            retrieval_strategy=state.retrieval_strategy.value,
            retry_reason=state.retry_reason,
        )
        return response


def _retry_reason(response: SearchResponse, state: QueryState) -> str | None:
    if not response.hits:
        return "no_candidates"
    top = response.hits[0].scores.rerank
    if top is not None and top < 0.7502601:
        return "provider_low_score"
    if any(item.hard_filter for item in state.linked_knowledge_points) and not any(
        hit.evidence_ids for hit in response.hits
    ):
        return "high_confidence_kp_not_found"
    return None
