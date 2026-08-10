from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter


class EmbeddingPort(Protocol):
    @property
    def identity(self) -> str: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class DenseRetrieverPort(Protocol):
    def search(
        self, query: str, *, filters: RetrievalFilter, top_k: int
    ) -> list[RetrievalCandidate]: ...


class SparseRetrieverPort(Protocol):
    def search(
        self, query: str, *, filters: RetrievalFilter, top_k: int
    ) -> list[RetrievalCandidate]: ...
