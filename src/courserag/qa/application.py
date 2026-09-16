from __future__ import annotations

from courserag.context.service import EvidenceContextService
from courserag.contracts.qa import QARequest, QAResponse
from courserag.contracts.retrieval import ContextRequest, SearchRequest
from courserag.qa.service import CitedQAService


class CitedQAApplication:
    def __init__(self, *, contexts: EvidenceContextService, qa: CitedQAService) -> None:
        self.contexts = contexts
        self.qa = qa

    def answer(self, request: QARequest) -> QAResponse:
        search_request = SearchRequest(
            context=request.context,
            course_id=request.course_id,
            query=request.question,
            filters=request.filters,
            retrieval=request.retrieval,
        )
        context, search = self.contexts.build_with_search(
            ContextRequest(
                context=request.context,
                course_id=request.course_id,
                query=request.question,
                purpose="question_answering",
                search_request=search_request,
            )
        )
        top_score = search.hits[0].scores.rerank if search.hits else None
        return self.qa.answer(
            request,
            context=context,
            top_rerank_score=top_score,
            intent_route=search.query.intent_route or "fact",
        )
