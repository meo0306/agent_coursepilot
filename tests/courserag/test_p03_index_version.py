import hashlib
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from courserag.indexing.manifests import IndexManifest, ManifestEntry
from courserag.indexing.version_manager import (
    ActiveIndexChangedError,
    IndexManifestError,
    IndexVersionManager,
)
from courserag.jobs.artifacts import FileArtifactStore
from courserag.persistence.models import (
    ArtifactRecord,
    BuildJobDocumentVersionRecord,
    BuildJobRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


def _artifact(session: Session, store: FileArtifactStore, content: bytes) -> ArtifactRecord:
    stored = store.put(content, media_type="application/json")
    record = ArtifactRecord(
        uri=stored.uri,
        sha256=stored.sha256,
        size_bytes=stored.size_bytes,
        media_type=stored.media_type,
    )
    session.add(record)
    session.flush()
    return record


def _manifest(
    store: FileArtifactStore,
    knowledge_base_id: str,
    build_job_id: str,
    document_version_ids: list[str],
    *,
    index_kind: str = "dense",
    materialize_shard: bool = True,
) -> bytes:
    shard_hash = hashlib.sha256(b"dense-index").hexdigest()
    if materialize_shard:
        store.put(b"dense-index", media_type="application/octet-stream")
    return (
        IndexManifest(
            index_kind=index_kind,
            status="ready",
            knowledge_base_id=knowledge_base_id,
            build_job_id=build_job_id,
            document_version_ids=document_version_ids,
            config_hash="a" * 64,
            entries=[
                ManifestEntry(
                    shard_uri=f"artifact://sha256/{shard_hash}",
                    sha256=shard_hash,
                    item_count=1,
                )
            ],
        )
        .model_dump_json()
        .encode()
    )


def _job(
    session: Session, kb: KnowledgeBaseRecord, request_hash: str
) -> tuple[BuildJobRecord, DocumentVersionRecord]:
    source = SourceDocumentRecord(
        knowledge_base_id=kb.id,
        legacy_document_id=f"legacy-{request_hash[0]}",
        filename=f"{request_hash[0]}.pdf",
        document_type="pdf",
    )
    session.add(source)
    session.flush()
    document = DocumentVersionRecord(
        source_document_id=source.id,
        version_number=1,
        content_sha256=request_hash,
        object_uri=f"legacy-document://{source.id}/{request_hash}",
        mime_type="application/pdf",
        size_bytes=1,
    )
    session.add(document)
    session.flush()
    job = BuildJobRecord(
        knowledge_base_id=kb.id,
        request_hash=request_hash,
        status="succeeded",
    )
    session.add(job)
    session.flush()
    session.add(
        BuildJobDocumentVersionRecord(
            build_job_id=job.id,
            document_version_id=document.id,
        )
    )
    session.flush()
    return job, document


def test_publish_is_atomic_and_failures_preserve_active_pointer(
    p03_session: Session, tmp_path: Path
) -> None:
    kb = KnowledgeBaseRecord(course_id="course-index", name="Course")
    p03_session.add(kb)
    p03_session.flush()
    repository = CourseRAGRepository(p03_session)
    store = FileArtifactStore(tmp_path / "artifacts")
    manager = IndexVersionManager(repository, store)

    first_job, first_document = _job(p03_session, kb, "1" * 64)
    first_artifact = _artifact(
        p03_session,
        store,
        _manifest(store, kb.id, first_job.id, [first_document.id]),
    )
    first = manager.create_staging(
        knowledge_base_id=kb.id,
        build_job_id=first_job.id,
        dense_manifest_artifact_id=first_artifact.id,
    )
    manager.publish(first.id, expected_active_index_id=None)
    assert kb.active_index_version_id == first.id
    assert first.status == "active"

    bad_job, _ = _job(p03_session, kb, "2" * 64)
    bad_artifact = _artifact(p03_session, store, b'{"invalid":true}')
    bad = manager.create_staging(
        knowledge_base_id=kb.id,
        build_job_id=bad_job.id,
        dense_manifest_artifact_id=bad_artifact.id,
    )
    with pytest.raises(IndexManifestError):
        manager.publish(bad.id, expected_active_index_id=first.id)
    assert kb.active_index_version_id == first.id
    assert first.status == "active"
    assert bad.status == "failed"

    second_job, second_document = _job(p03_session, kb, "3" * 64)
    second_artifact = _artifact(
        p03_session,
        store,
        _manifest(store, kb.id, second_job.id, [second_document.id]),
    )
    second = manager.create_staging(
        knowledge_base_id=kb.id,
        build_job_id=second_job.id,
        dense_manifest_artifact_id=second_artifact.id,
    )
    with pytest.raises(ActiveIndexChangedError):
        manager.publish(second.id, expected_active_index_id=None)
    assert kb.active_index_version_id == first.id
    assert first.status == "active"


def test_publish_rejects_missing_shard_and_wrong_sparse_scope(
    p03_session: Session, tmp_path: Path
) -> None:
    kb = KnowledgeBaseRecord(course_id="course-validation", name="Course")
    p03_session.add(kb)
    p03_session.flush()
    repository = CourseRAGRepository(p03_session)
    store = FileArtifactStore(tmp_path / "artifacts")
    manager = IndexVersionManager(repository, store)

    missing_job, missing_document = _job(p03_session, kb, "4" * 64)
    missing_manifest = _artifact(
        p03_session,
        store,
        _manifest(
            store,
            kb.id,
            missing_job.id,
            [missing_document.id],
            materialize_shard=False,
        ),
    )
    missing = manager.create_staging(
        knowledge_base_id=kb.id,
        build_job_id=missing_job.id,
        dense_manifest_artifact_id=missing_manifest.id,
    )
    with pytest.raises(IndexManifestError, match="shard"):
        manager.publish(missing.id, expected_active_index_id=None)
    assert kb.active_index_version_id is None

    valid_job, valid_document = _job(p03_session, kb, "5" * 64)
    dense = _artifact(
        p03_session,
        store,
        _manifest(store, kb.id, valid_job.id, [valid_document.id]),
    )
    sparse = _artifact(
        p03_session,
        store,
        _manifest(
            store,
            "wrong-kb",
            valid_job.id,
            [valid_document.id],
            index_kind="sparse",
        ),
    )
    candidate = manager.create_staging(
        knowledge_base_id=kb.id,
        build_job_id=valid_job.id,
        dense_manifest_artifact_id=dense.id,
        sparse_manifest_artifact_id=sparse.id,
        sparse_status="ready",
    )
    with pytest.raises(IndexManifestError, match="Sparse manifest knowledge base mismatch"):
        manager.publish(candidate.id, expected_active_index_id=None)
    assert kb.active_index_version_id is None
