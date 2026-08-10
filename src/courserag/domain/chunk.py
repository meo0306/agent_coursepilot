"""Versioned parent-child Chunk domain objects derived from stable Evidence."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from courserag.domain.document import (
    Sha256,
    StrictIRModel,
    canonical_json_bytes,
    sha256_bytes,
    sha256_text,
)


class ChunkProfile(StrictIRModel):
    schema_version: Literal["courserag.chunk-profile.v1"] = "courserag.chunk-profile.v1"
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    tokenizer_id: str = Field(min_length=1, max_length=160)
    tokenizer_sha256: Sha256
    parent_min_tokens: int = Field(ge=1)
    parent_target_tokens: int = Field(ge=1)
    parent_max_tokens: int = Field(ge=1)
    child_min_tokens: int = Field(ge=1)
    child_target_tokens: int = Field(ge=1)
    child_max_tokens: int = Field(ge=1)
    child_overlap_tokens: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_ranges(self) -> ChunkProfile:
        if not self.parent_min_tokens <= self.parent_target_tokens <= self.parent_max_tokens:
            raise ValueError("Parent token limits must be ordered")
        if not self.child_min_tokens <= self.child_target_tokens <= self.child_max_tokens:
            raise ValueError("Child token limits must be ordered")
        if self.child_overlap_tokens >= self.child_max_tokens:
            raise ValueError("Child overlap must be below the Child maximum")
        return self

    @property
    def profile_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class ChunkEvidenceLink(StrictIRModel):
    evidence_id: str = Field(pattern=r"^ev1_[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    evidence_char_start: int = Field(ge=0)
    evidence_char_end: int = Field(ge=0)
    coverage_sha256: Sha256

    @model_validator(mode="after")
    def validate_range(self) -> ChunkEvidenceLink:
        if self.evidence_char_end <= self.evidence_char_start:
            raise ValueError("Chunk Evidence coverage must be non-empty")
        return self


class ChunkRecord(StrictIRModel):
    schema_version: Literal["courserag.chunk.v1"] = "courserag.chunk.v1"
    chunk_id: str = Field(pattern=r"^ch1_[0-9a-f]{64}$")
    chunk_set_id: str = Field(pattern=r"^cs1_[0-9a-f]{64}$")
    document_version_id: str = Field(min_length=1, max_length=160)
    section_id: str | None = Field(default=None, max_length=160)
    kind: Literal["parent", "child"]
    parent_chunk_id: str | None = Field(default=None, pattern=r"^ch1_[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    content_sha256: Sha256
    token_count: int = Field(ge=1)
    profile_sha256: Sha256
    evidence_links: tuple[ChunkEvidenceLink, ...] = Field(min_length=1)
    warning_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_chunk(self) -> ChunkRecord:
        if self.content_sha256 != sha256_text(self.text):
            raise ValueError("Chunk content hash does not match text")
        if self.kind == "parent" and self.parent_chunk_id is not None:
            raise ValueError("Parent Chunk cannot reference another Parent")
        if self.kind == "child" and self.parent_chunk_id is None:
            raise ValueError("Child Chunk requires exactly one Parent")
        if self.chunk_id != stable_chunk_id(
            self.chunk_set_id,
            self.kind,
            self.parent_chunk_id,
            self.evidence_links,
            self.content_sha256,
        ):
            raise ValueError("Chunk ID does not match its immutable profile/source identity")
        return self


class ChunkArtifact(StrictIRModel):
    schema_version: Literal["courserag.chunk-artifact.v1"] = "courserag.chunk-artifact.v1"
    chunk_set_id: str = Field(pattern=r"^cs1_[0-9a-f]{64}$")
    document_id: str
    document_version_id: str
    evidence_artifact_sha256: Sha256
    profile: ChunkProfile
    chunks: tuple[ChunkRecord, ...]
    warning_codes: tuple[str, ...] = ()

    @property
    def content_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


def stable_chunk_set_id(
    document_version_id: str, evidence_artifact_sha256: str, profile_sha256: str
) -> str:
    return "cs1_" + sha256_bytes(
        canonical_json_bytes([document_version_id, evidence_artifact_sha256, profile_sha256])
    )


def stable_chunk_id(
    chunk_set_id: str,
    kind: str,
    parent_chunk_id: str | None,
    links: tuple[ChunkEvidenceLink, ...],
    content_sha256: str,
) -> str:
    return "ch1_" + sha256_bytes(
        canonical_json_bytes(
            {
                "chunk_set_id": chunk_set_id,
                "kind": kind,
                "parent_chunk_id": parent_chunk_id,
                "links": [link.model_dump(mode="json") for link in links],
                "content_sha256": content_sha256,
            }
        )
    )
