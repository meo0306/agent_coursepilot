from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from time import perf_counter
from typing import Protocol

from courserag.contracts.common import CourseRAGError, ErrorCode, ResponseMeta
from courserag.contracts.retrieval import (
    QueryTrace,
    RankBreakdown,
    RetrievalTrace,
    ScoreBreakdown,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceTier,
)
from courserag.indexing.verified_overlay import (
    VerifiedOverlayHit,
    fuse_overlay_hits,
    retrieval_snapshot_id,
)
from courserag.persistence.base import utc_now
from courserag.persistence.models import RetrievalRunRecord
from courserag.persistence.repositories import CourseRAGRepository
from courserag.providers.reranker import RerankerFailurePolicy, RerankResult
from courserag.retrieval.models import RetrievalFilter


class RetrievalPipelinePort(Protocol):
    def search(
        self,
        query: str,
        *,
        filters: RetrievalFilter,
        candidate_k: int,
        top_n: int,
        failure_policy: RerankerFailurePolicy,
    ) -> tuple[RerankResult, dict[str, int]]: ...


class VerifiedOverlaySearchPort(Protocol):
    def search(
        self,
        *,
        overlay_version_id: str,
        query: str,
        top_k: int,
        knowledge_point_ids: tuple[str, ...] = (),
    ) -> list[VerifiedOverlayHit]: ...


class VersionedSearchService:
    def __init__(
        self,
        *,
        repository: CourseRAGRepository,
        pipeline_factory: Callable[[str], RetrievalPipelinePort],
        retrieval_config_version: str,
        manifest_sha256: str,
        production: bool = True,
        overlay_search: VerifiedOverlaySearchPort | None = None,
    ) -> None:
        self.repository = repository
        self.pipeline_factory = pipeline_factory
        self.retrieval_config_version = retrieval_config_version
        self.manifest_sha256 = manifest_sha256
        self.production = production
        self.overlay_search = overlay_search

    def search(self, request: SearchRequest) -> SearchResponse:
        started = perf_counter()
        knowledge_base = self.repository.get_knowledge_base_by_course(request.course_id)
        if knowledge_base is None or knowledge_base.active_index_version_id is None:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.INDEX_NOT_READY,
                message="CourseRAG has no valid Active Index.",
            )
        index_version_id = knowledge_base.active_index_version_id
        if request.filters.index_version not in {None, index_version_id}:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.VERSION_CONFLICT,
                message="Requested Index Version is not active.",
            )
        normalized = " ".join(request.query.split())
        request_hash = _sha256(
            {"request": request.model_dump(mode="json"), "index_version_id": index_version_id}
        )
        query_run = self.repository.get_or_create_normalize_query_run(
            knowledge_base_id=knowledge_base.id,
            request_id=request.context.request_id,
            trace_id=request.context.trace_id,
            input_sha256=hashlib.sha256(request.query.encode()).hexdigest(),
            normalized_query=normalized,
        )
        filters = RetrievalFilter(
            course_id=request.course_id,
            index_version_id=index_version_id,
            document_ids=tuple(request.filters.document_ids),
            document_version_ids=tuple(request.filters.document_version_ids),
            section_ids=tuple(path[-1] for path in request.filters.section_paths if path),
            knowledge_point_ids=tuple(request.filters.knowledge_point_ids),
            source_tiers=tuple(item.value for item in request.filters.source_tiers),
        )
        result, latency = self.pipeline_factory(index_version_id).search(
            normalized,
            filters=filters,
            candidate_k=request.retrieval.candidate_k,
            top_n=request.retrieval.return_top_n,
            failure_policy=(
                RerankerFailurePolicy.FUSION_ORDER
                if self.production
                else RerankerFailurePolicy.FAIL_SAMPLE
            ),
        )
        hits = [self._hit(item, rank) for rank, item in enumerate(result.candidates, start=1)]
        overlay_hits: list[VerifiedOverlayHit] = []
        overlay_version = knowledge_base.active_verified_index_version_id
        source_tiers = set(request.filters.source_tiers)
        include_overlay = not source_tiers or SourceTier.TEACHER_VERIFIED in source_tiers
        include_primary = not source_tiers or SourceTier.PRIMARY_SOURCE in source_tiers
        if not include_primary:
            hits = []
        if self.overlay_search is not None and overlay_version is not None and include_overlay:
            overlay_hits = self.overlay_search.search(
                overlay_version_id=overlay_version,
                query=normalized,
                top_k=request.retrieval.candidate_k,
                knowledge_point_ids=tuple(request.filters.knowledge_point_ids),
            )
            hits = self._fuse_hits(
                hits,
                overlay_hits,
                overlay_version=overlay_version,
                top_n=request.retrieval.return_top_n,
            )
        debug_trace: dict[str, int | str] = {"index_version_id": index_version_id}
        if overlay_version is not None:
            debug_trace.update(
                {
                    "verified_overlay_version": overlay_version,
                    "verified_overlay_hit_count": len(overlay_hits),
                }
            )
        result_payload = [item.model_dump(mode="json") for item in hits]
        run = RetrievalRunRecord(
            query_run_id=query_run.id,
            index_version_id=index_version_id,
            retrieval_mode=request.retrieval.mode.value,
            top_k=request.retrieval.return_top_n,
            result_json=result_payload,
            latency_ms=max(0, (perf_counter() - started) * 1000),
            status="succeeded",
            request_sha256=request_hash,
            config_sha256=hashlib.sha256(self.retrieval_config_version.encode()).hexdigest(),
            result_sha256=_sha256(result_payload),
            reranker_provider=result.provider,
            reranker_model=result.model,
            candidate_k=request.retrieval.candidate_k,
            top_n=request.retrieval.return_top_n,
            dense_latency_ms=latency.get("dense"),
            sparse_latency_ms=latency.get("sparse"),
            fusion_latency_ms=latency.get("fusion"),
            rerank_latency_ms=latency.get("rerank"),
            usage_json=result.usage.model_dump(mode="json"),
            fallback_applied=result.fallback_applied,
            warnings_json=result.warnings,
            debug_trace_json=debug_trace,
            completed_at=utc_now(),
        )
        self.repository.add_retrieval_run(run)
        duration = max(0, round((perf_counter() - started) * 1000))
        return SearchResponse(
            meta=ResponseMeta.from_context(
                request.context, duration_ms=duration, warnings=result.warnings
            ),
            query=QueryTrace(original=request.query, normalized=normalized),
            hits=hits,
            retrieval=RetrievalTrace(
                retrieval_config_version=self.retrieval_config_version,
                index_version=index_version_id,
                candidate_count=request.retrieval.candidate_k,
                returned_count=len(hits),
                run_id=run.id,
                provider=result.provider,
                model=result.model,
                manifest_sha256=self.manifest_sha256,
                stage_latency_ms=latency,
                fallback_applied=result.fallback_applied,
                warnings=result.warnings,
                usage=result.usage.model_dump(mode="json"),
                debug_trace=debug_trace,
                verified_overlay_version=overlay_version,
                retrieval_snapshot_id=retrieval_snapshot_id(index_version_id, overlay_version),
            ),
        )

    @staticmethod
    def _hit(item: object, rank: int) -> SearchHit:
        from courserag.retrieval.models import RetrievalCandidate

        if not isinstance(item, RetrievalCandidate):
            raise TypeError("Retrieval pipeline returned an invalid Candidate")
        return SearchHit(
            rank=rank,
            chunk_id=item.chunk_id,
            document_id=item.document_id,
            document_version=item.document_version_id,
            section_path=[item.section_id] if item.section_id else [],
            text=item.text,
            scores=ScoreBreakdown(
                dense=item.dense_score,
                sparse=item.sparse_score,
                fusion=item.fusion_score,
                rerank=item.rerank_score,
            ),
            ranks=RankBreakdown(
                dense=item.dense_rank,
                sparse=item.sparse_rank,
                fusion=item.fusion_rank,
                rerank=item.rerank_rank,
            ),
            evidence_ids=list(item.evidence_ids),
            source_tier=SourceTier(item.source_tier),
        )

    @staticmethod
    def _fuse_hits(
        primary_hits: list[SearchHit],
        overlay_hits: list[VerifiedOverlayHit],
        *,
        overlay_version: str,
        top_n: int,
    ) -> list[SearchHit]:
        primary_by_id = {item.chunk_id: item for item in primary_hits}
        overlay_by_id = {item.verified_content_id: item for item in overlay_hits}
        primary_scores = [
            (item.chunk_id, item.scores.rerank or item.scores.fusion or 0.0)
            for item in primary_hits
        ]
        fused = fuse_overlay_hits(primary_scores, overlay_hits, top_k=top_n)
        output: list[SearchHit] = []
        for rank, (identifier, score, tier) in enumerate(fused, start=1):
            if tier == SourceTier.PRIMARY_SOURCE.value:
                original = primary_by_id[identifier]
                output.append(
                    original.model_copy(
                        update={
                            "rank": rank,
                            "scores": original.scores.model_copy(update={"fusion": score}),
                            "ranks": original.ranks.model_copy(update={"fusion": rank}),
                        }
                    )
                )
                continue
            overlay = overlay_by_id[identifier]
            output.append(
                SearchHit(
                    rank=rank,
                    chunk_id=identifier,
                    document_id=identifier,
                    document_version=overlay_version,
                    title=overlay.title,
                    text=overlay.text,
                    scores=ScoreBreakdown(
                        dense=overlay.dense_score,
                        sparse=overlay.sparse_score,
                        fusion=score,
                    ),
                    ranks=RankBreakdown(fusion=rank),
                    evidence_ids=list(overlay.evidence_ids),
                    source_tier=SourceTier.TEACHER_VERIFIED,
                )
            )
        return output


def _sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
