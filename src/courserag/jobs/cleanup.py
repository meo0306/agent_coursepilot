from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from courserag.jobs.artifacts import FileArtifactStore
from courserag.persistence.base import utc_now
from courserag.persistence.repositories import CourseRAGRepository


@dataclass(frozen=True)
class CleanupPlan:
    artifact_ids: tuple[str, ...]
    physical_orphan_uris: tuple[str, ...]
    staging_index_version_ids: tuple[str, ...]
    dry_run: bool


class CleanupService:
    """Retention cleanup is dry-run unless an operator explicitly opts in."""

    def __init__(self, repository: CourseRAGRepository, artifact_store: FileArtifactStore) -> None:
        self.repository = repository
        self.artifact_store = artifact_store

    def run(
        self,
        *,
        artifact_retention_hours: int,
        staging_retention_hours: int,
        dry_run: bool = True,
        actor_id: str = "system",
    ) -> CleanupPlan:
        now = utc_now()
        artifact_cutoff = now - timedelta(hours=artifact_retention_hours)
        artifacts = self.repository.list_cleanup_artifacts(artifact_cutoff)
        stale_indexes = self.repository.list_stale_staging_indexes(
            now - timedelta(hours=staging_retention_hours)
        )
        physical_orphans = self.artifact_store.list_physical_orphans(
            self.repository.list_artifact_uris(), older_than=artifact_cutoff
        )
        if not dry_run:
            for index in stale_indexes:
                index.status = "failed"
                index.dense_manifest_artifact_id = None
                index.sparse_manifest_artifact_id = None
                index.overall_manifest_artifact_id = None
            self.repository.flush()
            released_artifacts = self.repository.list_cleanup_artifacts(artifact_cutoff)
            artifacts = list(
                {record.id: record for record in [*artifacts, *released_artifacts]}.values()
            )
        plan = CleanupPlan(
            artifact_ids=tuple(sorted(record.id for record in artifacts)),
            physical_orphan_uris=physical_orphans,
            staging_index_version_ids=tuple(sorted(record.id for record in stale_indexes)),
            dry_run=dry_run,
        )
        self.repository.audit(
            "cleanup.planned" if dry_run else "cleanup.executed",
            "cleanup",
            now.isoformat(),
            actor_id=actor_id,
            details={
                "artifact_ids": list(plan.artifact_ids),
                "physical_orphan_uris": list(plan.physical_orphan_uris),
                "staging_index_version_ids": list(plan.staging_index_version_ids),
                "dry_run": dry_run,
            },
        )
        if dry_run:
            self.repository.flush()
            return plan
        for artifact in artifacts:
            self.artifact_store.delete(artifact.uri)
            artifact.status = "deleted"
            artifact.deleted_at = now
        for uri in physical_orphans:
            self.artifact_store.delete(uri)
        self.repository.flush()
        return plan
