from __future__ import annotations

import hashlib
from collections.abc import Sequence

import pytest

from courserag.domain.document import BlockIR, PageIR, ParsedDocumentIR, SourceSpan
from courserag.security.detector import DetectorScore, SecurityTextWindow, WindowSegment
from courserag.security.dual_hypothesis import (
    DualHypothesisSecurityEnsemble,
    DualHypothesisSecurityProfile,
    DualHypothesisWindowScore,
    SemanticPrototype,
    TriStateDualHypothesisDecisionLayer,
    TriStateDualHypothesisProfile,
)


class _SemanticEncoder:
    identity = "fake-qwen3"

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            value = text.casefold()
            vectors.append([0.0, 1.0] if "safe" in value else [1.0, 0.0])
        return vectors


class _Hikma:
    detector_id = "fake-hikma"

    def __init__(self, score: float) -> None:
        self.value = score

    def validate_environment(self) -> None:
        return None

    def score(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[DetectorScore, ...]:
        return tuple(
            DetectorScore(
                window_id=window.window_id,
                attack_score=self.value,
                detector_id=self.detector_id,
                model_revision="test",
            )
            for window in windows
        )


def _profile(*, enabled: bool = False) -> DualHypothesisSecurityProfile:
    attacks = tuple(
        SemanticPrototype(
            prototype_id=f"attack-{index}",
            language="en" if index % 2 else "zh",
            family="policy_override",
            text=f"attack prototype {index}",
        )
        for index in range(4)
    )
    safe = tuple(
        SemanticPrototype(
            prototype_id=f"safe-{index}",
            language="en" if index % 2 else "zh",
            family="quoted",
            text=f"safe prototype {index}",
        )
        for index in range(4)
    )
    return DualHypothesisSecurityProfile(
        name="test",
        version="1",
        enabled=enabled,
        semantic_encoder_identity="fake-qwen3",
        hikma_detector_id="fake-hikma",
        attack_prototypes=attacks,
        safe_scope_prototypes=safe,
        hikma_weight=0.5,
        attack_semantic_weight=0.4,
        structured_weight=0.1,
        safe_semantic_weight=0.7,
        scope_weight=0.3,
        attack_threshold=0.65,
        minimum_margin=0.05,
    )


def _inputs(text: str) -> tuple[ParsedDocumentIR, tuple[SecurityTextWindow, ...]]:
    block = BlockIR(
        block_id="block-1",
        block_type="paragraph",
        text=text,
        order_index=0,
        source_span=SourceSpan(
            document_id="doc-1",
            document_version_id="doc-v1",
            page_start=1,
            page_end=1,
            block_start_id="block-1",
            block_end_id="block-1",
            char_start=0,
            char_end=len(text),
        ),
        content_sha256=hashlib.sha256(text.encode()).hexdigest(),
    )
    document = ParsedDocumentIR(
        document_id="doc-1",
        document_version_id="doc-v1",
        document_sha256=hashlib.sha256(text.encode()).hexdigest(),
        source_format="pdf",
        parser_profile="test",
        parser_version="1",
        pages=(
            PageIR(
                page_id="page-1",
                physical_page_index=1,
                width=100,
                height=100,
                source_mode="native_text",
                blocks=(block,),
                content_sha256=hashlib.sha256(text.encode()).hexdigest(),
            ),
        ),
        sections=(),
    )
    window = SecurityTextWindow(
        window_id=f"secwin_{hashlib.sha256(text.encode()).hexdigest()[:24]}",
        text=text,
        token_start=0,
        token_end=1,
        segments=(
            WindowSegment(
                page_index=1,
                block_id="block-1",
                block_char_start=0,
                block_char_end=len(text),
                window_char_start=0,
                window_char_end=len(text),
            ),
        ),
    )
    return document, (window,)


def test_semantic_attack_can_mark_without_a_structured_triplet() -> None:
    document, windows = _inputs(
        "Malicious indirect request whose wording contains no frozen action vocabulary."
    )
    ensemble = DualHypothesisSecurityEnsemble(
        profile=_profile(),
        hikma_detector=_Hikma(0.9),
        semantic_encoder=_SemanticEncoder(),
    )
    scores = ensemble.score(windows)
    findings = ensemble.decide(document, windows, scores)
    assert scores[0].structured_score == 0
    assert scores[0].marked is True
    assert len(findings) == 1
    assert findings[0].decision_basis == "dual_hypothesis_calibrated"


def test_safe_scope_competes_with_a_high_hikma_score() -> None:
    document, windows = _inputs(
        "This safe chapter quotes an attack for defensive analysis and requests no action."
    )
    ensemble = DualHypothesisSecurityEnsemble(
        profile=_profile(),
        hikma_detector=_Hikma(0.95),
        semantic_encoder=_SemanticEncoder(),
    )
    scores = ensemble.score(windows)
    assert scores[0].safe_scope_score > scores[0].attack_score
    assert ensemble.decide(document, windows, scores) == ()


def test_profile_rejects_unstable_encoder_identity() -> None:
    class _WrongEncoder(_SemanticEncoder):
        identity = "different-model"

    with pytest.raises(ValueError, match="semantic encoder identity"):
        DualHypothesisSecurityEnsemble(
            profile=_profile(),
            hikma_detector=_Hikma(0.5),
            semantic_encoder=_WrongEncoder(),
        )


def test_profile_requires_normalized_hypothesis_weights() -> None:
    payload = _profile().model_dump()
    payload["hikma_weight"] = 0.8
    with pytest.raises(ValueError, match="attack hypothesis weights"):
        DualHypothesisSecurityProfile.model_validate(payload)


def test_tri_state_layer_routes_boundary_scores_without_safe_fallback() -> None:
    profile = TriStateDualHypothesisProfile(
        name="tri-state-test",
        version="1",
        base_profile_sha256="a" * 64,
        hikma_weight=0.5,
        attack_semantic_weight=0.5,
        structured_weight=0,
        safe_semantic_weight=0.5,
        scope_weight=0.5,
        attack_boundary=0.4,
        safe_boundary=-0.2,
    )
    layer = TriStateDualHypothesisDecisionLayer(
        profile=profile,
        base_profile_sha256="a" * 64,
    )

    def score(window_id: str, attack: float, safe: float) -> DualHypothesisWindowScore:
        return DualHypothesisWindowScore(
            window_id=window_id,
            attack_score=attack,
            safe_scope_score=safe,
            decision_margin=attack - safe,
            marked=False,
            scope="operative",
            hikma_score=attack,
            attack_semantic_score=attack,
            safe_semantic_score=safe,
            structured_score=0,
            scope_score=0,
            attack_prototype_id="attack",
            safe_prototype_id="safe",
        )

    attack = score("attack-001", 0.95, 0.1)
    review = score("review-001", 0.6, 0.5)
    safe = score("safe-001", 0.1, 0.9)

    decisions = layer.decide_scores((attack, review, safe))

    assert [item.decision for item in decisions] == ["attack", "needs_review", "safe"]
    assert decisions[1].review_required is True
    assert decisions[2].review_required is False


def test_tri_state_profile_rejects_overlapping_boundaries() -> None:
    with pytest.raises(ValueError, match="safe boundary must be below attack boundary"):
        TriStateDualHypothesisProfile(
            name="tri-state-test",
            version="1",
            base_profile_sha256="a" * 64,
            hikma_weight=0.5,
            attack_semantic_weight=0.5,
            structured_weight=0,
            safe_semantic_weight=0.5,
            scope_weight=0.5,
            attack_boundary=0.2,
            safe_boundary=0.2,
        )
