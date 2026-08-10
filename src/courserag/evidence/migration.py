"""Version-aware Citation Migration with conservative ambiguity handling."""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Sequence
from difflib import SequenceMatcher
from typing import Literal, Protocol

from pydantic import Field

from courserag.domain.document import StrictIRModel
from courserag.evidence.resolver import EvidenceNotFoundError, EvidenceResolver


class CitationMigrationRequest(StrictIRModel):
    course_id: str = Field(min_length=1, max_length=160)
    reference_type: Literal["evidence", "legacy_chunk"]
    reference_id: str = Field(min_length=1, max_length=160)
    source_document_version_id: str = Field(min_length=1, max_length=160)
    target_document_version_id: str = Field(min_length=1, max_length=160)


class CitationMigrationResult(StrictIRModel):
    status: Literal["valid", "migrated", "needs_review", "invalid"]
    source_reference_id: str
    target_evidence_id: str | None = None
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]+$")
    method: Literal["same_version", "exact", "structure", "similarity"] | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    candidates: tuple[CitationMigrationCandidate, ...] = ()


class CitationMigrationCandidate(StrictIRModel):
    evidence_id: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    section_path: tuple[str, ...] = ()
    score: float = Field(ge=0, le=1)
    method: Literal["exact", "structure", "similarity"]


class MigrationEvidence(StrictIRModel):
    evidence_id: str
    document_version_id: str
    text: str
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    section_path: tuple[str, ...] = ()
    previous_text: str | None = None
    next_text: str | None = None


class CitationMigrationProfile(StrictIRModel):
    auto_similarity: float = Field(default=0.92, ge=0, le=1)
    review_similarity: float = Field(default=0.75, ge=0, le=1)
    min_margin: float = Field(default=0.08, ge=0, le=1)

    @property
    def sha256(self) -> str:
        payload = f"{self.auto_similarity:.8f}|{self.review_similarity:.8f}|{self.min_margin:.8f}"
        return hashlib.sha256(payload.encode()).hexdigest()


class MigrationEvidenceSource(Protocol):
    def get_source(self, course_id: str, evidence_id: str) -> MigrationEvidence | None: ...

    def list_target(
        self, course_id: str, document_version_id: str
    ) -> Sequence[MigrationEvidence]: ...


class CitationMigrationPort(Protocol):
    def migrate(self, request: CitationMigrationRequest) -> CitationMigrationResult: ...


class P06CitationMigrationSkeleton:
    """Validate same-version Evidence without guessing any cross-version replacement."""

    def __init__(self, resolver: EvidenceResolver) -> None:
        self.resolver = resolver

    def migrate(self, request: CitationMigrationRequest) -> CitationMigrationResult:
        if request.reference_type == "legacy_chunk":
            return CitationMigrationResult(
                status="invalid",
                source_reference_id=request.reference_id,
                reason_code="LEGACY_CHUNK_IS_NOT_EVIDENCE",
            )
        if request.source_document_version_id != request.target_document_version_id:
            return CitationMigrationResult(
                status="needs_review",
                source_reference_id=request.reference_id,
                reason_code="CROSS_VERSION_MIGRATION_DEFERRED_TO_P10",
            )
        try:
            evidence = self.resolver.resolve(request.course_id, request.reference_id)
        except EvidenceNotFoundError:
            return CitationMigrationResult(
                status="invalid",
                source_reference_id=request.reference_id,
                reason_code="EVIDENCE_NOT_FOUND",
            )
        if evidence.document_version_id != request.source_document_version_id:
            return CitationMigrationResult(
                status="invalid",
                source_reference_id=request.reference_id,
                reason_code="EVIDENCE_VERSION_MISMATCH",
            )
        return CitationMigrationResult(
            status="valid",
            source_reference_id=request.reference_id,
            target_evidence_id=evidence.evidence_id,
            reason_code="SAME_VERSION_EVIDENCE_VALID",
            method="same_version",
            confidence=1.0,
        )


class P10CitationMigrator:
    """Map immutable Evidence across versions without guessing duplicate sources."""

    def __init__(
        self,
        source: MigrationEvidenceSource,
        profile: CitationMigrationProfile | None = None,
    ) -> None:
        self.source = source
        self.profile = profile or CitationMigrationProfile()

    def migrate(self, request: CitationMigrationRequest) -> CitationMigrationResult:
        if request.reference_type == "legacy_chunk":
            return _result(request, "invalid", "LEGACY_CHUNK_IS_NOT_EVIDENCE")
        origin = self.source.get_source(request.course_id, request.reference_id)
        if origin is None or origin.document_version_id != request.source_document_version_id:
            return _result(request, "invalid", "SOURCE_EVIDENCE_NOT_FOUND")
        if request.source_document_version_id == request.target_document_version_id:
            return CitationMigrationResult(
                status="valid",
                source_reference_id=request.reference_id,
                target_evidence_id=origin.evidence_id,
                reason_code="SAME_VERSION_EVIDENCE_VALID",
                method="same_version",
                confidence=1.0,
            )
        targets = tuple(
            self.source.list_target(request.course_id, request.target_document_version_id)
        )
        if not targets:
            return _result(request, "invalid", "TARGET_VERSION_HAS_NO_EVIDENCE")

        exact = [item for item in targets if item.content_sha256 == origin.content_sha256]
        if len(exact) == 1:
            candidate = _candidate(exact[0], 1.0, "exact")
            return _migrated(request, candidate, "UNIQUE_CONTENT_HASH_MATCH")
        if len(exact) > 1:
            candidates = tuple(_candidate(item, 1.0, "exact") for item in exact)
            return CitationMigrationResult(
                status="needs_review",
                source_reference_id=request.reference_id,
                reason_code="DUPLICATE_EXACT_MATCH",
                candidates=candidates,
            )

        structural = [
            item
            for item in targets
            if item.section_path == origin.section_path
            and _normalized(item.text) == _normalized(origin.text)
        ]
        if len(structural) == 1:
            candidate = _candidate(structural[0], 0.99, "structure")
            return _migrated(request, candidate, "UNIQUE_STRUCTURE_TEXT_MATCH")
        if len(structural) > 1:
            return CitationMigrationResult(
                status="needs_review",
                source_reference_id=request.reference_id,
                reason_code="DUPLICATE_STRUCTURE_MATCH",
                candidates=tuple(_candidate(item, 0.99, "structure") for item in structural),
            )

        scored = sorted(
            (_candidate(item, _score(origin, item), "similarity") for item in targets),
            key=lambda item: (-item.score, item.evidence_id),
        )
        best = scored[0]
        runner_up = scored[1].score if len(scored) > 1 else 0.0
        margin = best.score - runner_up
        if best.score >= self.profile.auto_similarity and margin >= self.profile.min_margin:
            return _migrated(request, best, "HIGH_CONFIDENCE_SIMILARITY")
        review = tuple(item for item in scored if item.score >= self.profile.review_similarity)
        if review:
            return CitationMigrationResult(
                status="needs_review",
                source_reference_id=request.reference_id,
                reason_code=(
                    "SIMILARITY_MARGIN_TOO_SMALL"
                    if best.score >= self.profile.auto_similarity
                    else "SIMILARITY_REQUIRES_REVIEW"
                ),
                candidates=review,
            )
        return _result(request, "invalid", "NO_CREDIBLE_TARGET")


def _result(
    request: CitationMigrationRequest,
    status: Literal["valid", "migrated", "needs_review", "invalid"],
    reason: str,
) -> CitationMigrationResult:
    return CitationMigrationResult(
        status=status,
        source_reference_id=request.reference_id,
        reason_code=reason,
    )


def _migrated(
    request: CitationMigrationRequest,
    candidate: CitationMigrationCandidate,
    reason: str,
) -> CitationMigrationResult:
    return CitationMigrationResult(
        status="migrated",
        source_reference_id=request.reference_id,
        target_evidence_id=candidate.evidence_id,
        reason_code=reason,
        method=candidate.method,
        confidence=candidate.score,
        candidates=(candidate,),
    )


def _candidate(
    value: MigrationEvidence,
    score: float,
    method: Literal["exact", "structure", "similarity"],
) -> CitationMigrationCandidate:
    return CitationMigrationCandidate(
        evidence_id=value.evidence_id,
        content_sha256=value.content_sha256,
        section_path=value.section_path,
        score=max(0.0, min(1.0, score)),
        method=method,
    )


def _score(origin: MigrationEvidence, target: MigrationEvidence) -> float:
    text_score = SequenceMatcher(None, _normalized(origin.text), _normalized(target.text)).ratio()
    trigram_score = _jaccard(_trigrams(origin.text), _trigrams(target.text))
    section_score = (
        1.0
        if origin.section_path == target.section_path
        else _path_overlap(origin.section_path, target.section_path)
    )
    adjacency_score = _adjacency(origin, target)
    return 0.55 * text_score + 0.25 * trigram_score + 0.15 * section_score + 0.05 * adjacency_score


def _normalized(value: str) -> str:
    return " ".join(re.sub(r"[^\w\u4e00-\u9fff]+", " ", value.casefold()).split())


def _trigrams(value: str) -> Counter[str]:
    normalized = _normalized(value).replace(" ", "")
    if len(normalized) < 3:
        return Counter({normalized: 1}) if normalized else Counter()
    return Counter(normalized[index : index + 3] for index in range(len(normalized) - 2))


def _jaccard(left: Counter[str], right: Counter[str]) -> float:
    keys = set(left) | set(right)
    union = sum(max(left[key], right[key]) for key in keys)
    return sum(min(left[key], right[key]) for key in keys) / union if union else 0.0


def _path_overlap(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    if not left or not right:
        return 0.0
    common = sum(a == b for a, b in zip(left, right, strict=False))
    return common / max(len(left), len(right))


def _adjacency(left: MigrationEvidence, right: MigrationEvidence) -> float:
    pairs = ((left.previous_text, right.previous_text), (left.next_text, right.next_text))
    scores = [
        SequenceMatcher(None, _normalized(a), _normalized(b)).ratio() for a, b in pairs if a and b
    ]
    return sum(scores) / len(scores) if scores else 0.0
