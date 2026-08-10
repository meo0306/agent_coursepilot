import pytest

from courserag.indexing.manifests import ManifestEntry, VersionedIndexManifest
from courserag.indexing.version_manager import IndexManifestError, IndexVersionManager
from courserag.persistence.models import IndexVersionRecord


class FakeRepository:
    def __init__(self, chunk_ids: list[str]) -> None:
        self.chunk_ids = chunk_ids

    def list_index_chunk_ids(self, index_version_id: str) -> list[str]:
        assert index_version_id == "iv"
        return self.chunk_ids


def manifest(chunk_ids: list[str]) -> VersionedIndexManifest:
    return VersionedIndexManifest(
        index_kind="dense",
        knowledge_base_id="kb",
        build_job_id="job",
        index_version_id="iv",
        document_version_ids=["dv"],
        chunk_ids=chunk_ids,
        corpus_mapping_sha256="a" * 64,
        config_hash="b" * 64,
        component_identity_sha256="c" * 64,
        entries=[ManifestEntry(shard_uri="artifact://shard", sha256="d" * 64, item_count=1)],
    )


def test_v2_manifest_requires_exact_postgres_chunk_set() -> None:
    manager = IndexVersionManager(FakeRepository(["chunk-1"]), object())
    candidate = IndexVersionRecord(
        id="iv",
        knowledge_base_id="kb",
        build_job_id="job",
        version_number=1,
        status="staging",
    )
    manager._validate_versioned_identity(candidate, manifest(["chunk-1"]))
    with pytest.raises(IndexManifestError, match="Chunk sets differ"):
        manager._validate_versioned_identity(candidate, manifest(["other"]))
