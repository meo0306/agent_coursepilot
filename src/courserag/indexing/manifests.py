from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shard_uri: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    item_count: int = Field(ge=0)


class IndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    index_kind: Literal["dense", "sparse"]
    status: Literal["ready", "not_materialized"]
    knowledge_base_id: str
    build_job_id: str
    document_version_ids: list[str]
    entries: list[ManifestEntry] = Field(default_factory=list)
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_materialization(self) -> IndexManifest:
        if len(set(self.document_version_ids)) != len(self.document_version_ids):
            raise ValueError("Document version IDs must be unique")
        shard_uris = [entry.shard_uri for entry in self.entries]
        if len(set(shard_uris)) != len(shard_uris):
            raise ValueError("Shard URIs must be unique")
        if self.status == "ready" and not self.entries:
            raise ValueError("A ready index manifest must contain at least one entry")
        if self.status == "not_materialized" and self.entries:
            raise ValueError("A non-materialized index manifest cannot contain entries")
        return self


class PublishedIndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    knowledge_base_id: str
    build_job_id: str
    dense_manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sparse_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    sparse_status: Literal["ready", "not_materialized"]


class VersionedIndexManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["2.0"] = "2.0"
    index_kind: Literal["dense", "sparse"]
    status: Literal["ready"] = "ready"
    knowledge_base_id: str
    build_job_id: str
    index_version_id: str
    document_version_ids: list[str]
    chunk_ids: list[str]
    corpus_mapping_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    component_identity_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    entries: list[ManifestEntry]

    @model_validator(mode="after")
    def validate_identity_sets(self) -> VersionedIndexManifest:
        if not self.entries or not self.chunk_ids:
            raise ValueError("A v2 index requires Shards and Chunk IDs")
        if len(set(self.document_version_ids)) != len(self.document_version_ids):
            raise ValueError("Document version IDs must be unique")
        if len(set(self.chunk_ids)) != len(self.chunk_ids):
            raise ValueError("Chunk IDs must be unique")
        return self
