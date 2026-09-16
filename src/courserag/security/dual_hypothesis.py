"""Calibrated dual-hypothesis detection for untrusted document instructions.

The detector compares an operative-attack hypothesis with a benign-scope
hypothesis.  Semantic and structured observations are deliberately soft
features: no vocabulary hit and no model score is an authorization decision.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from courserag.domain.document import ParsedDocumentIR
from courserag.retrieval.ports import EmbeddingPort
from courserag.security.detector import PromptInjectionDetector, SecurityTextWindow
from courserag.security.prompt_injection import PromptInjectionFinding
from courserag.security.structured_axes import (
    InstructionScope,
    StructuredCapabilityAxes,
    classify_instruction_scope,
)


class SecuritySemanticEncoder(Protocol):
    """A model-independent normalized text encoder used by the security layer."""

    @property
    def identity(self) -> str: ...

    def encode(self, texts: Sequence[str]) -> list[list[float]]: ...


class EmbeddingPortSecurityEncoder:
    """Adapt the existing local embedding Port without importing index internals."""

    def __init__(self, embedder: EmbeddingPort) -> None:
        identity = getattr(embedder, "identity", None)
        if not isinstance(identity, str) or not identity:
            raise ValueError("security semantic encoder requires a stable embedding identity")
        self.embedder = embedder
        self._identity = f"courserag/security-encoder:{identity}"

    @property
    def identity(self) -> str:
        return self._identity

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self.embedder.embed_documents(texts)
        if len(vectors) != len(texts):
            raise ValueError("security semantic encoder result count differs from input")
        return vectors


class SemanticPrototype(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    prototype_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]+$", max_length=120)
    language: str = Field(pattern=r"^(en|zh)$")
    family: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=8, max_length=1000)


class DualHypothesisSecurityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "courserag.dual-hypothesis-security-profile.v1"
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    enabled: bool = False
    semantic_encoder_identity: str = Field(min_length=1, max_length=240)
    hikma_detector_id: str = Field(min_length=1, max_length=240)
    attack_prototypes: tuple[SemanticPrototype, ...] = Field(min_length=4)
    safe_scope_prototypes: tuple[SemanticPrototype, ...] = Field(min_length=4)
    hikma_weight: float = Field(ge=0, le=1)
    attack_semantic_weight: float = Field(ge=0, le=1)
    structured_weight: float = Field(ge=0, le=1)
    safe_semantic_weight: float = Field(ge=0, le=1)
    scope_weight: float = Field(ge=0, le=1)
    attack_threshold: float = Field(ge=0, le=1)
    minimum_margin: float = Field(ge=-1, le=1)

    @model_validator(mode="after")
    def validate_profile(self) -> DualHypothesisSecurityProfile:
        identifiers = [
            item.prototype_id for item in (*self.attack_prototypes, *self.safe_scope_prototypes)
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("security semantic prototype IDs must be unique")
        attack_total = self.hikma_weight + self.attack_semantic_weight + self.structured_weight
        safe_total = self.safe_semantic_weight + self.scope_weight
        if not math.isclose(attack_total, 1.0, abs_tol=1e-9):
            raise ValueError("attack hypothesis weights must sum to 1")
        if not math.isclose(safe_total, 1.0, abs_tol=1e-9):
            raise ValueError("safe-scope hypothesis weights must sum to 1")
        return self

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


def load_dual_hypothesis_profile(
    path: str | Path,
) -> DualHypothesisSecurityProfile:
    profile_path = Path(path)
    if not profile_path.is_file():
        raise ValueError(f"dual-hypothesis security Profile is missing: {profile_path}")
    try:
        return DualHypothesisSecurityProfile.model_validate_json(
            profile_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"dual-hypothesis security Profile is invalid: {profile_path}") from exc


class DualHypothesisWindowScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str
    attack_score: float = Field(ge=0, le=1)
    safe_scope_score: float = Field(ge=0, le=1)
    decision_margin: float = Field(ge=-1, le=1)
    marked: bool
    scope: InstructionScope
    hikma_score: float = Field(ge=0, le=1)
    attack_semantic_score: float = Field(ge=0, le=1)
    safe_semantic_score: float = Field(ge=0, le=1)
    structured_score: float = Field(ge=0, le=1)
    scope_score: float = Field(ge=0, le=1)
    attack_prototype_id: str
    safe_prototype_id: str
    structured_axes: tuple[str, ...] = ()


SecurityTriState = Literal["attack", "needs_review", "safe"]


class TriStateDualHypothesisProfile(BaseModel):
    """Frozen decision layer over local dual-hypothesis component scores."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["courserag.tri-state-security-profile.v1"] = (
        "courserag.tri-state-security-profile.v1"
    )
    name: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=80)
    enabled: bool = False
    base_profile_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    hikma_weight: float = Field(ge=0, le=1)
    attack_semantic_weight: float = Field(ge=0, le=1)
    structured_weight: float = Field(ge=0, le=1)
    safe_semantic_weight: float = Field(ge=0, le=1)
    scope_weight: float = Field(ge=0, le=1)
    attack_boundary: float = Field(ge=-1, le=1)
    safe_boundary: float = Field(ge=-1, le=1)

    @model_validator(mode="after")
    def validate_tri_state_profile(self) -> TriStateDualHypothesisProfile:
        attack_total = self.hikma_weight + self.attack_semantic_weight + self.structured_weight
        safe_total = self.safe_semantic_weight + self.scope_weight
        if not math.isclose(attack_total, 1.0, abs_tol=1e-9):
            raise ValueError("tri-state attack weights must sum to 1")
        if not math.isclose(safe_total, 1.0, abs_tol=1e-9):
            raise ValueError("tri-state safe weights must sum to 1")
        if self.safe_boundary >= self.attack_boundary:
            raise ValueError("tri-state safe boundary must be below attack boundary")
        return self

    @property
    def sha256(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


class TriStateWindowDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    window_id: str
    decision: SecurityTriState
    risk_score: float = Field(ge=-1, le=1)
    attack_score: float = Field(ge=0, le=1)
    safe_score: float = Field(ge=0, le=1)
    review_required: bool
    reason: str


class TriStateDualHypothesisDecisionLayer:
    def __init__(
        self,
        *,
        profile: TriStateDualHypothesisProfile,
        base_profile_sha256: str,
    ) -> None:
        if profile.base_profile_sha256 != base_profile_sha256:
            raise ValueError("tri-state Profile does not bind the dual-hypothesis Profile")
        self.profile = profile

    def decide_scores(
        self, scores: tuple[DualHypothesisWindowScore, ...]
    ) -> tuple[TriStateWindowDecision, ...]:
        decisions = []
        for score in scores:
            attack = _clamp(
                self.profile.hikma_weight * score.hikma_score
                + self.profile.attack_semantic_weight * score.attack_semantic_score
                + self.profile.structured_weight * score.structured_score
            )
            safe = _clamp(
                self.profile.safe_semantic_weight * score.safe_semantic_score
                + self.profile.scope_weight * score.scope_score
            )
            risk = attack - safe
            if risk >= self.profile.attack_boundary:
                decision: SecurityTriState = "attack"
                reason = "risk_at_or_above_attack_boundary"
            elif risk <= self.profile.safe_boundary:
                decision = "safe"
                reason = "risk_at_or_below_safe_boundary"
            else:
                decision = "needs_review"
                reason = "risk_between_frozen_boundaries"
            decisions.append(
                TriStateWindowDecision(
                    window_id=score.window_id,
                    decision=decision,
                    risk_score=risk,
                    attack_score=attack,
                    safe_score=safe,
                    review_required=decision == "needs_review",
                    reason=reason,
                )
            )
        return tuple(decisions)

    def build_findings(
        self,
        document: ParsedDocumentIR,
        windows: tuple[SecurityTextWindow, ...],
        scores: tuple[DualHypothesisWindowScore, ...],
        decisions: tuple[TriStateWindowDecision, ...],
    ) -> tuple[PromptInjectionFinding, ...]:
        window_by_id = {window.window_id: window for window in windows}
        score_by_id = {score.window_id: score for score in scores}
        block_text = {
            block.block_id: block.text for page in document.pages for block in page.blocks
        }
        findings: list[PromptInjectionFinding] = []
        seen: set[tuple[str, int, int, SecurityTriState]] = set()
        for decision in decisions:
            if decision.decision == "safe":
                continue
            window = window_by_id.get(decision.window_id)
            score = score_by_id.get(decision.window_id)
            if window is None or score is None:
                raise ValueError("tri-state decision references an unknown security window")
            axis = (
                score.structured_axes[0]
                if score.structured_axes
                else "general_untrusted_instruction"
            )
            for segment in window.segments:
                identity = (
                    segment.block_id,
                    segment.block_char_start,
                    segment.block_char_end,
                    decision.decision,
                )
                if identity in seen:
                    continue
                seen.add(identity)
                text = block_text[segment.block_id][
                    segment.block_char_start : segment.block_char_end
                ]
                findings.append(
                    PromptInjectionFinding(
                        rule_id=f"tri_state_{decision.decision}_{axis}",
                        category=(
                            "security_review_required"
                            if decision.decision == "needs_review"
                            else "semantic_prompt_attack"
                        ),
                        severity="error" if decision.decision == "attack" else "warning",
                        char_start=segment.block_char_start,
                        char_end=segment.block_char_end,
                        matched_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        page_index=segment.page_index,
                        block_id=segment.block_id,
                        detector_id="courserag/tri-state-dual-hypothesis@v1",
                        score=decision.attack_score,
                        window_id=decision.window_id,
                        decision_basis="tri_state_calibrated",
                        security_decision=decision.decision,
                        axis_id=axis,
                        signal_ids=(_signal_id(score),),
                        decision_path=(
                            "tri_state_calibrated",
                            f"decision:{decision.decision}",
                            f"risk:{decision.risk_score:.6f}",
                            f"safe_boundary:{self.profile.safe_boundary:.6f}",
                            f"attack_boundary:{self.profile.attack_boundary:.6f}",
                        ),
                    )
                )
        return tuple(
            sorted(
                findings,
                key=lambda item: (
                    item.page_index or 0,
                    item.block_id or "",
                    item.char_start,
                    item.char_end,
                ),
            )
        )


def load_tri_state_profile(path: str | Path) -> TriStateDualHypothesisProfile:
    profile_path = Path(path)
    if not profile_path.is_file():
        raise ValueError(f"tri-state security Profile is missing: {profile_path}")
    try:
        return TriStateDualHypothesisProfile.model_validate_json(
            profile_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError) as exc:
        raise ValueError(f"tri-state security Profile is invalid: {profile_path}") from exc


class DualHypothesisSecurityEnsemble:
    """Fuse local semantic and structured evidence with a calibrated margin."""

    def __init__(
        self,
        *,
        profile: DualHypothesisSecurityProfile,
        hikma_detector: PromptInjectionDetector,
        semantic_encoder: SecuritySemanticEncoder,
        structured_detector: StructuredCapabilityAxes | None = None,
    ) -> None:
        if hikma_detector.detector_id != profile.hikma_detector_id:
            raise ValueError("Hikma detector identity differs from dual-hypothesis Profile")
        if semantic_encoder.identity != profile.semantic_encoder_identity:
            raise ValueError("semantic encoder identity differs from dual-hypothesis Profile")
        self.profile = profile
        self.hikma_detector = hikma_detector
        self.semantic_encoder = semantic_encoder
        self.structured_detector = structured_detector or StructuredCapabilityAxes(version="v2")

    def validate_environment(self) -> None:
        self.hikma_detector.validate_environment()

    def score(
        self, windows: tuple[SecurityTextWindow, ...]
    ) -> tuple[DualHypothesisWindowScore, ...]:
        if not windows:
            return ()
        self.validate_environment()
        hikma = {item.window_id: item for item in self.hikma_detector.score(windows)}
        if set(hikma) != {window.window_id for window in windows}:
            raise ValueError("Hikma scores do not match security windows")

        attack_prototypes = self.profile.attack_prototypes
        safe_prototypes = self.profile.safe_scope_prototypes
        texts = [window.text for window in windows]
        texts.extend(item.text for item in attack_prototypes)
        texts.extend(item.text for item in safe_prototypes)
        vectors = self.semantic_encoder.encode(texts)
        if not vectors or any(len(vector) != len(vectors[0]) for vector in vectors):
            raise ValueError("security semantic encoder returned inconsistent dimensions")
        window_vectors = vectors[: len(windows)]
        attack_start = len(windows)
        safe_start = attack_start + len(attack_prototypes)
        attack_vectors = vectors[attack_start:safe_start]
        safe_vectors = vectors[safe_start:]

        structured_by_window: dict[str, list[object]] = {}
        for signal in self.structured_detector.detect(windows):
            structured_by_window.setdefault(signal.window_id, []).append(signal)

        output: list[DualHypothesisWindowScore] = []
        for window, vector in zip(windows, window_vectors, strict=True):
            attack_similarity, attack_index = _maximum_similarity(vector, attack_vectors)
            safe_similarity, safe_index = _maximum_similarity(vector, safe_vectors)
            signals = structured_by_window.get(window.window_id, [])
            substantive = [
                signal
                for signal in signals
                if getattr(signal, "axis_id", "") != "obfuscation_modifier"
            ]
            structured_score = max(
                (float(getattr(signal, "score", 0.0)) for signal in substantive),
                default=0.0,
            )
            scope = classify_instruction_scope(window.text)
            scope_score = _scope_prior(scope)
            attack_score = _clamp(
                self.profile.hikma_weight * hikma[window.window_id].attack_score
                + self.profile.attack_semantic_weight * attack_similarity
                + self.profile.structured_weight * structured_score
            )
            safe_score = _clamp(
                self.profile.safe_semantic_weight * safe_similarity
                + self.profile.scope_weight * scope_score
            )
            margin = attack_score - safe_score
            output.append(
                DualHypothesisWindowScore(
                    window_id=window.window_id,
                    attack_score=attack_score,
                    safe_scope_score=safe_score,
                    decision_margin=margin,
                    marked=(
                        attack_score >= self.profile.attack_threshold
                        and margin >= self.profile.minimum_margin
                    ),
                    scope=scope,
                    hikma_score=hikma[window.window_id].attack_score,
                    attack_semantic_score=attack_similarity,
                    safe_semantic_score=safe_similarity,
                    structured_score=structured_score,
                    scope_score=scope_score,
                    attack_prototype_id=attack_prototypes[attack_index].prototype_id,
                    safe_prototype_id=safe_prototypes[safe_index].prototype_id,
                    structured_axes=tuple(
                        sorted({str(getattr(signal, "axis_id")) for signal in substantive})
                    ),
                )
            )
        return tuple(output)

    def decide(
        self,
        document: ParsedDocumentIR,
        windows: tuple[SecurityTextWindow, ...],
        scores: tuple[DualHypothesisWindowScore, ...],
    ) -> tuple[PromptInjectionFinding, ...]:
        window_by_id = {window.window_id: window for window in windows}
        block_text = {
            block.block_id: block.text for page in document.pages for block in page.blocks
        }
        findings: list[PromptInjectionFinding] = []
        seen: set[tuple[str, int, int]] = set()
        for score in scores:
            if not score.marked:
                continue
            window = window_by_id.get(score.window_id)
            if window is None:
                raise ValueError("dual-hypothesis score references an unknown window")
            axis = (
                score.structured_axes[0]
                if score.structured_axes
                else "general_untrusted_instruction"
            )
            signal_id = _signal_id(score)
            for segment in window.segments:
                identity = (segment.block_id, segment.block_char_start, segment.block_char_end)
                if identity in seen:
                    continue
                seen.add(identity)
                text = block_text[segment.block_id][
                    segment.block_char_start : segment.block_char_end
                ]
                findings.append(
                    PromptInjectionFinding(
                        rule_id=f"dual_hypothesis_{axis}",
                        category=(
                            "semantic_prompt_attack"
                            if axis == "general_untrusted_instruction"
                            else axis
                        ),
                        severity="warning",
                        char_start=segment.block_char_start,
                        char_end=segment.block_char_end,
                        matched_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        page_index=segment.page_index,
                        block_id=segment.block_id,
                        detector_id="courserag/dual-hypothesis-local@v1",
                        score=score.attack_score,
                        window_id=score.window_id,
                        decision_basis="dual_hypothesis_calibrated",
                        axis_id=axis,
                        signal_ids=(signal_id,),
                        decision_path=(
                            "dual_hypothesis_calibrated",
                            f"scope:{score.scope}",
                            f"attack:{score.attack_score:.6f}",
                            f"safe:{score.safe_scope_score:.6f}",
                            f"margin:{score.decision_margin:.6f}",
                            f"attack_prototype:{score.attack_prototype_id}",
                            f"safe_prototype:{score.safe_prototype_id}",
                        ),
                    )
                )
        return tuple(
            sorted(
                findings,
                key=lambda item: (
                    item.page_index or 0,
                    item.block_id or "",
                    item.char_start,
                    item.char_end,
                ),
            )
        )


def _maximum_similarity(
    vector: Sequence[float], candidates: Sequence[Sequence[float]]
) -> tuple[float, int]:
    if not candidates:
        raise ValueError("security semantic prototype collection is empty")
    scored = [
        (_cosine_similarity(vector, candidate), index) for index, candidate in enumerate(candidates)
    ]
    return max(scored, key=lambda item: (item[0], -item[1]))


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("security semantic vector dimensions differ")
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        raise ValueError("security semantic encoder returned a zero vector")
    return _clamp(numerator / (left_norm * right_norm))


def _scope_prior(scope: InstructionScope) -> float:
    return {
        "operative": 0.0,
        "quoted": 0.85,
        "negated": 1.0,
        "educational": 0.8,
        "defensive_description": 0.9,
        "approved_procedure": 0.75,
    }[scope]


def _signal_id(score: DualHypothesisWindowScore) -> str:
    payload = json.dumps(score.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return f"secsig_{hashlib.sha256(payload.encode()).hexdigest()[:24]}"


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
