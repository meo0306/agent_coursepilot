"""Database-backed Window Result cache with recoverable attempt evidence."""

from __future__ import annotations

from courserag.domain.knowledge_point import SectionWindow, WindowExtractionResult
from courserag.jobs.artifacts import FileArtifactStore
from courserag.persistence.base import utc_now
from courserag.persistence.models import (
    ArtifactRecord,
    KnowledgePointWindowRunRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class DatabaseExtractionCache:
    def __init__(
        self,
        repository: CourseRAGRepository,
        artifact_store: FileArtifactStore,
        *,
        batch_id: str,
        provider: str,
        model: str,
        prompt_sha256: str,
        extractor_profile_sha256: str,
        worker_id: str,
    ) -> None:
        self.repository = repository
        self.artifact_store = artifact_store
        self.batch_id = batch_id
        self.provider = provider
        self.model = model
        self.prompt_sha256 = prompt_sha256
        self.extractor_profile_sha256 = extractor_profile_sha256
        self.worker_id = worker_id
        self._running_by_cache_key: dict[str, KnowledgePointWindowRunRecord] = {}

    def get(self, cache_key: str) -> WindowExtractionResult | None:
        run = self.repository.find_cached_kp_window_run(cache_key)
        if run is None or run.artifact_id is None:
            return None
        artifact = self.repository.get_artifact(run.artifact_id)
        if artifact is None or not self.artifact_store.verify(artifact.uri, artifact.sha256):
            return None
        return WindowExtractionResult.model_validate_json(
            self.artifact_store.read(artifact.uri, expected_sha256=artifact.sha256)
        )

    def begin(self, window: SectionWindow, cache_key: str) -> None:
        persisted = self.repository.get_kp_window(self.batch_id, window.window_id)
        if persisted is None:
            raise RuntimeError("Knowledge Point Window must be persisted before extraction")
        stale = self.repository.get_running_kp_window_run(persisted.id)
        if stale is not None:
            stale.status = "failed"
            stale.error_code = "STALE_WINDOW_RECOVERED"
            stale.error_message = "Previous Window attempt was recovered after interruption"
            stale.completed_at = utc_now()
        run = KnowledgePointWindowRunRecord(
            window_id=persisted.id,
            attempt_number=self.repository.next_kp_window_attempt(persisted.id),
            cache_key=cache_key,
            status="running",
            provider=self.provider,
            model_name=self.model,
            prompt_sha256=self.prompt_sha256,
            extractor_profile_sha256=self.extractor_profile_sha256,
            worker_id=self.worker_id,
            created_at=utc_now(),
        )
        self.repository.add(run)
        self.repository.flush()
        self._running_by_cache_key[cache_key] = run

    def put(self, cache_key: str, result: WindowExtractionResult) -> None:
        run = self._running_by_cache_key.pop(cache_key, None)
        if run is None:
            raise RuntimeError("Knowledge Point Window Result has no running attempt")
        stored = self.artifact_store.put(
            result.model_dump_json().encode("utf-8"),
            media_type="application/vnd.courserag.kp-window-result+json",
        )
        artifact = self.repository.get_or_create_artifact(
            ArtifactRecord(
                uri=stored.uri,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                media_type=stored.media_type,
                status="available",
                last_verified_at=utc_now(),
            )
        )
        run.artifact_id = artifact.id
        run.status = "succeeded"
        run.usage_json = result.usage.model_dump(mode="json")
        run.duration_ms = result.duration_ms
        run.completed_at = utc_now()
        self.repository.flush()

    def fail(self, window: SectionWindow, cache_key: str, error_code: str) -> None:
        del window
        run = self._running_by_cache_key.pop(cache_key, None)
        if run is None:
            return
        run.status = "failed"
        run.error_code = error_code[:160]
        run.error_message = "Knowledge Point Window extraction failed; inspect protected logs"
        run.completed_at = utc_now()
        self.repository.flush()
