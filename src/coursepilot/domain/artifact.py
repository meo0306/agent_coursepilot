from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator

from coursepilot.domain.common import DomainModel, UTCDateTime, canonical_sha256


class StorageKind(StrEnum):
    STATE = "state"
    POSTGRES = "postgres"
    OBJECT = "object"


class ArtifactRef(DomainModel):
    artifact_id: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    artifact_version: int = Field(ge=1)
    storage_kind: StorageKind
    storage_uri: str | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str = Field(min_length=1)

    @field_validator("storage_uri")
    @classmethod
    def reject_host_paths(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.replace("\\", "/")
        if normalized.startswith("/") or (len(normalized) > 1 and normalized[1] == ":"):
            raise ValueError("Artifact storage_uri must not expose an absolute host path")
        return value


class ArtifactVersion(DomainModel):
    artifact_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    content: dict[str, object] | list[object]
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    schema_version: str = Field(min_length=1)
    created_at: UTCDateTime
    created_by: str = Field(min_length=1)

    @field_validator("content_hash")
    @classmethod
    def validate_content_hash(cls, value: str, info: object) -> str:
        data = getattr(info, "data", {})
        content = data.get("content")
        if content is not None and canonical_sha256(content) != value:
            raise ValueError("content_hash does not match canonical Artifact content")
        return value
