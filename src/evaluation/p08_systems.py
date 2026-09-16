from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from time import perf_counter

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from courserag.evals.p08_metrics import RetrievalEvalHit
from courserag.evals.schemas import RetrievalQACase
from courserag.indexing.sparse import SparseDocument, VersionedBM25Index
from courserag.providers.reranker import (
    CachingReranker,
    DisabledReranker,
    HTTPRerankerAdapter,
    RerankerFailurePolicy,
    RerankerPort,
    UsageBudget,
    rerank_with_policy,
)
from courserag.retrieval.models import RetrievalCandidate, RetrievalFilter
from courserag.retrieval.ports import EmbeddingPort
from courserag.retrieval.rrf import reciprocal_rank_fusion


class P08SystemResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hits: list[RetrievalEvalHit]
    stage_latency_ms: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, JsonValue] = Field(default_factory=dict)
    fallback_applied: bool = False
    warnings: list[str] = Field(default_factory=list)


@dataclass
class EmbeddingBudget:
    maximum_tokens: int = 500_000
    used_tokens: int = 0

    def reserve(self, texts: Sequence[str]) -> None:
        estimate = int(sum(max(1, (len(item) + 2) // 3) for item in texts) * 1.5)
        if self.used_tokens + estimate > self.maximum_tokens:
            raise RuntimeError("Embedding evaluation token budget would be exceeded")
        self.used_tokens += estimate


class EvaluationDenseIndex:
    def __init__(
        self,
        *,
        index_version_id: str,
        corpus: Sequence[RetrievalCandidate],
        embedder: EmbeddingPort,
        budget: EmbeddingBudget,
        batch_size: int = 64,
    ) -> None:
        self.index_version_id = index_version_id
        self.corpus = tuple(corpus)
        self.embedder = embedder
        self.budget = budget
        self.vectors: list[list[float]] = []
        for start in range(0, len(corpus), batch_size):
            texts = [item.text for item in corpus[start : start + batch_size]]
            budget.reserve(texts)
            try:
                embeddings = embedder.embed_documents(texts)
            except RuntimeError as exc:
                stop = min(start + batch_size, len(corpus))
                raise RuntimeError(f"Embedding batch {start}:{stop} failed: {exc}") from exc
            self.vectors.extend(embeddings)
        if len(self.vectors) != len(self.corpus):
            raise ValueError("Embedding result count differs from the evaluation corpus")

    def search(self, query: str, *, top_k: int) -> list[RetrievalCandidate]:
        self.budget.reserve([query])
        query_vector = self.embedder.embed_query(query)
        scores = [
            (candidate, _cosine(query_vector, vector))
            for candidate, vector in zip(self.corpus, self.vectors, strict=True)
        ]
        scores.sort(key=lambda item: (-item[1], item[0].chunk_id))
        output: list[RetrievalCandidate] = []
        for rank, (candidate, score) in enumerate(scores[:top_k], start=1):
            item = candidate.clone()
            item.dense_score = score
            item.dense_rank = rank
            output.append(item)
        return output


class P08RetrievalSystem:
    def __init__(
        self,
        *,
        label: str,
        corpus_by_course: Mapping[str, Sequence[RetrievalCandidate]],
        dense_by_course: Mapping[str, EvaluationDenseIndex],
        reranker: RerankerPort | None = None,
        use_sparse: bool,
        candidate_k: int = 30,
        top_n: int = 8,
        rrf_k: int = 60,
    ) -> None:
        self.label = label
        self.corpus_by_course = corpus_by_course
        self.dense_by_course = dense_by_course
        self.reranker = reranker or DisabledReranker()
        self.use_sparse = use_sparse
        self.candidate_k = candidate_k
        self.top_n = top_n
        self.rrf_k = rrf_k
        self._sparse: dict[str, VersionedBM25Index] = {}
        for course_id, corpus in corpus_by_course.items():
            index_id = dense_by_course[course_id].index_version_id
            self._sparse[course_id] = VersionedBM25Index(
                index_version_id=index_id,
                documents=[
                    SparseDocument(
                        chunk_id=item.chunk_id,
                        document_id=item.document_id,
                        document_version_id=item.document_version_id,
                        text=item.text,
                        section_id=item.section_id,
                        source_tier=item.source_tier,
                        knowledge_point_ids=item.knowledge_point_ids,
                    )
                    for item in corpus
                ],
            )

    def search(self, case: RetrievalQACase) -> P08SystemResult:
        course_id = case.course_id
        if course_id is None or course_id not in self.dense_by_course:
            raise ValueError("P08 Case course has no evaluation index")
        index = self.dense_by_course[course_id]
        filters = RetrievalFilter(course_id=course_id, index_version_id=index.index_version_id)
        started = perf_counter()
        dense = index.search(case.query, top_k=self.candidate_k)
        latency = {"dense": _elapsed(started)}
        candidates = dense
        if self.use_sparse:
            started = perf_counter()
            sparse = self._sparse[course_id].search(
                case.query, filters=filters, top_k=self.candidate_k
            )
            latency["sparse"] = _elapsed(started)
            started = perf_counter()
            candidates = reciprocal_rank_fusion(dense, sparse, k=self.rrf_k, top_k=self.candidate_k)
            latency["fusion"] = _elapsed(started)
        if self.reranker.provider_name == "disabled":
            ranked = candidates[: self.top_n]
            usage: dict[str, JsonValue] = {}
            fallback = False
            warnings: list[str] = []
        else:
            started = perf_counter()
            result = rerank_with_policy(
                self.reranker,
                case.query,
                candidates,
                top_n=self.top_n,
                policy=RerankerFailurePolicy.FAIL_SAMPLE,
            )
            latency["rerank"] = _elapsed(started)
            ranked = result.candidates
            usage = result.usage.model_dump(mode="json")
            fallback = result.fallback_applied
            warnings = result.warnings
        hits = [
            RetrievalEvalHit(
                chunk_id=item.chunk_id,
                evidence_ids=list(item.evidence_ids),
                score=_final_score(item),
            )
            for item in ranked
        ]
        return P08SystemResult(
            hits=hits,
            stage_latency_ms=latency,
            usage=usage,
            fallback_applied=fallback,
            warnings=warnings,
        )


def build_dense_indexes(
    corpus_by_course: Mapping[str, Sequence[RetrievalCandidate]],
    *,
    embedder: EmbeddingPort,
    budget: EmbeddingBudget,
    batch_size: int = 64,
) -> dict[str, EvaluationDenseIndex]:
    output: dict[str, EvaluationDenseIndex] = {}
    for course_id, corpus in corpus_by_course.items():
        identity = hashlib.sha256("\n".join(item.chunk_id for item in corpus).encode()).hexdigest()
        output[course_id] = EvaluationDenseIndex(
            index_version_id=f"p08-{identity[:24]}",
            corpus=corpus,
            embedder=embedder,
            budget=budget,
            batch_size=batch_size,
        )
    return output


def build_formal_p08_systems(
    *,
    corpus_by_course: Mapping[str, Sequence[RetrievalCandidate]],
    embedder: EmbeddingPort,
    settings: object,
    initial_cohere_search_units: int = 0,
    reranker_candidates: frozenset[str] | None = None,
) -> dict[str, P08RetrievalSystem]:
    candidate_k = int(getattr(settings, "COURSERAG_RERANKER_CANDIDATE_K"))
    top_n = int(getattr(settings, "COURSERAG_RERANKER_TOP_N"))
    max_document_tokens = int(getattr(settings, "COURSERAG_RERANKER_MAX_DOC_TOKENS"))
    budget = EmbeddingBudget(
        maximum_tokens=int(getattr(settings, "COURSERAG_EMBEDDING_EVAL_MAX_TOKENS"))
    )
    dense = build_dense_indexes(
        corpus_by_course,
        embedder=embedder,
        budget=budget,
        batch_size=int(getattr(settings, "COURSERAG_EMBEDDING_BATCH_SIZE")),
    )
    systems = {
        "b3_dense": P08RetrievalSystem(
            label=f"b3_dense:{embedder.identity}",
            corpus_by_course=corpus_by_course,
            dense_by_course=dense,
            use_sparse=False,
            candidate_k=candidate_k,
            top_n=top_n,
        ),
        "b4_hybrid_rrf": P08RetrievalSystem(
            label=f"b4_hybrid_rrf:{embedder.identity}",
            corpus_by_course=corpus_by_course,
            dense_by_course=dense,
            use_sparse=True,
            candidate_k=candidate_k,
            top_n=top_n,
        ),
    }
    candidates = (
        set(reranker_candidates)
        if reranker_candidates is not None
        else {
            item.strip().casefold()
            for item in str(getattr(settings, "COURSERAG_RERANKER_EVAL_CANDIDATES")).split(",")
            if item.strip()
        }
    )
    if not candidates or not candidates <= {"jina", "cohere"}:
        raise ValueError("Formal P08 reranker candidates must be Jina and/or Cohere")
    if reranker_candidates is None and candidates != {"jina", "cohere"}:
        raise ValueError("Formal P08 requires exactly the approved Jina and Cohere candidates")
    cache: dict[str, dict[str, object]] = {}
    for provider in sorted(candidates):
        prefix = f"COURSERAG_{provider.upper()}_RERANKER"
        endpoint = getattr(settings, f"{prefix}_BASE_URL")
        model = getattr(settings, f"{prefix}_MODEL")
        secret = getattr(settings, f"{prefix}_API_KEY")
        if endpoint is None or model is None or secret is None:
            raise ValueError(f"Formal P08 {provider} configuration is incomplete")
        config_sha256 = hashlib.sha256(
            json.dumps(
                {
                    "provider": provider,
                    "model": model,
                    "endpoint": str(endpoint),
                    "candidate_k": candidate_k,
                    "top_n": top_n,
                    "max_document_tokens": max_document_tokens,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        provider_budget = UsageBudget(
            max_jina_tokens=int(getattr(settings, "COURSERAG_JINA_MAX_TOKENS")),
            max_cohere_search_units=int(getattr(settings, "COURSERAG_COHERE_MAX_SEARCH_UNITS")),
            cohere_search_units=(initial_cohere_search_units if provider == "cohere" else 0),
        )
        adapter = HTTPRerankerAdapter(
            provider_name=provider,
            model_name=str(model),
            endpoint=str(endpoint),
            api_key=secret.get_secret_value(),
            timeout_seconds=float(getattr(settings, "COURSERAG_RERANKER_TIMEOUT_SECONDS")),
            max_retries=int(getattr(settings, "COURSERAG_RERANKER_MAX_RETRIES")),
            max_document_tokens=max_document_tokens,
            budget=provider_budget,
            min_request_interval_seconds=(
                60.0 / int(getattr(settings, "COURSERAG_COHERE_RERANKER_MAX_RPM"))
                if provider == "cohere"
                else 0.0
            ),
        )
        reranker = CachingReranker(
            adapter,
            cache=cache,
            config_sha256=config_sha256,
            max_document_tokens=max_document_tokens,
        )
        systems[f"b5_{provider}"] = P08RetrievalSystem(
            label=f"b5_{provider}:{model}:embedding={embedder.identity}",
            corpus_by_course=corpus_by_course,
            dense_by_course=dense,
            reranker=reranker,
            use_sparse=True,
            candidate_k=candidate_k,
            top_n=top_n,
        )
    return systems


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must have matching non-zero dimensions")
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(item * item for item in left))
    right_norm = math.sqrt(sum(item * item for item in right))
    return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0


def _final_score(item: RetrievalCandidate) -> float:
    for value in (item.rerank_score, item.fusion_score, item.dense_score, item.sparse_score):
        if value is not None:
            return value
    return 0.0


def _elapsed(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
