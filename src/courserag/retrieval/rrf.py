from __future__ import annotations

from collections.abc import Sequence

from courserag.retrieval.models import RetrievalCandidate


def reciprocal_rank_fusion(
    dense: Sequence[RetrievalCandidate],
    sparse: Sequence[RetrievalCandidate],
    *,
    k: int = 60,
    dense_weight: float = 1.0,
    sparse_weight: float = 1.0,
    top_k: int | None = None,
) -> list[RetrievalCandidate]:
    if k < 1:
        raise ValueError("RRF k must be positive")
    if dense_weight < 0 or sparse_weight < 0 or dense_weight + sparse_weight == 0:
        raise ValueError("RRF weights must be non-negative and not both zero")
    merged: dict[str, RetrievalCandidate] = {}
    scores: dict[str, float] = {}
    for source, weight, score_attr, rank_attr in (
        (dense, dense_weight, "dense_score", "dense_rank"),
        (sparse, sparse_weight, "sparse_score", "sparse_rank"),
    ):
        seen: set[str] = set()
        for rank, item in enumerate(source, start=1):
            if item.chunk_id in seen:
                continue
            seen.add(item.chunk_id)
            current = merged.setdefault(item.chunk_id, item.clone())
            setattr(current, score_attr, getattr(item, score_attr))
            setattr(current, rank_attr, rank)
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + weight / (k + rank)
    ordered = sorted(merged.values(), key=lambda item: (-scores[item.chunk_id], item.chunk_id))
    for rank, item in enumerate(ordered, start=1):
        item.fusion_score = scores[item.chunk_id]
        item.fusion_rank = rank
    return ordered if top_k is None else ordered[:top_k]
