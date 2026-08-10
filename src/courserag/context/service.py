from __future__ import annotations

from collections.abc import Callable

from courserag.context.packer import ContextPacker
from courserag.contracts.retrieval import (
    ContextPackage,
    ContextRequest,
    SearchRequest,
    SearchResponse,
)


class EvidenceContextService:
    def __init__(
        self,
        *,
        search: Callable[[SearchRequest], SearchResponse],
        packer: ContextPacker,
    ) -> None:
        self.search_backend = search
        self.packer = packer

    def build(self, request: ContextRequest) -> ContextPackage:
        package, _search = self.build_with_search(request)
        return package

    def build_with_search(self, request: ContextRequest) -> tuple[ContextPackage, SearchResponse]:
        search_request = request.search_request or SearchRequest(
            context=request.context,
            course_id=request.course_id,
            query=request.query,
        )
        search = self.search_backend(search_request)
        intent = search.query.intent_route or "fact"
        return (
            self.packer.pack(
                context=request.context,
                query=request.query,
                purpose=request.purpose,
                search=search,
                intent_route=intent,
            ),
            search,
        )
