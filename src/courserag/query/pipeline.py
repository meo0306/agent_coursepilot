from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from time import perf_counter
from typing import Protocol

from courserag.query.models import (
    IntentRoute,
    LinkedKnowledgePoint,
    ParsedFilters,
    QueryPipelineProfile,
    QueryState,
    QueryStepTrace,
    RetrievalStrategy,
    StepStatus,
)


@dataclass(frozen=True)
class KnowledgePointCandidate:
    knowledge_point_id: str
    name: str
    aliases: tuple[str, ...] = ()
    approved: bool = False
    publish_score: float = 0.0


class RewriteProvider(Protocol):
    def rewrite(self, query: str, *, max_rewrites: int) -> Sequence[str]: ...


class KnowledgePointCatalog(Protocol):
    def list_candidates(self) -> Sequence[KnowledgePointCandidate]: ...


class QueryPipeline:
    """Deterministic orchestration around optional, auditable query steps."""

    def __init__(
        self,
        *,
        profile: QueryPipelineProfile | None = None,
        knowledge_points: KnowledgePointCatalog | None = None,
        rewrite_provider: RewriteProvider | None = None,
    ) -> None:
        self.profile = profile or QueryPipelineProfile()
        self.knowledge_points = knowledge_points
        self.rewrite_provider = rewrite_provider

    def process(self, query: str) -> QueryState:
        if not query.strip():
            raise ValueError("query must not be blank")
        state = QueryState(raw_query=query, normalized_query=query, current_query=query)
        steps: tuple[tuple[str, bool, Callable[[QueryState], QueryState]], ...] = (
            ("normalize", self.profile.normalize, self._normalize),
            ("filter_parser", self.profile.filter_parser, self._filters),
            ("kp_link", self.profile.kp_link, self._kp_link),
            ("alias_expansion", self.profile.alias_expansion, self._aliases),
            ("intent_router", self.profile.intent_router, self._intent),
            ("retrieval_strategy", self.profile.retrieval_strategy, self._strategy),
            ("multi_query", self.profile.multi_query, self._multi_query),
        )
        for name, enabled, callback in steps:
            state = self._run_step(state, name, enabled, callback)
        return state

    def apply_low_recall_retry(self, state: QueryState, *, reason: str | None) -> QueryState:
        if not self.profile.low_recall_retry or reason is None or state.retry_reason is not None:
            return self._append_skipped(state, "low_recall_retry")
        before = _digest(state.model_dump(mode="json"))
        rewritten = state.model_copy(
            update={
                "retry_reason": reason,
                "rewrites": tuple(dict.fromkeys((*state.rewrites, state.raw_query))),
                "warnings": (*state.warnings, f"LOW_RECALL_RETRY:{reason}"),
            }
        )
        return self._append_trace(rewritten, "low_recall_retry", StepStatus.SUCCEEDED, before)

    def _run_step(
        self,
        state: QueryState,
        name: str,
        enabled: bool,
        callback: Callable[[QueryState], QueryState],
    ) -> QueryState:
        if not enabled:
            return self._append_skipped(state, name)
        started = perf_counter()
        before = _digest(state.model_dump(mode="json"))
        try:
            updated = callback(state)
            status = StepStatus.SUCCEEDED
        except Exception:
            if name != "multi_query":
                raise
            updated = state.model_copy(
                update={"warnings": (*state.warnings, "MULTI_QUERY_PROVIDER_FAILED")}
            )
            status = StepStatus.FALLBACK_ORIGINAL
        return self._append_trace(
            updated,
            name,
            status,
            before,
            duration_ms=max(0, round((perf_counter() - started) * 1000)),
        )

    @staticmethod
    def _normalize(state: QueryState) -> QueryState:
        normalized = unicodedata.normalize("NFKC", state.raw_query)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return state.model_copy(
            update={"normalized_query": normalized, "current_query": normalized}
        )

    @staticmethod
    def _filters(state: QueryState) -> QueryState:
        query = state.current_query
        fragments: list[str] = []
        section_terms: list[str] = []
        exclusions: list[str] = []
        page_start: int | None = None
        page_end: int | None = None
        for match in re.finditer(r"(?:第)?([一二三四五六七八九十百\d]+)(?:章|节)", query):
            fragments.append(match.group(0))
            section_terms.append(match.group(0))
        page = re.search(r"第?\s*(\d+)\s*(?:[-~—至]\s*(\d+)\s*)?页", query)
        if page:
            fragments.append(page.group(0))
            page_start = int(page.group(1))
            page_end = int(page.group(2) or page.group(1))
        for match in re.finditer(r"(?:不要|排除|不包括)\s*([^，。；;]+)", query):
            fragments.append(match.group(0))
            exclusions.append(match.group(1).strip())
        filters = ParsedFilters(
            section_terms=tuple(dict.fromkeys(section_terms)),
            page_start=page_start,
            page_end=page_end,
            exclusions=tuple(dict.fromkeys(exclusions)),
            source_fragments=tuple(fragments),
        )
        return state.model_copy(update={"explicit_filters": filters})

    def _kp_link(self, state: QueryState) -> QueryState:
        if self.knowledge_points is None:
            return state
        query = _name(state.current_query)
        matches: list[LinkedKnowledgePoint] = []
        for item in self.knowledge_points.list_candidates():
            names = (item.name, *item.aliases)
            normalized = tuple(_name(value) for value in names if value.strip())
            method = ""
            confidence = 0.0
            if _name(item.name) in query:
                method, confidence = "canonical_exact", 1.0
            elif any(alias in query for alias in normalized[1:]):
                method, confidence = "alias_exact", 0.98
            else:
                confidence = max(
                    (SequenceMatcher(None, query, value).ratio() for value in normalized), default=0
                )
                if confidence >= 0.72:
                    method = "fuzzy_candidate"
            if not method:
                continue
            eligible = item.approved or item.publish_score >= 0.75
            matches.append(
                LinkedKnowledgePoint(
                    knowledge_point_id=item.knowledge_point_id,
                    name=item.name,
                    confidence=confidence,
                    match_method=method,
                    hard_filter=eligible and confidence >= self.profile.kp_hard_filter_threshold,
                )
            )
        matches.sort(key=lambda value: (-value.confidence, value.knowledge_point_id))
        return state.model_copy(update={"linked_knowledge_points": tuple(matches)})

    def _aliases(self, state: QueryState) -> QueryState:
        aliases: list[str] = []
        if self.knowledge_points is not None:
            by_id = {
                item.knowledge_point_id: item for item in self.knowledge_points.list_candidates()
            }
            for link in state.linked_knowledge_points:
                item = by_id.get(link.knowledge_point_id)
                if item is not None and (item.approved or item.publish_score >= 0.75):
                    aliases.extend(item.aliases)
        return state.model_copy(update={"aliases": tuple(dict.fromkeys(aliases))})

    @staticmethod
    def _intent(state: QueryState) -> QueryState:
        query = state.current_query.lower()
        quoted_terms = re.findall(r"“[^”]+”|\"[^\"]+\"", query)
        if (
            any(term in query for term in ("区别", "异同", "相比", "对比", "vs"))
            or query.count("什么") >= 2
            or ("分别" in query and any(term in query for term in ("关注", "目标")))
        ):
            route = (
                IntentRoute.COMPARISON,
                "intent.comparison.explicit_relation.v2",
                "explicit comparison or paired-target wording",
                2,
            )
        elif (
            any(term in query for term in ("分别如何说明", "分别说明", "分别介绍", "分别在哪"))
            or len(state.explicit_filters.section_terms) > 1
            or any(term in query for term in ("跨章", "跨章节", "综合多个章节"))
            or (len(quoted_terms) >= 2 and "分别" in query)
        ):
            route = (
                IntentRoute.CROSS_SECTION,
                "intent.cross_section.paired_sources.v2",
                "paired concepts or explicit cross-section wording",
                2,
            )
        elif (
            any(term in query for term in ("如何定义", "定义或说明", "什么是", "含义"))
            or re.search(r"(?:定义|概念)\s*[？?]?$", query) is not None
        ):
            route = (
                IntentRoute.DEFINITION,
                "intent.definition.explicit_definition.v2",
                "explicit definition wording",
                1,
            )
        elif any(
            term in query
            for term in ("应用场景", "作用或限制", "应用中的", "用于", "例子", "案例", "举例")
        ):
            route = (
                IntentRoute.EXAMPLE_APPLICATION,
                "intent.example_application.use_case.v2",
                "application, example, role, or limitation wording",
                1,
            )
        elif any(
            term in query
            for term in (
                "步骤",
                "流程",
                "按什么过程",
                "条件与过程",
                "怎样配置和执行",
                "如何配置和执行",
                "从迭代到收敛",
                "先后",
            )
        ):
            route = (
                IntentRoute.PROCEDURE,
                "intent.procedure.explicit_sequence.v2",
                "explicit sequence, process, configuration, or convergence wording",
                1,
            )
        else:
            route = (
                IntentRoute.FACT,
                "intent.fact.default.v2",
                "no higher-specificity intent rule matched",
                1,
            )
        intent, rule_id, reason, minimum_source_count = route
        return state.model_copy(
            update={
                "intent_route": intent,
                "intent_rule_id": rule_id,
                "intent_reason": reason,
                "minimum_source_count": minimum_source_count,
            }
        )

    @staticmethod
    def _strategy(state: QueryState) -> QueryState:
        if state.explicit_filters.source_fragments or any(
            item.hard_filter for item in state.linked_knowledge_points
        ):
            strategy = RetrievalStrategy.METADATA_FILTERED
        elif any(term in state.current_query for term in ("无答案", "无法回答", "教材中没有")):
            strategy = RetrievalStrategy.UNANSWERABLE_AUDIT
        else:
            strategy = RetrievalStrategy.HYBRID
        return state.model_copy(update={"retrieval_strategy": strategy})

    def _multi_query(self, state: QueryState) -> QueryState:
        if self.rewrite_provider is None or self.profile.max_rewrites == 0:
            return state
        required = _required_terms(state)
        rewrites = []
        for value in self.rewrite_provider.rewrite(
            state.current_query, max_rewrites=self.profile.max_rewrites
        ):
            candidate = " ".join(value.split()).strip()
            if not candidate or candidate == state.current_query:
                continue
            if required and not all(term.casefold() in candidate.casefold() for term in required):
                continue
            rewrites.append(candidate)
        return state.model_copy(
            update={
                "rewrites": tuple(dict.fromkeys(rewrites))[: self.profile.max_rewrites],
                "required_terms": required,
            }
        )

    def _append_skipped(self, state: QueryState, name: str) -> QueryState:
        before = _digest(state.model_dump(mode="json"))
        return self._append_trace(state, name, StepStatus.SKIPPED_DISABLED, before)

    @staticmethod
    def _append_trace(
        state: QueryState,
        name: str,
        status: StepStatus,
        before: str,
        *,
        duration_ms: int = 0,
    ) -> QueryState:
        output = _digest(state.model_dump(mode="json", exclude={"traces"}))
        trace = QueryStepTrace(
            step=name,
            status=status,
            input_sha256=before,
            output_sha256=output,
            duration_ms=duration_ms,
        )
        return state.model_copy(update={"traces": (*state.traces, trace)})


def _required_terms(state: QueryState) -> tuple[str, ...]:
    terms = re.findall(r"[A-Za-z][A-Za-z0-9+*/.-]*|[A-Z]/[A-Z]/[A-Z]", state.raw_query)
    terms.extend(
        item.name
        for item in state.linked_knowledge_points
        if item.match_method == "canonical_exact" and item.confidence >= 0.9
    )
    return tuple(dict.fromkeys(terms))


def _name(value: str) -> str:
    return "".join(unicodedata.normalize("NFKC", value).casefold().split())


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
        ).encode()
    ).hexdigest()


def aggregate_query_candidates(
    ranked_lists: Iterable[Sequence[str]], *, rrf_k: int = 60
) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for values in ranked_lists:
        for rank, chunk_id in enumerate(values, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
