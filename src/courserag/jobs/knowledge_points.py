"""P07 offline Knowledge Point extraction and materialization coordinator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import uuid4

from courserag.chunking.tokenizer import TokenCounter
from courserag.domain.knowledge_point import (
    SectionWindow,
    WindowEvidence,
    canonical_json_bytes,
    sha256_bytes,
)
from courserag.jobs.artifacts import FileArtifactStore
from courserag.knowledge_points.cache import DatabaseExtractionCache
from courserag.knowledge_points.materialize import materialize_knowledge_points
from courserag.knowledge_points.normalize import consolidate_candidates
from courserag.knowledge_points.profile import KnowledgePointPipelineProfile
from courserag.knowledge_points.provider import (
    KnowledgePointExtractionRunner,
    KnowledgePointProvider,
)
from courserag.knowledge_points.scoring import KnowledgePointScorer
from courserag.knowledge_points.windows import SectionSource, SectionWindowBuilder
from courserag.persistence.base import utc_now
from courserag.persistence.models import (
    KnowledgePointExtractionBatchRecord,
    KnowledgePointRecord,
    KnowledgePointWindowRecord,
    SectionRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


@dataclass(frozen=True)
class KnowledgePointPipelineResult:
    batch: KnowledgePointExtractionBatchRecord
    knowledge_points: tuple[KnowledgePointRecord, ...]


class KnowledgePointPipelineCoordinator:
    def __init__(
        self,
        repository: CourseRAGRepository,
        artifact_store: FileArtifactStore,
        provider: KnowledgePointProvider,
        tokenizer: TokenCounter,
        profile: KnowledgePointPipelineProfile,
        *,
        prompt: str,
        prompt_sha256: str,
        concurrency: int = 4,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
        retry_max_seconds: float = 30.0,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.provider = provider
        self.tokenizer = tokenizer
        self.profile = profile
        self.prompt = prompt
        self.prompt_sha256 = prompt_sha256
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds
        self.retry_max_seconds = retry_max_seconds

    def run(
        self,
        *,
        knowledge_base_id: str,
        document_version_ids: tuple[str, ...],
        build_job_id: str | None = None,
        force: bool = False,
    ) -> KnowledgePointPipelineResult:
        knowledge_base = self.repository.get_knowledge_base(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("Knowledge Point pipeline Knowledge Base not found")
        sections = self.repository.list_sections_for_document_versions(document_version_ids)
        sources = tuple(
            self._source(knowledge_base_id, knowledge_base.course_id, section)
            for section in sections
        )
        sources = tuple(source for source in sources if source.evidence)
        windows = tuple(
            window
            for source in sources
            for window in SectionWindowBuilder(self.profile.window, self.tokenizer).build(source)
        )
        if not windows:
            raise ValueError("Knowledge Point pipeline has no Evidence Windows")
        identity = sha256_bytes(
            canonical_json_bytes(
                {
                    "knowledge_base_id": knowledge_base_id,
                    "document_version_ids": sorted(document_version_ids),
                    "window_ids": [window.window_id for window in windows],
                    "provider": self.provider.provider_name,
                    "model": self.provider.model_name,
                    "prompt_sha256": self.prompt_sha256,
                    "profile_sha256": self.profile.profile_sha256,
                }
            )
        )
        batch = self.repository.get_kp_extraction_batch(knowledge_base_id, identity)
        if batch is None:
            batch = KnowledgePointExtractionBatchRecord(
                knowledge_base_id=knowledge_base_id,
                build_job_id=build_job_id,
                identity_sha256=identity,
                provider=self.provider.provider_name,
                model_name=self.provider.model_name,
                prompt_sha256=self.prompt_sha256,
                extractor_profile_sha256=self.profile.profile_sha256,
                scoring_profile_sha256=self.profile.scoring.profile_sha256,
                status="queued",
                window_count=len(windows),
                created_at=utc_now(),
            )
            self.repository.add(batch)
            self.repository.flush()
        self._persist_windows(batch.id, windows)
        batch.status = "running"
        batch.started_at = batch.started_at or utc_now()
        batch.completed_at = None
        worker_id = f"kp-worker-{uuid4().hex[:16]}"
        cache = DatabaseExtractionCache(
            self.repository,
            self.artifact_store,
            batch_id=batch.id,
            provider=self.provider.provider_name,
            model=self.provider.model_name,
            prompt_sha256=self.prompt_sha256,
            extractor_profile_sha256=self.profile.profile_sha256,
            worker_id=worker_id,
        )
        runner = KnowledgePointExtractionRunner(
            self.provider,
            cache,
            prompt=self.prompt,
            prompt_sha256=self.prompt_sha256,
            extractor_profile_sha256=self.profile.profile_sha256,
            concurrency=self.concurrency,
            max_retries=self.max_retries,
            retry_base_seconds=self.retry_base_seconds,
            retry_max_seconds=self.retry_max_seconds,
        )
        try:
            results = runner.run(windows, force=force)
            drafts = consolidate_candidates(windows, results)
            scorer = KnowledgePointScorer(self.profile.scoring)
            scores = {draft.stable_key: scorer.score(draft) for draft in drafts}
            records = materialize_knowledge_points(
                self.repository,
                extraction_batch_id=batch.id,
                extractor_version=self.profile.version,
                extractor_profile_sha256=self.profile.profile_sha256,
                drafts=drafts,
                scores=scores,
            )
        except Exception:
            batch.status = "failed"
            batch.provider_call_count += runner.last_provider_call_count
            batch.cache_hit_count += runner.last_cache_hit_count
            batch.completed_at = utc_now()
            self.repository.flush()
            raise
        batch.status = "succeeded"
        batch.provider_call_count += runner.last_provider_call_count
        batch.cache_hit_count += runner.last_cache_hit_count
        batch.usage_json = {
            "input_tokens": sum(item.usage.input_tokens or 0 for item in results),
            "output_tokens": sum(item.usage.output_tokens or 0 for item in results),
            "total_tokens": sum(item.usage.total_tokens or 0 for item in results),
        }
        batch.completed_at = utc_now()
        self.repository.audit(
            "knowledge_points.extracted",
            "knowledge_base",
            knowledge_base_id,
            details={
                "batch_id": batch.id,
                "window_count": len(windows),
                "knowledge_point_count": len(records),
                "provider_call_count": runner.last_provider_call_count,
                "cache_hit_count": runner.last_cache_hit_count,
            },
        )
        self.repository.flush()
        return KnowledgePointPipelineResult(batch=batch, knowledge_points=records)

    def _source(
        self, knowledge_base_id: str, course_id: str, section: SectionRecord
    ) -> SectionSource:
        section_id = section.id
        evidence_records = self.repository.list_evidence_for_section(section_id)
        evidence = tuple(
            WindowEvidence(
                evidence_id=record.stable_key,
                text=record.text,
                content_sha256=record.content_sha256,
                ordinal=index,
                block_id=record.block_id,
                source_mode=_source_mode(record.metadata_json.get("source_mode")),
                confidence=record.confidence,
                warning_codes=tuple(record.metadata_json.get("warning_codes", [])),
            )
            for index, record in enumerate(evidence_records)
        )
        return SectionSource(
            knowledge_base_id=knowledge_base_id,
            course_id=course_id,
            section_id=section_id,
            section_title=section.heading,
            evidence=evidence,
        )

    def _persist_windows(self, batch_id: str, windows: tuple[SectionWindow, ...]) -> None:
        for window in windows:
            existing = self.repository.get_kp_window(batch_id, window.window_id)
            if existing is not None:
                if existing.content_sha256 != window.content_sha256:
                    raise ValueError("Persisted Knowledge Point Window Hash conflict")
                continue
            self.repository.add(
                KnowledgePointWindowRecord(
                    batch_id=batch_id,
                    section_id=window.section_id,
                    window_key=window.window_id,
                    ordinal=window.ordinal,
                    content_sha256=window.content_sha256,
                    profile_sha256=window.profile_sha256,
                    token_count=window.token_count,
                    evidence_ids_json=[item.evidence_id for item in window.evidence],
                    warning_codes_json=list(window.warning_codes),
                    created_at=utc_now(),
                )
            )
        self.repository.flush()


def _source_mode(value: object) -> Literal["native", "ocr", "hybrid"]:
    if value == "ocr":
        return "ocr"
    if value == "hybrid":
        return "hybrid"
    return "native"
