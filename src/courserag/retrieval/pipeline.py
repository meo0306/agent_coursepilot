from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from courserag.providers.reranker import (
    RerankerFailurePolicy,
    RerankerPort,
    RerankResult,
    rerank_with_policy,
)
from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter
from courserag.retrieval.ports import DenseRetrieverPort, SparseRetrieverPort
from courserag.retrieval.rrf import reciprocal_rank_fusion


class VersionedRetrievalPipeline:
    def __init__(
        self,
        *,
        dense: DenseRetrieverPort,
        sparse: SparseRetrieverPort,
        hydrate: Callable[[list[RetrievalCandidate]], list[RetrievalCandidate]],
        reranker: RerankerPort,
        rrf_k: int = 60,
    ) -> None:
        self.dense = dense
        self.sparse = sparse
        self.hydrate = hydrate
        self.reranker = reranker
        self.rrf_k = rrf_k

    def search(
        self,
        query: str,
        *,
        filters: RetrievalFilter,
        candidate_k: int = 30,
        top_n: int = 8,
        failure_policy: RerankerFailurePolicy = RerankerFailurePolicy.FAIL_SAMPLE,
    ) -> tuple[RerankResult, dict[str, int]]:
        latency: dict[str, int] = {}
        started = perf_counter()
        dense = self.dense.search(query, filters=filters, top_k=candidate_k)
        latency["dense"] = _elapsed_ms(started)
        started = perf_counter()
        sparse = self.sparse.search(query, filters=filters, top_k=candidate_k)
        latency["sparse"] = _elapsed_ms(started)
        started = perf_counter()
        fused = reciprocal_rank_fusion(dense, sparse, k=self.rrf_k, top_k=candidate_k)
        latency["fusion"] = _elapsed_ms(started)
        started = perf_counter()
        hydrated = self.hydrate(fused)
        if [item.chunk_id for item in hydrated] != [item.chunk_id for item in fused]:
            raise ValueError("Repository hydration changed Candidate order or identity")
        latency["hydrate"] = _elapsed_ms(started)
        started = perf_counter()
        result = rerank_with_policy(
            self.reranker, query, hydrated, top_n=top_n, policy=failure_policy
        )
        latency["rerank"] = _elapsed_ms(started)
        return result, latency


def _elapsed_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
