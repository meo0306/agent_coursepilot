from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

CITATION_COMPOSER_VERSION = "claim_evidence_char_bigram_v1"


@dataclass(frozen=True)
class CitationSelection:
    evidence_ids: tuple[str, ...]
    score: float
    status: str


def compose_claim_evidence_ids(
    claim_text: str,
    evidence_texts: Mapping[str, str],
) -> tuple[str, ...]:
    """Select one stable Evidence for an atomic Claim without consulting Gold.

    P09 Claims are contractually atomic.  The composer therefore chooses the Context
    Evidence whose normalized character bigrams cover the largest share of the Claim.
    A stable Evidence-ID tie break makes replay deterministic.
    """

    selected = compose_claim_evidence(claim_text, evidence_texts).evidence_ids
    if selected or not evidence_texts:
        return selected
    return (sorted(evidence_texts)[0],)


def compose_claim_evidence(
    claim_text: str,
    evidence_texts: Mapping[str, str],
    *,
    original_evidence_ids: tuple[str, ...] = (),
) -> CitationSelection:
    if not evidence_texts:
        return CitationSelection(original_evidence_ids, 0.0, "no_context_evidence")
    claim_bigrams = _bigrams(claim_text)
    ranked = sorted(
        (
            (_coverage(claim_bigrams, _bigrams(text)), evidence_id)
            for evidence_id, text in evidence_texts.items()
        ),
        key=lambda value: (-value[0], value[1]),
    )
    score, evidence_id = ranked[0]
    if score <= 0:
        retained = tuple(value for value in original_evidence_ids if value in evidence_texts)
        return CitationSelection(retained, 0.0, "model_reference_retained_no_lexical_signal")
    return CitationSelection((evidence_id,), score, "composed")


def _bigrams(text: str) -> frozenset[str]:
    normalized = "".join(
        character.lower()
        for character in unicodedata.normalize("NFKC", text)
        if character.isalnum() or "\u4e00" <= character <= "\u9fff"
    )
    if len(normalized) < 2:
        return frozenset({normalized}) if normalized else frozenset()
    return frozenset(normalized[index : index + 2] for index in range(len(normalized) - 1))


def _coverage(claim: frozenset[str], evidence: frozenset[str]) -> float:
    return len(claim & evidence) / len(claim) if claim else 0.0
