import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.cleanup import CleanupService
from courserag.persistence.base import utc_now
from courserag.persistence.models import (
    ArtifactRecord,
    BuildJobRecord,
    IndexVersionRecord,
    KnowledgeBaseRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


def test_cleanup_defaults_to_dry_run_and_only_deletes_after_opt_in(
    p03_session: Session, tmp_path: Path
) -> None:
    store = FileArtifactStore(tmp_path / "artifacts")
    stored = store.put(b"orphan", media_type="application/octet-stream")
    artifact = ArtifactRecord(
        uri=stored.uri,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        media_type=stored.media_type,
        created_at=utc_now() - timedelta(hours=200),
    )
    p03_session.add(artifact)
    p03_session.flush()
    service = CleanupService(CourseRAGRepository(p03_session), store)

    dry_run = service.run(artifact_retention_hours=168, staging_retention_hours=72)
    assert dry_run.dry_run is True
    assert dry_run.artifact_ids == (artifact.id,)
    assert artifact.status == "available"
    assert store.verify(artifact.uri, artifact.sha256)

    executed = service.run(
        artifact_retention_hours=168,
        staging_retention_hours=72,
        dry_run=False,
        actor_id="test-operator",
    )
    assert executed.dry_run is False
    assert artifact.status == "deleted"
    assert not store.verify(artifact.uri, artifact.sha256)


def test_cleanup_discovers_physical_artifact_without_database_record(
    p03_session: Session, tmp_path: Path
) -> None:
    store = FileArtifactStore(tmp_path / "artifacts")
    stored = store.put(b"rolled-back-stage-output", media_type="application/octet-stream")
    path = tmp_path / "artifacts" / stored.sha256[:2] / stored.sha256[2:4] / stored.sha256
    old_timestamp = (utc_now() - timedelta(hours=200)).timestamp()
    os.utime(path, (old_timestamp, old_timestamp))
    service = CleanupService(CourseRAGRepository(p03_session), store)

    dry_run = service.run(artifact_retention_hours=168, staging_retention_hours=72)
    assert dry_run.physical_orphan_uris == (stored.uri,)
    assert store.verify(stored.uri, stored.sha256)

    executed = service.run(
        artifact_retention_hours=168,
        staging_retention_hours=72,
        dry_run=False,
    )
    assert executed.physical_orphan_uris == (stored.uri,)
    assert not store.verify(stored.uri, stored.sha256)


def test_cleanup_releases_stale_staging_manifest_artifacts(
    p03_session: Session, tmp_path: Path
) -> None:
    store = FileArtifactStore(tmp_path / "artifacts")
    stored = store.put(b"stale-manifest", media_type="application/json")
    artifact = ArtifactRecord(
        uri=stored.uri,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        media_type=stored.media_type,
        created_at=utc_now() - timedelta(hours=200),
    )
    knowledge_base = KnowledgeBaseRecord(course_id="cleanup-course", name="Course")
    p03_session.add_all([artifact, knowledge_base])
    p03_session.flush()
    job = BuildJobRecord(
        knowledge_base_id=knowledge_base.id,
        request_hash="a" * 64,
    )
    p03_session.add(job)
    p03_session.flush()
    index = IndexVersionRecord(
        knowledge_base_id=knowledge_base.id,
        build_job_id=job.id,
        version_number=1,
        status="staging",
        dense_manifest_artifact_id=artifact.id,
        created_at=utc_now() - timedelta(hours=100),
    )
    p03_session.add(index)
    p03_session.flush()
    service = CleanupService(CourseRAGRepository(p03_session), store)

    dry_run = service.run(artifact_retention_hours=168, staging_retention_hours=72)
    assert dry_run.staging_index_version_ids == (index.id,)
    assert artifact.id not in dry_run.artifact_ids

    executed = service.run(
        artifact_retention_hours=168,
        staging_retention_hours=72,
        dry_run=False,
    )
    assert artifact.id in executed.artifact_ids
    assert index.status == "failed"
    assert index.dense_manifest_artifact_id is None
    assert artifact.status == "deleted"
    assert not store.verify(stored.uri, stored.sha256)
