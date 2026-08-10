from __future__ import annotations

from pydantic import TypeAdapter, ValidationError

from courserag.indexing.manifests import (
    IndexManifest,
    PublishedIndexManifest,
    VersionedIndexManifest,
)
from courserag.jobs.artifacts import ArtifactIntegrityError, FileArtifactStore, StoredArtifact
from courserag.jobs.stages import canonical_json_bytes
from courserag.persistence.base import utc_now
from courserag.persistence.models import ArtifactRecord, IndexVersionRecord
from courserag.persistence.repositories import CourseRAGRepository


class ActiveIndexChangedError(RuntimeError):
    pass


class IndexManifestError(RuntimeError):
    pass


class IndexVersionManager:
    def __init__(self, repository: CourseRAGRepository, artifact_store: FileArtifactStore) -> None:
        self.repository = repository
        self.artifact_store = artifact_store

    def create_staging(
        self,
        *,
        knowledge_base_id: str,
        build_job_id: str,
        dense_manifest_artifact_id: str,
        sparse_manifest_artifact_id: str | None = None,
        sparse_status: str = "not_materialized",
    ) -> IndexVersionRecord:
        if sparse_status not in {"ready", "not_materialized"}:
            raise ValueError("Unsupported sparse index status")
        if sparse_status == "ready" and sparse_manifest_artifact_id is None:
            raise ValueError("Ready sparse index requires a manifest artifact")
        if sparse_status == "not_materialized" and sparse_manifest_artifact_id is not None:
            raise ValueError("Non-materialized sparse index cannot have a manifest artifact")
        knowledge_base = self.repository.lock_knowledge_base(knowledge_base_id)
        if knowledge_base is None:
            raise ValueError("Knowledge base not found")
        build_job = self.repository.get_build_job(build_job_id)
        if build_job is None or build_job.knowledge_base_id != knowledge_base_id:
            raise ValueError("Build job does not belong to the knowledge base")
        document_version_ids = [
            record.id for record in self.repository.list_build_document_versions(build_job_id)
        ]
        if not document_version_ids:
            raise ValueError("Index build requires at least one document version")
        record = IndexVersionRecord(
            knowledge_base_id=knowledge_base_id,
            build_job_id=build_job_id,
            version_number=self.repository.next_index_version(knowledge_base_id),
            status="staging",
            dense_manifest_artifact_id=dense_manifest_artifact_id,
            sparse_manifest_artifact_id=sparse_manifest_artifact_id,
            sparse_status=sparse_status,
        )
        self.repository.add(record)
        self.repository.flush()
        self.repository.add_index_document_versions(record.id, document_version_ids)
        build_job.target_index_version_id = record.id
        return record

    def publish(
        self, index_version_id: str, *, expected_active_index_id: str | None
    ) -> IndexVersionRecord:
        candidate = self.repository.get_index_version(index_version_id)
        if candidate is None:
            raise ValueError("Index version not found")
        if candidate.status not in {"staging", "validating"}:
            raise ValueError("Only a staging index can be published")
        candidate.status = "validating"
        try:
            dense_hash, sparse_hash = self._validate(candidate)
            overall_artifact = self._record_published_manifest(
                candidate, dense_hash=dense_hash, sparse_hash=sparse_hash
            )
            knowledge_base = self.repository.lock_knowledge_base(candidate.knowledge_base_id)
            if knowledge_base is None:
                raise ValueError("Knowledge base not found")
            if knowledge_base.active_index_version_id != expected_active_index_id:
                raise ActiveIndexChangedError("Active index pointer changed during build")
        except Exception as exc:
            candidate.status = "failed"
            self.repository.audit(
                "index.publish_failed",
                "index_version",
                candidate.id,
                details={"error_code": type(exc).__name__},
            )
            self.repository.flush()
            raise
        old = (
            self.repository.get_index_version(knowledge_base.active_index_version_id)
            if knowledge_base.active_index_version_id is not None
            else None
        )
        if old is not None:
            old.status = "retired"
            self.repository.flush()
        candidate.status = "active"
        candidate.overall_manifest_artifact_id = overall_artifact.id
        candidate.manifest_sha256 = overall_artifact.sha256
        candidate.published_at = utc_now()
        knowledge_base.active_index_version_id = candidate.id
        knowledge_base.status = "ready"
        self.repository.audit(
            "index.published",
            "index_version",
            candidate.id,
            details={"replaced_index_version_id": expected_active_index_id},
        )
        self.repository.flush()
        return candidate

    def _validate(self, candidate: IndexVersionRecord) -> tuple[str, str | None]:
        build_job = self.repository.get_build_job(candidate.build_job_id)
        if build_job is None or build_job.knowledge_base_id != candidate.knowledge_base_id:
            raise IndexManifestError("Index build job knowledge base mismatch")
        expected_document_ids = {
            record.id
            for record in self.repository.list_build_document_versions(candidate.build_job_id)
        }
        if not expected_document_ids:
            raise IndexManifestError("Index build has no document versions")
        artifact = (
            self.repository.get_artifact(candidate.dense_manifest_artifact_id)
            if candidate.dense_manifest_artifact_id is not None
            else None
        )
        if artifact is None:
            raise IndexManifestError("Dense manifest artifact is missing")
        content = self.artifact_store.read(artifact.uri, expected_sha256=artifact.sha256)
        try:
            manifest = _parse_manifest(content)
        except ValidationError as exc:
            raise IndexManifestError("Dense manifest schema validation failed") from exc
        if manifest.index_kind != "dense" or manifest.status != "ready":
            raise IndexManifestError("Dense manifest must be materialized")
        if manifest.knowledge_base_id != candidate.knowledge_base_id:
            raise IndexManifestError("Dense manifest knowledge base mismatch")
        if manifest.build_job_id != candidate.build_job_id:
            raise IndexManifestError("Dense manifest build job mismatch")
        if set(manifest.document_version_ids) != expected_document_ids:
            raise IndexManifestError("Dense manifest document version set mismatch")
        self._validate_versioned_identity(candidate, manifest)
        self._validate_shards(manifest)
        sparse_hash: str | None = None
        if candidate.sparse_status == "ready":
            if candidate.sparse_manifest_artifact_id is None:
                raise IndexManifestError("Ready sparse index requires a manifest")
            sparse_artifact = self.repository.get_artifact(candidate.sparse_manifest_artifact_id)
            if sparse_artifact is None:
                raise IndexManifestError("Sparse manifest artifact is missing")
            sparse_content = self.artifact_store.read(
                sparse_artifact.uri, expected_sha256=sparse_artifact.sha256
            )
            try:
                sparse = _parse_manifest(sparse_content)
            except ValidationError as exc:
                raise IndexManifestError("Sparse manifest schema validation failed") from exc
            if sparse.index_kind != "sparse" or sparse.status != "ready":
                raise IndexManifestError("Sparse manifest must be materialized")
            if sparse.knowledge_base_id != candidate.knowledge_base_id:
                raise IndexManifestError("Sparse manifest knowledge base mismatch")
            if sparse.build_job_id != candidate.build_job_id:
                raise IndexManifestError("Sparse manifest build job mismatch")
            if set(sparse.document_version_ids) != expected_document_ids:
                raise IndexManifestError("Sparse manifest document version set mismatch")
            self._validate_versioned_identity(candidate, sparse)
            self._validate_shards(sparse)
            sparse_hash = sparse_artifact.sha256
        elif candidate.sparse_manifest_artifact_id is not None:
            raise IndexManifestError("Non-materialized sparse index cannot have a manifest")
        return artifact.sha256, sparse_hash

    def _validate_versioned_identity(
        self, candidate: IndexVersionRecord, manifest: IndexManifest | VersionedIndexManifest
    ) -> None:
        if not isinstance(manifest, VersionedIndexManifest):
            return
        if manifest.index_version_id != candidate.id:
            raise IndexManifestError("Manifest index version mismatch")
        if set(manifest.chunk_ids) != set(self.repository.list_index_chunk_ids(candidate.id)):
            raise IndexManifestError("Manifest and PostgreSQL Chunk sets differ")

    def _validate_shards(self, manifest: IndexManifest | VersionedIndexManifest) -> None:
        for entry in manifest.entries:
            try:
                self.artifact_store.read(entry.shard_uri, expected_sha256=entry.sha256)
            except (ArtifactIntegrityError, FileNotFoundError, ValueError) as exc:
                raise IndexManifestError("Index shard is missing or invalid") from exc

    def _record_published_manifest(
        self,
        candidate: IndexVersionRecord,
        *,
        dense_hash: str,
        sparse_hash: str | None,
    ) -> ArtifactRecord:
        content = canonical_json_bytes(
            PublishedIndexManifest(
                knowledge_base_id=candidate.knowledge_base_id,
                build_job_id=candidate.build_job_id,
                dense_manifest_sha256=dense_hash,
                sparse_manifest_sha256=sparse_hash,
                sparse_status=candidate.sparse_status,
            ).model_dump(mode="json")
        )
        stored: StoredArtifact = self.artifact_store.put(content, media_type="application/json")
        return self.repository.get_or_create_artifact(
            ArtifactRecord(
                uri=stored.uri,
                sha256=stored.sha256,
                size_bytes=stored.size_bytes,
                media_type=stored.media_type,
                status="available",
                last_verified_at=utc_now(),
            )
        )


def _parse_manifest(content: bytes) -> IndexManifest | VersionedIndexManifest:
    return TypeAdapter(IndexManifest | VersionedIndexManifest).validate_json(content)
