"""Course-level Knowledge Point assets derived from stable Evidence."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = str
KnowledgePointRole = Literal[
    "definition",
    "principle",
    "procedure",
    "example",
    "comparison",
    "formula",
    "application",
    "limitation",
    "exercise",
    "summary",
]
KnowledgePointStatus = Literal[
    "unreviewed",
    "needs_review",
    "approved",
    "rejected",
    "deprecated",
]


class StrictKnowledgePointModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_json_bytes(value: object) -> bytes:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def normalized_knowledge_point_name(value: str) -> str:
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    return normalized.casefold()


class WindowProfile(StrictKnowledgePointModel):
    schema_version: Literal["courserag.kp-window-profile.v1"] = "courserag.kp-window-profile.v1"
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    tokenizer_id: str = Field(min_length=1, max_length=160)
    tokenizer_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    min_tokens: int = Field(default=1500, ge=1)
    max_tokens: int = Field(default=3000, ge=1)
    overlap_evidence_count: Literal[1] = 1

    @model_validator(mode="after")
    def validate_limits(self) -> WindowProfile:
        if self.min_tokens > self.max_tokens:
            raise ValueError("Knowledge Point Window minimum exceeds maximum")
        return self

    @property
    def profile_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class WindowEvidence(StrictKnowledgePointModel):
    evidence_id: str = Field(pattern=r"^ev1_[0-9a-f]{64}$")
    text: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ordinal: int = Field(ge=0)
    block_id: str | None = Field(default=None, max_length=160)
    source_mode: Literal["native", "ocr", "hybrid"] = "native"
    confidence: float | None = Field(default=None, ge=0, le=1)
    warning_codes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_content_hash(self) -> WindowEvidence:
        if sha256_text(self.text) != self.content_sha256:
            raise ValueError("Window Evidence content Hash differs from text")
        return self


class SectionWindow(StrictKnowledgePointModel):
    schema_version: Literal["courserag.kp-window.v1"] = "courserag.kp-window.v1"
    window_id: str = Field(pattern=r"^kpw1_[0-9a-f]{64}$")
    knowledge_base_id: str = Field(min_length=1, max_length=160)
    course_id: str = Field(min_length=1, max_length=160)
    section_id: str = Field(min_length=1, max_length=160)
    section_title: str | None = Field(default=None, max_length=500)
    ordinal: int = Field(ge=0)
    evidence: tuple[WindowEvidence, ...] = Field(min_length=1)
    token_count: int = Field(ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    warning_codes: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return "\n\n".join(item.text for item in self.evidence)

    @model_validator(mode="after")
    def validate_identity(self) -> SectionWindow:
        if self.content_sha256 != sha256_text(self.text):
            raise ValueError("Section Window content Hash differs from its Evidence text")
        expected = stable_window_id(
            self.knowledge_base_id,
            self.course_id,
            self.section_id,
            self.ordinal,
            tuple(item.evidence_id for item in self.evidence),
            self.content_sha256,
            self.profile_sha256,
        )
        if self.window_id != expected:
            raise ValueError("Section Window ID differs from its immutable identity")
        return self


class KnowledgePointEvidenceRef(StrictKnowledgePointModel):
    evidence_id: str = Field(pattern=r"^ev1_[0-9a-f]{64}$")
    role: KnowledgePointRole
    is_primary: bool = False
    strength: float = Field(default=1.0, ge=0, le=1)


class KnowledgePointCandidate(StrictKnowledgePointModel):
    canonical_name: str = Field(min_length=1, max_length=240)
    aliases: tuple[str, ...] = ()
    summary: str = Field(min_length=1, max_length=4000)
    parent_name: str | None = Field(default=None, max_length=240)
    evidence_refs: tuple[KnowledgePointEvidenceRef, ...] = Field(min_length=1)
    model_confidence: float | None = Field(default=None, ge=0, le=1)
    ambiguity_flags: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_candidate(self) -> KnowledgePointCandidate:
        evidence_ids = [item.evidence_id for item in self.evidence_refs]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Knowledge Point Candidate Evidence references must be unique")
        if not any(item.is_primary for item in self.evidence_refs):
            raise ValueError("Knowledge Point Candidate requires primary Evidence")
        normalized_aliases = [normalized_knowledge_point_name(item) for item in self.aliases]
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ValueError("Knowledge Point Candidate aliases must be unique")
        if normalized_knowledge_point_name(self.canonical_name) in normalized_aliases:
            raise ValueError("Canonical Knowledge Point name cannot repeat as an Alias")
        return self


class ProviderUsage(StrictKnowledgePointModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)


class WindowExtractionResult(StrictKnowledgePointModel):
    schema_version: Literal["courserag.kp-window-result.v1"] = "courserag.kp-window-result.v1"
    window_id: str = Field(pattern=r"^kpw1_[0-9a-f]{64}$")
    window_content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: str = Field(min_length=1, max_length=160)
    model: str = Field(min_length=1, max_length=240)
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidates: tuple[KnowledgePointCandidate, ...] = ()
    usage: ProviderUsage = Field(default_factory=ProviderUsage)
    duration_ms: int = Field(default=0, ge=0)
    warning_codes: tuple[str, ...] = ()

    @property
    def result_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class KnowledgePointDraft(StrictKnowledgePointModel):
    knowledge_base_id: str = Field(min_length=1, max_length=160)
    course_id: str = Field(min_length=1, max_length=160)
    stable_key: str = Field(min_length=1, max_length=512)
    canonical_name: str = Field(min_length=1, max_length=240)
    normalized_name: str = Field(min_length=1, max_length=240)
    aliases: tuple[str, ...] = ()
    summary: str = Field(min_length=1, max_length=4000)
    parent_name: str | None = Field(default=None, max_length=240)
    section_ids: tuple[str, ...] = Field(min_length=1)
    window_ids: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[KnowledgePointEvidenceRef, ...] = Field(min_length=1)
    ambiguity_flags: tuple[str, ...] = ()
    duplicate_count: int = Field(default=0, ge=0)


class PublishScoreComponents(StrictKnowledgePointModel):
    evidence: float = Field(ge=0, le=1)
    naming: float = Field(ge=0, le=1)
    cross_window: float = Field(ge=0, le=1)
    ambiguity_safety: float = Field(ge=0, le=1)
    duplicate_safety: float = Field(ge=0, le=1)


class PublishScore(StrictKnowledgePointModel):
    schema_version: Literal["courserag.kp-publish-score.v1"] = "courserag.kp-publish-score.v1"
    total: float = Field(ge=0, le=1)
    components: PublishScoreComponents
    profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    threshold: float = Field(ge=0, le=1)
    deterministic_checks_passed: bool
    status: Literal["unreviewed", "needs_review"]


def stable_window_id(
    knowledge_base_id: str,
    course_id: str,
    section_id: str,
    ordinal: int,
    evidence_ids: tuple[str, ...],
    content_sha256: str,
    profile_sha256: str,
) -> str:
    return "kpw1_" + sha256_bytes(
        canonical_json_bytes(
            {
                "knowledge_base_id": knowledge_base_id,
                "course_id": course_id,
                "section_id": section_id,
                "ordinal": ordinal,
                "evidence_ids": evidence_ids,
                "content_sha256": content_sha256,
                "profile_sha256": profile_sha256,
            }
        )
    )


def stable_knowledge_point_key(
    course_id: str, normalized_name: str, primary_evidence_ids: tuple[str, ...]
) -> str:
    return "kp1_" + sha256_bytes(
        canonical_json_bytes(
            {
                "course_id": course_id,
                "normalized_name": normalized_name,
                "primary_evidence_ids": sorted(primary_evidence_ids),
            }
        )
    )
