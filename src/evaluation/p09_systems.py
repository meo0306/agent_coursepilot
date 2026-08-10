from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.chunking.tokenizer import LocalTokenizer
from courserag.context import ContextPacker, ContextProfile
from courserag.contracts.common import RequestContext, ResponseMeta
from courserag.contracts.qa import AnswerType, QARequest
from courserag.contracts.retrieval import (
    QueryTrace,
    RetrievalTrace,
    ScoreBreakdown,
    SearchHit,
    SearchResponse,
    SourceTier,
)
from courserag.indexing.dense import LocalSentenceTransformerEmbeddingAdapter
from courserag.infrastructure.qa_provider import (
    OpenAICompatibleCapability,
    OpenAICompatibleQAProvider,
)
from courserag.infrastructure.query_provider import OpenAICompatibleRewriteProvider
from courserag.providers.reranker import (
    CachingReranker,
    HTTPRerankerAdapter,
    RerankerFailurePolicy,
    RerankerPort,
    UsageBudget,
    rerank_with_policy,
)
from courserag.qa import CitedQAService, EvidenceSufficiencyGate, SufficiencyProfile
from courserag.qa.models import ProviderPlainQAResult, ProviderQAResult, ProviderUsage
from courserag.query import (
    KnowledgePointCandidate,
    QueryPipeline,
    QueryPipelineProfile,
    aggregate_query_candidates,
)
from courserag.query.answer_shape import AnswerShapeDecision
from courserag.query.models import (
    IntentRoute,
    LinkedKnowledgePoint,
    ParsedFilters,
    QueryState,
    RetrievalStrategy,
)
from courserag.retrieval.models import RetrievalCandidate
from evaluation.p08_systems import (
    EmbeddingBudget,
    EvaluationDenseIndex,
    P08RetrievalSystem,
    build_dense_indexes,
)
from evaluation.p09_corpus import P09RuntimeCorpus, load_p09_runtime_corpus
from evaluation.p09_dev_loader import P09DevCase
from evaluation.p09_retrieval_qa_eval import P09ClaimResult, P09SystemResult, P09UsageBudget


class _Catalog:
    def __init__(self, values: Sequence[KnowledgePointCandidate]) -> None:
        self.values = tuple(values)

    def list_candidates(self) -> tuple[KnowledgePointCandidate, ...]:
        return self.values


class _CachingQAProvider:
    def __init__(self, inner: OpenAICompatibleQAProvider, budget: P09UsageBudget) -> None:
        self.inner = inner
        self.budget = budget
        self.cache: dict[str, ProviderQAResult] = {}
        self.plain_cache: dict[str, ProviderPlainQAResult] = {}

    def generate_plain(self, question: str, context: object) -> ProviderPlainQAResult:
        from courserag.contracts.retrieval import ContextPackage

        if not isinstance(context, ContextPackage):
            raise TypeError("QA Context has an invalid type")
        key = _qa_cache_key(question, context, "plain")
        if key in self.plain_cache:
            cached = self.plain_cache[key].model_copy(deep=True)
            cached.usage = ProviderUsage()
            return cached
        self.budget.reserve(deepseek_tokens=_estimated_qa_tokens(context))
        result = self.inner.generate_plain(question, context)
        self.plain_cache[key] = result.model_copy(deep=True)
        return result

    def generate(
        self,
        question: str,
        context: object,
        *,
        answer_shape: AnswerShapeDecision,
    ) -> ProviderQAResult:
        from courserag.contracts.retrieval import ContextPackage

        if not isinstance(context, ContextPackage):
            raise TypeError("QA Context has an invalid type")
        key = _qa_cache_key(question, context, f"generate:{answer_shape.rule_id}")
        if key in self.cache:
            cached = self.cache[key].model_copy(deep=True)
            cached.usage = ProviderUsage()
            return cached
        self.budget.reserve(
            deepseek_tokens=_estimated_qa_tokens(context, answer_shape=answer_shape)
        )
        result = self.inner.generate(question, context, answer_shape=answer_shape)
        self.cache[key] = result.model_copy(deep=True)
        return result

    def repair(
        self,
        question: str,
        context: object,
        *,
        error: str,
        answer_shape: AnswerShapeDecision,
    ) -> ProviderQAResult:
        from courserag.contracts.retrieval import ContextPackage

        if not isinstance(context, ContextPackage):
            raise TypeError("QA Context has an invalid type")
        key = _qa_cache_key(question, context, f"repair:{answer_shape.rule_id}:{error}")
        if key in self.cache:
            cached = self.cache[key].model_copy(deep=True)
            cached.usage = ProviderUsage()
            return cached
        self.budget.reserve(
            deepseek_tokens=_estimated_qa_tokens(context, answer_shape=answer_shape)
        )
        result = self.inner.repair(question, context, error=error, answer_shape=answer_shape)
        self.cache[key] = result.model_copy(deep=True)
        return result


class P09FormalSuite:
    """Shared P09 evaluation runtime; systems reuse retrieval and Provider caches."""

    def __init__(
        self,
        *,
        corpus: P09RuntimeCorpus,
        dense_by_course: Mapping[str, EvaluationDenseIndex],
        reranker: RerankerPort,
        rewrite_provider: OpenAICompatibleRewriteProvider,
        qa_provider: OpenAICompatibleQAProvider,
        tokenizer: LocalTokenizer,
        budget: P09UsageBudget,
        label_suffix: str = "candidate-v1",
        restored_results: Mapping[tuple[str, str], P09SystemResult] | None = None,
        generation_reliability_enabled: bool = False,
    ) -> None:
        self.corpus = corpus
        self.reranker = reranker
        self.rewrite_provider = rewrite_provider
        self.qa_provider = _CachingQAProvider(qa_provider, budget)
        self.budget = budget
        self.label_suffix = label_suffix
        self.restored_results = dict(restored_results or {})
        self.generation_reliability_enabled = generation_reliability_enabled
        self.candidates = {
            item.chunk_id: item
            for values in corpus.candidates_by_course.values()
            for item in values
        }
        self.raw_retriever: dict[str, P08RetrievalSystem] = {}
        for course_id, candidates in corpus.candidates_by_course.items():
            if course_id not in dense_by_course:
                continue
            dense = dense_by_course[course_id]
            self.raw_retriever[course_id] = P08RetrievalSystem(
                label="p09_hybrid_candidate_source",
                corpus_by_course={course_id: candidates},
                dense_by_course={course_id: dense},
                use_sparse=True,
                candidate_k=30,
                top_n=30,
            )
        catalog = _Catalog(_load_kp_candidates(Path.cwd()))
        self.b6_pipeline = QueryPipeline(
            profile=QueryPipelineProfile(multi_query=False), knowledge_points=catalog
        )
        self.b7_pipeline = QueryPipeline(
            profile=QueryPipelineProfile(multi_query=True),
            knowledge_points=catalog,
            rewrite_provider=rewrite_provider,
        )
        self.packer = ContextPacker(
            resolve_evidence=lambda evidence_id: corpus.evidence_by_id[evidence_id],
            tokenizer=tokenizer,
            profile=ContextProfile(max_items=8, max_tokens=4000),
        )
        self.retrieval_cache: dict[tuple[str, str], tuple[object, SearchResponse]] = {}
        self.context_cache: dict[tuple[str, str], object] = {}

    def system(self, variant: str) -> P09FormalSystem:
        return P09FormalSystem(self, variant, label_suffix=self.label_suffix)

    def run(self, case: P09DevCase, variant: str) -> P09SystemResult:
        if variant in {"b6", "b7", "b8"}:
            state, search = self._retrieval(case, "b6" if variant == "b6" else "b7")
            selected = _gold_evidence(search, self.corpus.gold_by_system_evidence)
            if variant == "b8":
                context = self._context(case, state, search, "b7")
                selected = _gold_context(context, self.corpus.gold_by_system_evidence)
            snapshot, snapshot_sha256 = _search_snapshot(search)
            return P09SystemResult(
                intent_route=state.intent_route.value,
                intent_rule_id=state.intent_rule_id,
                intent_reason=state.intent_reason,
                minimum_source_count=state.minimum_source_count,
                retrieval_strategy=state.retrieval_strategy.value,
                selected_evidence_ids=selected,
                context_token_count=(context.token_count if variant == "b8" else 0),
                context_item_count=(len(context.items) if variant == "b8" else 0),
                packing_report=(
                    context.packing_report.model_dump(mode="json") if variant == "b8" else {}
                ),
                search_snapshot=snapshot,
                search_snapshot_sha256=snapshot_sha256,
                usage=self._usage(),
            )
        retrieval_variant = {"q0": "dense", "q1": "b6", "q2": "b7", "q3": "b7"}[variant]
        restored_variant = {"q0": "q0", "q1": "b6", "q2": "b8", "q3": "q3"}.get(variant)
        restored = (
            self.restored_results.get((restored_variant, case.qa.record_id))
            if restored_variant
            else None
        )
        if restored is not None:
            if variant == "q3":
                return restored.model_copy(deep=True)
            state = self.b6_pipeline.process(case.qa.query)
            context, search = self._restored_context(case, state, restored)
        elif retrieval_variant == "dense":
            state, search = self._retrieval(case, "dense")
            context = self._context(case, state, search, retrieval_variant)
        else:
            state, search = self._retrieval(case, retrieval_variant)
            context = self._context(case, state, search, retrieval_variant)
        profile = (
            SufficiencyProfile(rerank_threshold=-1, multi_source_intents=())
            if variant != "q3"
            else SufficiencyProfile()
        )
        tokens_before = self.budget.deepseek_tokens
        if variant == "q0":
            plain = self.qa_provider.generate_plain(case.qa.query, context)
            return P09SystemResult(
                intent_route=state.intent_route.value,
                intent_rule_id=state.intent_rule_id,
                intent_reason=state.intent_reason,
                minimum_source_count=state.minimum_source_count,
                retrieval_strategy=state.retrieval_strategy.value,
                selected_evidence_ids=_gold_context(context, self.corpus.gold_by_system_evidence),
                context_token_count=context.token_count,
                context_item_count=len(context.items),
                answer_status="answered",
                answer=plain.output.answer,
                packing_report=context.packing_report.model_dump(mode="json"),
                usage={"deepseek_total_tokens": self.budget.deepseek_tokens - tokens_before},
                usage_is_cumulative=False,
            )
        response = CitedQAService(
            provider=self.qa_provider,
            gate=EvidenceSufficiencyGate(profile),
            generation_reliability_enabled=self.generation_reliability_enabled,
        ).answer(
            QARequest(course_id=case.qa.course_id, question=case.qa.query),
            context=context,
            top_rerank_score=(search.hits[0].scores.rerank if search.hits else None),
            intent_route=state.intent_route.value,
            minimum_source_count=state.minimum_source_count,
        )
        snapshot, snapshot_sha256 = _search_snapshot(search)
        return P09SystemResult(
            intent_route=state.intent_route.value,
            intent_rule_id=state.intent_rule_id,
            intent_reason=state.intent_reason,
            minimum_source_count=state.minimum_source_count,
            retrieval_strategy=state.retrieval_strategy.value,
            selected_evidence_ids=_gold_context(context, self.corpus.gold_by_system_evidence),
            context_token_count=context.token_count,
            context_item_count=len(context.items),
            answer_status=response.answer_status.value,
            answer=response.answer,
            answer_type=(response.answer_type.value if response.answer_type else None),
            list_items=response.list_items,
            claims=[
                P09ClaimResult(
                    text=claim.text,
                    evidence_ids=[
                        self.corpus.gold_by_system_evidence.get(value, value)
                        for value in claim.evidence_ids
                    ],
                )
                for claim in response.claims
            ],
            resolvable_citations=[
                citation.evidence_id in context.evidence_map for citation in response.citations
            ],
            packing_report=context.packing_report.model_dump(mode="json"),
            validation_summary=cast(dict[str, JsonValue], response.validation_summary),
            citation_composer_version=_string_value(
                response.validation_summary.get("citation_composer_version")
            ),
            answer_shape_rule_id=_string_value(
                response.validation_summary.get("answer_shape_rule_id")
            ),
            search_snapshot=snapshot,
            search_snapshot_sha256=snapshot_sha256,
            usage={"deepseek_total_tokens": self.budget.deepseek_tokens - tokens_before},
            usage_is_cumulative=False,
            warnings=response.warnings,
        )

    def _restored_context(self, case: P09DevCase, state: object, restored: P09SystemResult):
        from courserag.query.models import QueryState

        typed_state = QueryState.model_validate(state)
        system_by_gold = {
            gold: system for system, gold in self.corpus.gold_by_system_evidence.items()
        }
        candidates: list[RetrievalCandidate] = []
        for rank, gold_id in enumerate(restored.selected_evidence_ids, start=1):
            system_id = system_by_gold.get(gold_id)
            if system_id is None or system_id not in self.corpus.evidence_by_id:
                continue
            evidence = self.corpus.evidence_by_id[system_id]
            candidates.append(
                RetrievalCandidate(
                    chunk_id=f"restored-{rank}-{system_id}",
                    document_id=evidence.document_id,
                    document_version_id=evidence.document_version_id,
                    section_id=evidence.section_id,
                    text=evidence.text,
                    evidence_ids=(system_id,),
                    rerank_score=1.0,
                    rerank_rank=rank,
                )
            )
        search = _search_response(
            case,
            typed_state,
            candidates,
            "restored_approved_dev_checkpoint",
            "cohere-rerank-v4.0-pro",
            {},
        )
        return self.packer.pack(
            context=RequestContext(),
            query=case.qa.query,
            purpose="question_answering",
            search=search,
            intent_route=typed_state.intent_route.value,
        ), search

    def _retrieval(self, case: P09DevCase, variant: str):
        from courserag.query.models import QueryState

        key = (variant, case.qa.record_id)
        cached = self.retrieval_cache.get(key)
        if cached is not None:
            state, response = cached
            return state, response
        restored = self.restored_results.get(key)
        if restored is not None and restored.search_snapshot:
            response = SearchResponse.model_validate(restored.search_snapshot)
            _, actual_sha256 = _search_snapshot(response)
            if actual_sha256 != restored.search_snapshot_sha256:
                raise ValueError("restored P09 Search Snapshot hash differs from Checkpoint")
            state = _query_state_from_search(response)
            self.retrieval_cache[key] = (state, response)
            return state, response
        if case.qa.course_id not in self.raw_retriever:
            raise ValueError("P09 Case course is absent from runtime corpus")
        pipeline = self.b6_pipeline if variant in {"b6", "dense"} else self.b7_pipeline
        state = pipeline.process(case.qa.query)
        queries = (
            (state.current_query,) if variant == "dense" else (state.current_query, *state.rewrites)
        )
        raw_results = [
            self.raw_retriever[case.qa.course_id].search(
                case.retrieval.model_copy(update={"query": query})
            )
            for query in queries
        ]
        ranked_ids = aggregate_query_candidates(
            tuple(tuple(hit.chunk_id for hit in result.hits) for result in raw_results)
        )
        candidates: list[RetrievalCandidate] = []
        for rank, (chunk_id, score) in enumerate(ranked_ids[:30], start=1):
            item = self.candidates[chunk_id].clone()
            item.fusion_rank = rank
            item.fusion_score = score
            candidates.append(item)
        if variant == "dense":
            ranked = candidates[:8]
            provider, model, usage = "disabled", "dense-baseline", {}
        else:
            reranked = rerank_with_policy(
                self.reranker,
                case.qa.query,
                candidates,
                top_n=8,
                policy=RerankerFailurePolicy.FAIL_SAMPLE,
            )
            ranked = reranked.candidates
            provider, model = reranked.provider, reranked.model
            usage = reranked.usage.model_dump(mode="json")
            self.budget.reserve(cohere_search_units=reranked.usage.search_units)
        response = _search_response(case, state, ranked, provider, model, usage)
        typed_state = QueryState.model_validate(state)
        self.retrieval_cache[key] = (typed_state, response)
        return typed_state, response

    def _context(self, case: P09DevCase, state: object, search: SearchResponse, variant: str):
        from courserag.query.models import QueryState

        key = (variant, case.qa.record_id)
        if key in self.context_cache:
            return self.context_cache[key]
        typed_state = QueryState.model_validate(state)
        context = self.packer.pack(
            context=RequestContext(),
            query=case.qa.query,
            purpose="question_answering",
            search=search,
            intent_route=typed_state.intent_route.value,
        )
        self.context_cache[key] = context
        return context

    def _usage(self) -> dict[str, JsonValue]:
        return {
            "deepseek_total_tokens": self.budget.deepseek_tokens,
            "cohere_search_units": self.budget.cohere_search_units,
        }


class P09FormalSystem:
    def __init__(
        self, suite: P09FormalSuite, variant: str, *, label_suffix: str = "candidate-v1"
    ) -> None:
        self.suite = suite
        self.variant = variant
        self.label = f"p09-{variant}-{label_suffix}"

    def run(self, case: P09DevCase) -> P09SystemResult:
        return self.suite.run(case, self.variant)


def build_formal_p09_suite(
    repository_root: Path,
    settings: object,
    *,
    checkpoint_path: Path | None = None,
    max_deepseek_tokens: int = 2_500_000,
    max_cohere_search_units: int = 180,
    label_suffix: str = "candidate-v1",
    discard_restored_variants: frozenset[str] = frozenset(),
    initial_deepseek_tokens: int | None = None,
    retrieval_snapshot_path: Path | None = None,
    generation_reliability_enabled: bool = False,
    generation_reliability_factoid_enabled: bool = True,
) -> P09FormalSuite:
    root = repository_root.resolve()
    corpus = load_p09_runtime_corpus(root)
    if retrieval_snapshot_path is None:
        embedder = LocalSentenceTransformerEmbeddingAdapter(
            model_path=str(getattr(settings, "COURSERAG_EMBEDDING_MODEL_PATH")),
            model_name=str(getattr(settings, "COURSERAG_EMBEDDING_MODEL")),
            model_bundle_sha256=str(getattr(settings, "COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256")),
            weights_sha256=str(getattr(settings, "COURSERAG_EMBEDDING_WEIGHTS_SHA256")),
            device=str(getattr(settings, "COURSERAG_EMBEDDING_DEVICE")),
            dtype=str(getattr(settings, "COURSERAG_EMBEDDING_DTYPE")),
            max_length=int(getattr(settings, "COURSERAG_EMBEDDING_MAX_LENGTH")),
            batch_size=int(getattr(settings, "COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE")),
            query_prompt_name=str(getattr(settings, "COURSERAG_EMBEDDING_QUERY_PROMPT_NAME")),
        )
        dense = build_dense_indexes(
            corpus.candidates_by_course,
            embedder=embedder,
            budget=EmbeddingBudget(maximum_tokens=500_000),
            batch_size=int(getattr(settings, "COURSERAG_EMBEDDING_BATCH_SIZE")),
        )
    else:
        dense = {}
    cohere_secret = getattr(settings, "COURSERAG_COHERE_RERANKER_API_KEY")
    compatible_secret = getattr(settings, "COURSERAG_QA_API_KEY") or getattr(
        settings, "COMPATIBLE_API_KEY"
    )
    compatible_url = getattr(settings, "COURSERAG_QA_BASE_URL") or getattr(
        settings, "COMPATIBLE_BASE_URL"
    )
    compatible_model = getattr(settings, "COURSERAG_QA_MODEL") or getattr(
        settings, "COMPATIBLE_MODEL"
    )
    if not all((cohere_secret, compatible_secret, compatible_url, compatible_model)):
        raise ValueError("Formal P09 Provider configuration is incomplete")
    all_restored_results = _load_restored_results(checkpoint_path)
    for key, value in _load_retrieval_snapshot(retrieval_snapshot_path).items():
        all_restored_results.setdefault(key, value)
    restored_cohere_units = _restored_cohere_budget(all_restored_results)
    usage_budget = UsageBudget(
        max_cohere_search_units=max_cohere_search_units,
        cohere_search_units=restored_cohere_units,
    )
    inner_reranker = HTTPRerankerAdapter(
        provider_name="cohere",
        model_name=str(getattr(settings, "COURSERAG_COHERE_RERANKER_MODEL")),
        endpoint=str(getattr(settings, "COURSERAG_COHERE_RERANKER_BASE_URL")),
        api_key=cohere_secret.get_secret_value(),
        timeout_seconds=float(getattr(settings, "COURSERAG_RERANKER_TIMEOUT_SECONDS")),
        max_retries=int(getattr(settings, "COURSERAG_RERANKER_MAX_RETRIES")),
        max_document_tokens=int(getattr(settings, "COURSERAG_RERANKER_MAX_DOC_TOKENS")),
        budget=usage_budget,
        min_request_interval_seconds=6.0,
    )
    reranker = CachingReranker(
        inner_reranker,
        cache={},
        config_sha256=hashlib.sha256(b"p09-cohere-default-v1").hexdigest(),
        max_document_tokens=int(getattr(settings, "COURSERAG_RERANKER_MAX_DOC_TOKENS")),
    )
    rewrite = OpenAICompatibleRewriteProvider(
        base_url=str(compatible_url),
        api_key=compatible_secret,
        model=str(compatible_model),
        supports_thinking_toggle=True,
        timeout_seconds=float(getattr(settings, "COURSERAG_QA_TIMEOUT_SECONDS")),
    )
    qa = OpenAICompatibleQAProvider(
        base_url=str(compatible_url),
        api_key=compatible_secret,
        model=str(compatible_model),
        capability=OpenAICompatibleCapability(
            profile_name="deepseek_v4", supports_thinking_toggle=True
        ),
        timeout_seconds=float(getattr(settings, "COURSERAG_QA_TIMEOUT_SECONDS")),
        max_output_tokens=int(getattr(settings, "COURSERAG_QA_MAX_OUTPUT_TOKENS")),
        list_max_output_tokens=int(getattr(settings, "COURSERAG_QA_LIST_MAX_OUTPUT_TOKENS")),
        generation_reliability_enabled=generation_reliability_enabled,
        generation_reliability_factoid_enabled=generation_reliability_factoid_enabled,
    )
    tokenizer = LocalTokenizer(
        root / str(getattr(settings, "COURSERAG_CONTEXT_TOKENIZER_PATH")),
        tokenizer_id="coursepilot-local-tokenizer-v1",
        expected_sha256="ecb6f9fc369894346f0511f4074ca75cee5cd5f3b06d02f1ba35fcd39f8e121d",
    )
    return P09FormalSuite(
        corpus=corpus,
        dense_by_course=dense,
        reranker=reranker,
        rewrite_provider=rewrite,
        qa_provider=qa,
        tokenizer=tokenizer,
        budget=P09UsageBudget(
            max_deepseek_tokens=max_deepseek_tokens,
            max_cohere_search_units=max_cohere_search_units,
            deepseek_tokens=(
                initial_deepseek_tokens
                if initial_deepseek_tokens is not None
                else _restored_deepseek_budget(all_restored_results)
            ),
            cohere_search_units=restored_cohere_units,
        ),
        label_suffix=label_suffix,
        restored_results={
            key: value
            for key, value in all_restored_results.items()
            if key[0] not in discard_restored_variants
        },
        generation_reliability_enabled=generation_reliability_enabled,
    )


def _search_response(
    case: P09DevCase,
    state: object,
    candidates: Sequence[RetrievalCandidate],
    provider: str,
    model: str,
    usage: dict[str, object],
) -> SearchResponse:
    from courserag.query.models import QueryState

    typed_state = QueryState.model_validate(state)
    context = RequestContext()
    return SearchResponse(
        meta=ResponseMeta.from_context(context),
        query=QueryTrace(
            original=case.qa.query,
            normalized=typed_state.normalized_query,
            rewrites=list(typed_state.rewrites),
            intent_route=typed_state.intent_route.value,
            intent_rule_id=typed_state.intent_rule_id,
            intent_reason=typed_state.intent_reason,
            minimum_source_count=typed_state.minimum_source_count,
            retrieval_strategy=typed_state.retrieval_strategy.value,
        ),
        hits=[
            SearchHit(
                rank=rank,
                chunk_id=item.chunk_id,
                document_version=item.document_version_id,
                section_path=[item.section_id] if item.section_id else [],
                text=item.text,
                scores=ScoreBreakdown(
                    dense=item.dense_score,
                    sparse=item.sparse_score,
                    fusion=item.fusion_score,
                    rerank=item.rerank_score,
                ),
                evidence_ids=list(item.evidence_ids),
                source_tier=SourceTier.PRIMARY_SOURCE,
            )
            for rank, item in enumerate(candidates, start=1)
        ],
        retrieval=RetrievalTrace(
            retrieval_config_version="p09-candidate-v1",
            index_version=f"p09-{case.qa.course_id}",
            candidate_count=30,
            returned_count=len(candidates),
            provider=provider,
            model=model,
            usage=cast(dict[str, JsonValue], usage),
        ),
    )


def _search_snapshot(response: SearchResponse) -> tuple[dict[str, JsonValue], str]:
    snapshot = cast(dict[str, JsonValue], response.model_dump(mode="json"))
    digest = hashlib.sha256(
        json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return snapshot, digest


def _query_state_from_search(response: SearchResponse) -> QueryState:
    trace = response.query
    return QueryState(
        raw_query=trace.original,
        normalized_query=trace.normalized,
        current_query=trace.normalized,
        explicit_filters=ParsedFilters.model_validate(trace.parsed_filters),
        linked_knowledge_points=tuple(
            LinkedKnowledgePoint.model_validate(item) for item in trace.linked_knowledge_points
        ),
        rewrites=tuple(trace.rewrites),
        intent_route=IntentRoute(trace.intent_route or IntentRoute.FACT.value),
        intent_rule_id=trace.intent_rule_id or "intent.fact.default.v2",
        intent_reason=trace.intent_reason or "restored Search Snapshot",
        minimum_source_count=trace.minimum_source_count,
        retrieval_strategy=RetrievalStrategy(
            trace.retrieval_strategy or RetrievalStrategy.HYBRID.value
        ),
        retry_reason=trace.retry_reason,
    )


def _gold_evidence(search: SearchResponse, mapping: Mapping[str, str]) -> list[str]:
    return list(
        dict.fromkeys(
            mapping[value] for hit in search.hits for value in hit.evidence_ids if value in mapping
        )
    )


def _gold_context(context: object, mapping: Mapping[str, str]) -> list[str]:
    from courserag.contracts.retrieval import ContextPackage

    typed = ContextPackage.model_validate(context)
    return list(dict.fromkeys(mapping[value] for value in typed.evidence_map if value in mapping))


def _qa_cache_key(question: str, context: object, mode: str) -> str:
    from courserag.contracts.retrieval import ContextPackage

    typed = ContextPackage.model_validate(context)
    return hashlib.sha256(
        json.dumps(
            {"question": question, "context": typed.result_sha256, "mode": mode},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _estimated_qa_tokens(
    context: object, *, answer_shape: AnswerShapeDecision | None = None
) -> int:
    from courserag.contracts.retrieval import ContextPackage

    typed = ContextPackage.model_validate(context)
    output_tokens = 3200 if answer_shape and answer_shape.forced_type == AnswerType.LIST else 600
    return int((typed.token_count + output_tokens) * 1.5)


def _string_value(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _restored_deepseek_budget(
    restored_results: Mapping[tuple[str, str], P09SystemResult],
) -> int:
    cumulative = 0
    incremental = 0
    for (variant, _), result in restored_results.items():
        if variant not in {"q0", "q1", "q2", "q3"}:
            continue
        value = result.usage.get("deepseek_total_tokens", 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if result.usage_is_cumulative:
            cumulative = max(cumulative, int(value))
        else:
            incremental += int(value)
    return cumulative + incremental


def _restored_cohere_budget(
    restored_results: Mapping[tuple[str, str], P09SystemResult],
) -> int:
    """Restore the largest persisted cumulative Cohere usage counter.

    P09 results store one shared cumulative counter rather than per-case deltas.  Summing
    the values would therefore over-count on Resume; the maximum is the exact completed
    usage watermark.
    """
    watermarks: list[int] = []
    for result in restored_results.values():
        value = result.usage.get("cohere_search_units", 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        watermarks.append(int(value))
    return max(watermarks, default=0)


def _load_kp_candidates(root: Path) -> list[KnowledgePointCandidate]:
    path = root / "datasets/courserag_eval/v1/approved/ds3/p07_knowledge_points.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        KnowledgePointCandidate(
            knowledge_point_id=str(item["gold_kp_id"]),
            name=str(item["canonical_name"]),
            aliases=tuple(str(value) for value in item.get("aliases", [])),
            approved=True,
            publish_score=1.0,
        )
        for item in payload["knowledge_points"]
    ]


def _load_restored_results(
    checkpoint_path: Path | None,
) -> dict[tuple[str, str], P09SystemResult]:
    if checkpoint_path is None or not checkpoint_path.is_file():
        return {}
    payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    output: dict[tuple[str, str], P09SystemResult] = {}
    for case_id, state in payload.get("cases", {}).items():
        if state.get("status") != "succeeded" or ":" not in case_id:
            continue
        variant, qa_case_id = case_id.split(":", 1)
        output[(variant, qa_case_id)] = P09SystemResult.model_validate(state["result"])
    return output


def _load_retrieval_snapshot(
    snapshot_path: Path | None,
) -> dict[tuple[str, str], P09SystemResult]:
    if snapshot_path is None:
        return {}
    payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "courserag.p09-retrieval-snapshot.v1":
        raise ValueError("P09 Answer Grounding requires a v1 Retrieval Snapshot")
    if payload.get("approved_bundle_sha256") != (
        "5a84bac041375310d5bb80f17f7481464d07dbcf75f9f980c6b8a030e58af0c1"
    ):
        raise ValueError("P09 Retrieval Snapshot uses a different Approved Bundle")
    if payload.get("test_access") is not False:
        raise ValueError("P09 Retrieval Snapshot must be Dev-only")
    cases = payload.get("cases")
    if not isinstance(cases, dict) or len(cases) != 60:
        raise ValueError("P09 Retrieval Snapshot requires exactly 60 Dev cases")
    output: dict[tuple[str, str], P09SystemResult] = {}
    for case_id, item in cases.items():
        if not isinstance(case_id, str) or not isinstance(item, dict):
            raise ValueError("P09 Retrieval Snapshot contains an invalid case")
        snapshot = item.get("search_response")
        expected_sha256 = item.get("search_response_sha256")
        if not isinstance(snapshot, dict) or not isinstance(expected_sha256, str):
            raise ValueError("P09 Retrieval Snapshot case is incomplete")
        actual_sha256 = hashlib.sha256(
            json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        if actual_sha256 != expected_sha256:
            raise ValueError("P09 Retrieval Snapshot case Hash mismatch")
        output[("b7", case_id)] = P09SystemResult(
            search_snapshot=cast(dict[str, JsonValue], snapshot),
            search_snapshot_sha256=expected_sha256,
        )
    return output
