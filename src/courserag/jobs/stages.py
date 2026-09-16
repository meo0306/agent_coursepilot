from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Protocol

from courserag.jobs.artifacts import FileArtifactStore, StoredArtifact
from courserag.persistence.base import utc_now
from courserag.persistence.models import ArtifactRecord, BuildStageRunRecord
from courserag.persistence.repositories import CourseRAGRepository


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class StageContext:
    build_job_id: str
    knowledge_base_id: str
    input_hashes: tuple[str, ...]
    input_identities: tuple[str, ...]
    config: dict[str, object]
    provider_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StageOutput:
    content: bytes
    media_type: str = "application/json"
    counts: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


class BuildStage(Protocol):
    """Pure stage computation.

    Implementations return bytes and must not perform external writes. The runner owns the
    content-addressed artifact side effect, which makes at-least-once replay idempotent.
    """

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def execute(self, context: StageContext) -> StageOutput: ...


def stage_fingerprint(stage: BuildStage, context: StageContext) -> str:
    if not context.knowledge_base_id:
        raise ValueError("Stage cache scope requires a knowledge base ID")
    if len(context.input_hashes) != len(context.input_identities):
        raise ValueError("Stage input hashes and identities must have equal cardinality")
    provider_metadata = _validated_provider_metadata(context.provider_metadata)
    return sha256_json(
        {
            "stage_name": stage.name,
            "stage_version": stage.version,
            "knowledge_base_id": context.knowledge_base_id,
            "inputs": [
                {"identity": identity, "sha256": digest}
                for identity, digest in zip(
                    context.input_identities, context.input_hashes, strict=True
                )
            ],
            "config": context.config,
            "provider": provider_metadata,
        }
    )


_ALLOWED_PROVIDER_METADATA_KEYS = {
    "provider",
    "model",
    "model_version",
    "prompt_hash",
    "usage",
}


def _validated_provider_metadata(metadata: dict[str, object]) -> dict[str, object]:
    unexpected = sorted(set(metadata) - _ALLOWED_PROVIDER_METADATA_KEYS)
    if unexpected:
        raise ValueError(f"Unsupported provider metadata keys: {', '.join(unexpected)}")
    usage = metadata.get("usage")
    if usage is not None and (
        not isinstance(usage, dict)
        or any(not isinstance(value, (int, float)) for value in usage.values())
    ):
        raise ValueError("Provider usage metadata must contain numeric counters")
    return dict(metadata)


class BuildStageRunner:
    def __init__(self, repository: CourseRAGRepository, artifact_store: FileArtifactStore) -> None:
        self.repository = repository
        self.artifact_store = artifact_store

    def run(
        self, stage: BuildStage, context: StageContext, *, force: bool = False
    ) -> BuildStageRunRecord:
        fingerprint = stage_fingerprint(stage, context)
        config_hash = sha256_json(context.config)
        provider_metadata = _validated_provider_metadata(context.provider_metadata)
        if not force:
            reusable = self.repository.find_reusable_job_stage(
                context.build_job_id, stage.name, fingerprint
            )
            if reusable is not None and reusable.artifact_id is not None:
                artifact = self.repository.get_artifact(reusable.artifact_id)
                if artifact is not None and self.artifact_store.verify(
                    artifact.uri, artifact.sha256
                ):
                    return reusable

        recovered_at = utc_now()
        for stale in self.repository.list_running_stage_attempts(context.build_job_id, stage.name):
            stale.status = "failed"
            stale.error_code = "STALE_STAGE_RECOVERED"
            stale.error_message = "Previous running attempt was recovered after lease takeover"
            stale.completed_at = recovered_at
        self.repository.flush()

        attempt = self.repository.next_stage_attempt(context.build_job_id, stage.name)
        cached = None if force else self.repository.find_cached_stage(fingerprint)
        if cached is not None and cached.artifact_id is not None:
            artifact = self.repository.get_artifact(cached.artifact_id)
            if artifact is not None and self.artifact_store.verify(artifact.uri, artifact.sha256):
                run = BuildStageRunRecord(
                    build_job_id=context.build_job_id,
                    stage_name=stage.name,
                    stage_version=stage.version,
                    fingerprint=fingerprint,
                    attempt_number=attempt,
                    status="cached",
                    cache_hit=True,
                    artifact_id=artifact.id,
                    input_hashes_json=list(context.input_hashes),
                    config_hash=config_hash,
                    provider_metadata_json=provider_metadata,
                    counts_json=cached.counts_json,
                    warnings_json=cached.warnings_json,
                    started_at=utc_now(),
                    completed_at=utc_now(),
                )
                self.repository.add(run)
                self.repository.flush()
                return run

        run = BuildStageRunRecord(
            build_job_id=context.build_job_id,
            stage_name=stage.name,
            stage_version=stage.version,
            fingerprint=fingerprint,
            attempt_number=attempt,
            status="running",
            cache_hit=False,
            input_hashes_json=list(context.input_hashes),
            config_hash=config_hash,
            provider_metadata_json=provider_metadata,
            started_at=utc_now(),
        )
        self.repository.add(run)
        self.repository.flush()
        try:
            output = stage.execute(context)
            stored = self.artifact_store.put(output.content, media_type=output.media_type)
            artifact = self._record_artifact(stored)
            run.artifact_id = artifact.id
            run.counts_json = output.counts
            run.warnings_json = list(output.warnings)
            run.status = "succeeded"
            run.completed_at = utc_now()
            self.repository.flush()
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_code = type(exc).__name__
            run.error_message = "Stage execution failed; inspect protected service logs"
            run.completed_at = utc_now()
            self.repository.flush()
            raise

    def _record_artifact(self, stored: StoredArtifact) -> ArtifactRecord:
        artifact = ArtifactRecord(
            uri=stored.uri,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            media_type=stored.media_type,
            status="available",
            last_verified_at=utc_now(),
        )
        return self.repository.get_or_create_artifact(artifact)
