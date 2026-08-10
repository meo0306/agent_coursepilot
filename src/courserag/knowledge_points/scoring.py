"""Deterministic Knowledge Point publication score."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from courserag.domain.knowledge_point import (
    KnowledgePointDraft,
    PublishScore,
    PublishScoreComponents,
    StrictKnowledgePointModel,
    canonical_json_bytes,
    sha256_bytes,
)


class ScoringWeights(StrictKnowledgePointModel):
    evidence: float = Field(default=0.35, ge=0, le=1)
    naming: float = Field(default=0.20, ge=0, le=1)
    cross_window: float = Field(default=0.20, ge=0, le=1)
    ambiguity_safety: float = Field(default=0.15, ge=0, le=1)
    duplicate_safety: float = Field(default=0.10, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> ScoringWeights:
        if abs(sum(self.model_dump().values()) - 1.0) > 1e-9:
            raise ValueError("Knowledge Point scoring weights must sum to one")
        return self


class ScoringProfile(StrictKnowledgePointModel):
    schema_version: Literal["courserag.kp-scoring-profile.v1"] = "courserag.kp-scoring-profile.v1"
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    threshold: float = Field(default=0.75, ge=0, le=1)
    weights: ScoringWeights = Field(default_factory=ScoringWeights)

    @property
    def profile_sha256(self) -> str:
        return sha256_bytes(canonical_json_bytes(self))


class KnowledgePointScorer:
    def __init__(self, profile: ScoringProfile) -> None:
        self.profile = profile

    def score(self, draft: KnowledgePointDraft) -> PublishScore:
        components = PublishScoreComponents(
            evidence=self._evidence_score(draft),
            naming=self._naming_score(draft),
            cross_window=min(1.0, 0.5 + 0.25 * (len(draft.window_ids) - 1)),
            ambiguity_safety=max(0.0, 1.0 - 0.25 * len(draft.ambiguity_flags)),
            duplicate_safety=max(0.0, 1.0 - 0.10 * draft.duplicate_count),
        )
        weights = self.profile.weights
        total = round(
            components.evidence * weights.evidence
            + components.naming * weights.naming
            + components.cross_window * weights.cross_window
            + components.ambiguity_safety * weights.ambiguity_safety
            + components.duplicate_safety * weights.duplicate_safety,
            6,
        )
        checks_passed = bool(
            draft.evidence_refs
            and any(item.is_primary for item in draft.evidence_refs)
            and not draft.ambiguity_flags
        )
        status: Literal["unreviewed", "needs_review"] = (
            "unreviewed" if checks_passed and total >= self.profile.threshold else "needs_review"
        )
        return PublishScore(
            total=total,
            components=components,
            profile_sha256=self.profile.profile_sha256,
            threshold=self.profile.threshold,
            deterministic_checks_passed=checks_passed,
            status=status,
        )

    @staticmethod
    def _evidence_score(draft: KnowledgePointDraft) -> float:
        strengths = [item.strength for item in draft.evidence_refs]
        base = sum(strengths) / len(strengths)
        primary_bonus = 0.10 if any(item.is_primary for item in draft.evidence_refs) else 0.0
        multiple_bonus = 0.10 if len(draft.evidence_refs) > 1 else 0.0
        return min(1.0, base * 0.8 + primary_bonus + multiple_bonus)

    @staticmethod
    def _naming_score(draft: KnowledgePointDraft) -> float:
        length = len(draft.canonical_name.strip())
        if 2 <= length <= 80:
            base = 1.0
        elif length <= 160:
            base = 0.75
        else:
            base = 0.5
        return min(1.0, base + (0.05 if draft.aliases else 0.0))
