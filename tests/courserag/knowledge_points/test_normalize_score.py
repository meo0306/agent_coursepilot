from __future__ import annotations

import pytest

from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    KnowledgePointEvidenceRef,
    WindowExtractionResult,
    sha256_text,
)
from courserag.knowledge_points.normalize import consolidate_candidates
from courserag.knowledge_points.scoring import KnowledgePointScorer, ScoringProfile
from tests.courserag.knowledge_points.conftest import evidence, windows


def _candidate(name: str, evidence_id: str, *, confidence: float = 0.5):
    return KnowledgePointCandidate(
        canonical_name=name,
        aliases=("AI",),
        summary="人工智能的定义与范围",
        evidence_refs=(
            KnowledgePointEvidenceRef(
                evidence_id=evidence_id,
                role="definition",
                is_primary=True,
            ),
        ),
        model_confidence=confidence,
    )


def _result(window, *candidates):
    return WindowExtractionResult(
        window_id=window.window_id,
        window_content_sha256=window.content_sha256,
        provider="fake",
        model="fake-v1",
        prompt_sha256=sha256_text("prompt"),
        extractor_profile_sha256="e" * 64,
        candidates=tuple(candidates),
    )


def test_normalize_and_exact_deduplicate_preserve_all_evidence() -> None:
    source = windows(evidence(1), evidence(2), maximum=30, minimum=10)
    results = tuple(
        _result(
            window,
            _candidate(
                " 人工  智能 ",
                window.evidence[0].evidence_id,
            ),
        )
        for window in source
    )

    drafts = consolidate_candidates(source, results)

    assert len(drafts) == 1
    assert drafts[0].normalized_name == "人工 智能"
    assert len(drafts[0].window_ids) == len(source)
    assert {item.evidence_id for item in drafts[0].evidence_refs} == {
        window.evidence[0].evidence_id for window in source
    }


def test_candidate_cannot_reference_evidence_outside_window() -> None:
    source = windows(evidence(1), maximum=200)
    result = _result(source[0], _candidate("人工智能", f"ev1_{999:064x}"))

    with pytest.raises(ValueError, match="outside"):
        consolidate_candidates(source, (result,))


def test_model_confidence_does_not_change_publish_score() -> None:
    source = windows(evidence(1), maximum=200)
    low = consolidate_candidates(
        source,
        (
            _result(
                source[0], _candidate("人工智能", source[0].evidence[0].evidence_id, confidence=0)
            ),
        ),
    )[0]
    high_candidate = _candidate("人工智能", source[0].evidence[0].evidence_id, confidence=1)
    high = consolidate_candidates(source, (_result(source[0], high_candidate),))[0]
    scorer = KnowledgePointScorer(ScoringProfile(name="default", version="v1"))

    assert scorer.score(low) == scorer.score(high)


def test_ambiguity_forces_needs_review_even_above_threshold() -> None:
    source = windows(evidence(1), maximum=200)
    candidate = _candidate("人工智能", source[0].evidence[0].evidence_id)
    ambiguous = candidate.model_copy(update={"ambiguity_flags": ("GRANULARITY",)})
    draft = consolidate_candidates(source, (_result(source[0], ambiguous),))[0]
    score = KnowledgePointScorer(ScoringProfile(name="default", version="v1", threshold=0.1)).score(
        draft
    )

    assert score.status == "needs_review"
    assert not score.deterministic_checks_passed
