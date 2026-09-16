from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import bm25s

from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter
from courserag.retrieval.tokenizer import character_bigrams, search_tokens


@dataclass(frozen=True)
class SparseDocument:
    chunk_id: str
    document_version_id: str
    text: str
    document_id: str | None = None
    section_id: str | None = None
    source_tier: str = "primary_source"
    knowledge_point_ids: tuple[str, ...] = ()


class VersionedBM25Index:
    def __init__(self, *, index_version_id: str, documents: Sequence[SparseDocument]) -> None:
        if len({item.chunk_id for item in documents}) != len(documents):
            raise ValueError("Sparse corpus Chunk IDs must be unique")
        self.index_version_id = index_version_id
        self.documents = tuple(documents)
        corpus = [search_tokens(item.text) for item in self.documents]
        self._vocabulary = {token for document in corpus for token in document}
        self._word = bm25s.BM25()
        self._word.index(corpus)
        bigrams = [character_bigrams(item.text) for item in self.documents]
        self._bigram = bm25s.BM25()
        self._bigram.index(bigrams)

    @property
    def corpus_sha256(self) -> str:
        payload = [item.__dict__ for item in self.documents]
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def search(
        self, query: str, *, filters: RetrievalFilter, top_k: int
    ) -> list[RetrievalCandidate]:
        if filters.index_version_id != self.index_version_id:
            raise ValueError("Sparse query index version differs from loaded index")
        word_tokens = search_tokens(query)
        use_bigram = not bool(set(word_tokens) & self._vocabulary)
        tokens = character_bigrams(query) if use_bigram else word_tokens
        retriever = self._bigram if use_bigram else self._word
        count = len(self.documents)
        if count == 0:
            return []
        indexes, scores = retriever.retrieve([tokens], k=min(count, max(top_k * 4, top_k)))
        output: list[RetrievalCandidate] = []
        for corpus_index, score in zip(indexes[0], scores[0], strict=True):
            document = self.documents[int(corpus_index)]
            candidate = RetrievalCandidate(
                chunk_id=document.chunk_id,
                document_id=document.document_id,
                document_version_id=document.document_version_id,
                section_id=document.section_id,
                source_tier=document.source_tier,
                knowledge_point_ids=document.knowledge_point_ids,
                sparse_score=float(score),
            )
            if _matches(candidate, filters):
                output.append(candidate)
            if len(output) == top_k:
                break
        return output

    def save(self, directory: Path) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._word.save(directory / "word", show_progress=False)
        self._bigram.save(directory / "bigram", show_progress=False)
        payload = {
            "schema_version": "courserag.bm25-mapping.v2",
            "index_version_id": self.index_version_id,
            "corpus_sha256": self.corpus_sha256,
            "documents": [item.__dict__ for item in self.documents],
        }
        (directory / "mapping.json").write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, directory: Path) -> VersionedBM25Index:
        payload = json.loads((directory / "mapping.json").read_text(encoding="utf-8"))
        documents = tuple(SparseDocument(**item) for item in payload["documents"])
        instance = cls.__new__(cls)
        instance.index_version_id = str(payload["index_version_id"])
        instance.documents = documents
        corpus = [search_tokens(item.text) for item in documents]
        instance._vocabulary = {token for document in corpus for token in document}
        instance._word = bm25s.BM25.load(directory / "word", show_progress=False)
        instance._bigram = bm25s.BM25.load(directory / "bigram", show_progress=False)
        if instance.corpus_sha256 != payload["corpus_sha256"]:
            raise ValueError("Sparse mapping corpus Hash differs from saved index")
        return instance


def _matches(candidate: RetrievalCandidate, filters: RetrievalFilter) -> bool:
    if (
        filters.document_version_ids
        and candidate.document_version_id not in filters.document_version_ids
    ):
        return False
    if filters.document_ids and candidate.document_id not in filters.document_ids:
        return False
    if filters.section_ids and candidate.section_id not in filters.section_ids:
        return False
    if filters.source_tiers and candidate.source_tier not in filters.source_tiers:
        return False
    return not filters.knowledge_point_ids or bool(
        set(filters.knowledge_point_ids) & set(candidate.knowledge_point_ids)
    )
