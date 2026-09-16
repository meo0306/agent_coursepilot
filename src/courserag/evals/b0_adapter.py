from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from enum import StrEnum

from pydantic import Field, model_validator

from courserag.evals.schemas import EvidenceRecord
from evaluation.contracts import Sha256, StrictModel

_WHITESPACE = re.compile(r"\s+")


class MatchMethod(StrEnum):
    EXACT_TEXT = "exact_text"
    CHARACTER_SPAN = "character_span"
    CONTIGUOUS_TEXT = "contiguous_text"


class LegacyChunkObservation(StrictModel):
    """Read-only view of a B0 chunk returned by the legacy retriever."""

    chunk_id: str = Field(min_length=1, max_length=512)
    rank: int = Field(ge=1)
    document_id: str = Field(min_length=1, max_length=160)
    document_sha256: Sha256
    content: str = Field(min_length=1, max_length=200_000)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_coordinates(self) -> LegacyChunkObservation:
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("page_start and page_end must be supplied together")
        if self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must be greater than or equal to page_start")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end <= self.char_start:
                raise ValueError("char_end must be greater than char_start")
        return self


class EvidenceMatch(StrictModel):
    evidence_id: str
    legacy_chunk_id: str
    rank: int = Field(ge=1)
    method: MatchMethod
    coverage: float = Field(ge=0.0, le=1.0)


def normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return _WHITESPACE.sub(" ", normalized).strip()


def adapt_legacy_chunks(
    chunks: list[LegacyChunkObservation],
    gold_evidence: list[EvidenceRecord],
    *,
    overlap_threshold: float = 0.8,
    short_text_exact_length: int = 16,
) -> list[EvidenceMatch]:
    """Map legacy retrieval output to independent Gold Evidence.

    The adapter never creates or modifies Gold.  Legacy chunk identifiers are
    emitted only as trace metadata and do not participate in matching.
    """

    if not 0.0 < overlap_threshold <= 1.0:
        raise ValueError("overlap_threshold must be in (0, 1]")
    if short_text_exact_length < 1:
        raise ValueError("short_text_exact_length must be positive")

    matches: list[EvidenceMatch] = []
    for chunk in sorted(chunks, key=lambda item: item.rank):
        for evidence in gold_evidence:
            if not _same_source(chunk, evidence):
                continue
            match = _match_evidence(
                chunk,
                evidence,
                overlap_threshold=overlap_threshold,
                short_text_exact_length=short_text_exact_length,
            )
            if match is not None:
                matches.append(match)
    return matches


def _same_source(chunk: LegacyChunkObservation, evidence: EvidenceRecord) -> bool:
    span = evidence.source_span
    if chunk.document_id != span.document_id:
        return False
    if chunk.document_sha256 != span.document_sha256:
        return False
    if (
        chunk.page_start is not None
        and chunk.page_end is not None
        and span.page_start is not None
        and span.page_end is not None
    ):
        return not (chunk.page_end < span.page_start or span.page_end < chunk.page_start)
    return True


def _match_evidence(
    chunk: LegacyChunkObservation,
    evidence: EvidenceRecord,
    *,
    overlap_threshold: float,
    short_text_exact_length: int,
) -> EvidenceMatch | None:
    normalized_gold = normalize_match_text(evidence.gold_text)
    normalized_chunk = normalize_match_text(chunk.content)
    if normalized_gold and normalized_gold in normalized_chunk:
        return _match(chunk, evidence, MatchMethod.EXACT_TEXT, 1.0)

    if len(normalized_gold) < short_text_exact_length:
        return None

    span_coverage = _character_span_coverage(chunk, evidence)
    if span_coverage is not None and span_coverage >= overlap_threshold:
        return _match(
            chunk,
            evidence,
            MatchMethod.CHARACTER_SPAN,
            span_coverage,
        )

    if not normalized_gold or not normalized_chunk:
        return None
    longest = SequenceMatcher(
        None,
        normalized_gold,
        normalized_chunk,
        autojunk=False,
    ).find_longest_match()
    coverage = longest.size / len(normalized_gold)
    if coverage < overlap_threshold:
        return None
    return _match(
        chunk,
        evidence,
        MatchMethod.CONTIGUOUS_TEXT,
        coverage,
    )


def _character_span_coverage(
    chunk: LegacyChunkObservation,
    evidence: EvidenceRecord,
) -> float | None:
    span = evidence.source_span
    if (
        chunk.char_start is None
        or chunk.char_end is None
        or span.char_start is None
        or span.char_end is None
    ):
        return None
    overlap = max(
        0,
        min(chunk.char_end, span.char_end) - max(chunk.char_start, span.char_start),
    )
    return overlap / (span.char_end - span.char_start)


def _match(
    chunk: LegacyChunkObservation,
    evidence: EvidenceRecord,
    method: MatchMethod,
    coverage: float,
) -> EvidenceMatch:
    return EvidenceMatch(
        evidence_id=evidence.evidence_id,
        legacy_chunk_id=chunk.chunk_id,
        rank=chunk.rank,
        method=method,
        coverage=coverage,
    )
