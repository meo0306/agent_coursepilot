"""Legacy CoursePilot knowledge-base compatibility facade."""

from __future__ import annotations

from sqlalchemy.orm import Session

from coursepilot.adapters.courserag_mapping import search_hit_to_legacy_result
from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.rag.chunker import Chunker
from coursepilot.rag.vector_store import ChromaVectorStore
from coursepilot.schemas.document_schema import DocumentBuildResponse
from coursepilot.schemas.kb_schema import KBSearchRequest, KBSearchResult
from courserag.contracts import (
    RequestContext,
    RetrievalOptions,
    SearchFilters,
    SearchRequest,
    SourceTier,
)


class KnowledgeBaseService:
    """Preserve existing methods while delegating B0 behavior to the local Port adapter."""

    def __init__(
        self,
        session: Session,
        *,
        chunker: Chunker | None = None,
        vector_store: ChromaVectorStore | None = None,
        adapter: LocalCourseRAGAdapter | None = None,
    ) -> None:
        self.adapter = adapter or LocalCourseRAGAdapter(
            session,
            chunker=chunker,
            vector_store=vector_store,
        )

    def build_document(
        self,
        document_id: str,
        *,
        task_id: str | None = None,
    ) -> DocumentBuildResponse | None:
        return self.adapter.execute_legacy_build(document_id, task_id=task_id)

    def search(self, course_id: str, payload: KBSearchRequest) -> list[KBSearchResult]:
        source_tiers: list[SourceTier] = []
        if payload.verified_only is True:
            source_tiers = [SourceTier.TEACHER_VERIFIED]
        elif payload.verified_only is False:
            source_tiers = [SourceTier.PRIMARY_SOURCE]
        response = self.adapter.search(
            SearchRequest(
                context=RequestContext(caller="coursepilot-legacy-api"),
                course_id=course_id,
                query=payload.query,
                filters=SearchFilters(
                    document_types=[payload.source_type] if payload.source_type else [],
                    section_paths=[[payload.chapter]] if payload.chapter else [],
                    source_tiers=source_tiers,
                ),
                retrieval=RetrievalOptions(
                    candidate_k=payload.top_k,
                    rerank_top_n=payload.top_k,
                    return_top_n=payload.top_k,
                ),
            )
        )
        return [search_hit_to_legacy_result(hit, course_id=course_id) for hit in response.hits]
