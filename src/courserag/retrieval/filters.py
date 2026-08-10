from __future__ import annotations

from collections.abc import Iterable

from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter


def filter_candidates(
    candidates: Iterable[RetrievalCandidate],
    filters: RetrievalFilter,
    *,
    chunk_document_ids: dict[str, str] | None = None,
    chunk_knowledge_point_ids: dict[str, set[str]] | None = None,
) -> list[RetrievalCandidate]:
    document_ids = chunk_document_ids or {}
    knowledge_points = chunk_knowledge_point_ids or {}
    output: list[RetrievalCandidate] = []
    for item in candidates:
        if (
            filters.document_version_ids
            and item.document_version_id not in filters.document_version_ids
        ):
            continue
        if filters.document_ids and document_ids.get(item.chunk_id) not in filters.document_ids:
            continue
        if filters.section_ids and item.section_id not in filters.section_ids:
            continue
        if filters.source_tiers and item.source_tier not in filters.source_tiers:
            continue
        if filters.knowledge_point_ids and not (
            set(filters.knowledge_point_ids) & knowledge_points.get(item.chunk_id, set())
        ):
            continue
        output.append(item)
    return output
