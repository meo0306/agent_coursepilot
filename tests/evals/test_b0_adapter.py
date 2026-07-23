from courserag.evals.b0_adapter import (
    LegacyChunkObservation,
    MatchMethod,
    adapt_legacy_chunks,
)
from courserag.evals.schemas import EvidenceRecord
from evaluation.contracts import ReviewStatus, SourceSpan

DOCUMENT_HASH = "a" * 64
CONTENT_HASH = "b" * 64


def _evidence(
    text: str,
    *,
    evidence_id: str = "evidence-1",
    document_id: str = "document-1",
    page_start: int | None = 1,
    page_end: int | None = 1,
    char_start: int | None = None,
    char_end: int | None = None,
) -> EvidenceRecord:
    return EvidenceRecord(
        record_id=evidence_id,
        review_status=ReviewStatus.CANDIDATE,
        candidate_source="unit_test",
        evidence_id=evidence_id,
        source_span=SourceSpan(
            document_id=document_id,
            document_version="v1",
            document_sha256=DOCUMENT_HASH,
            page_start=page_start,
            page_end=page_end,
            char_start=char_start,
            char_end=char_end,
        ),
        source_type="synthetic",
        gold_text=text,
        content_sha256=CONTENT_HASH,
        semantic_unit_type="definition",
    )


def _chunk(
    content: str,
    *,
    chunk_id: str = "legacy-1",
    document_id: str = "document-1",
    document_sha256: str = DOCUMENT_HASH,
    page_start: int | None = 1,
    page_end: int | None = 1,
    char_start: int | None = None,
    char_end: int | None = None,
) -> LegacyChunkObservation:
    return LegacyChunkObservation(
        chunk_id=chunk_id,
        rank=1,
        document_id=document_id,
        document_sha256=document_sha256,
        content=content,
        page_start=page_start,
        page_end=page_end,
        char_start=char_start,
        char_end=char_end,
    )


def test_exact_match_normalizes_nfkc_whitespace_and_case():
    evidence = _evidence("Ａgent   COURSE")
    matches = adapt_legacy_chunks([_chunk("prefix agent course suffix")], [evidence])

    assert len(matches) == 1
    assert matches[0].method is MatchMethod.EXACT_TEXT
    assert matches[0].coverage == 1.0


def test_source_identity_and_page_overlap_are_required():
    evidence = _evidence("A sufficiently long independent evidence sentence.")

    assert not adapt_legacy_chunks(
        [_chunk(evidence.gold_text, document_id="other-document")],
        [evidence],
    )
    assert not adapt_legacy_chunks(
        [_chunk(evidence.gold_text, page_start=2, page_end=2)],
        [evidence],
    )


def test_character_span_match_uses_gold_span_coverage():
    evidence = _evidence(
        "A sufficiently long evidence sentence for span matching.",
        page_start=None,
        page_end=None,
        char_start=100,
        char_end=200,
    )
    chunk = _chunk(
        "content that intentionally does not text-match",
        page_start=None,
        page_end=None,
        char_start=110,
        char_end=200,
    )

    match = adapt_legacy_chunks([chunk], [evidence])[0]

    assert match.method is MatchMethod.CHARACTER_SPAN
    assert match.coverage == 0.9


def test_contiguous_text_requires_configured_coverage():
    gold = "abcdefghij" * 2
    evidence = _evidence(gold)
    chunk = _chunk(f"prefix {gold[:16]} changed-tail")

    assert len(adapt_legacy_chunks([chunk], [evidence])) == 1
    assert not adapt_legacy_chunks(
        [chunk],
        [evidence],
        overlap_threshold=0.9,
    )


def test_short_evidence_is_exact_only():
    evidence = _evidence("short evidence")
    chunk = _chunk("short evidencX")

    assert not adapt_legacy_chunks(
        [chunk],
        [evidence],
        overlap_threshold=0.5,
    )


def test_legacy_chunk_id_is_trace_only():
    evidence = _evidence("independent evidence text")
    first = adapt_legacy_chunks(
        [_chunk(evidence.gold_text, chunk_id="chunk-A")],
        [evidence],
    )
    second = adapt_legacy_chunks(
        [_chunk(evidence.gold_text, chunk_id="chunk-B")],
        [evidence],
    )

    assert first[0].evidence_id == second[0].evidence_id
    assert first[0].coverage == second[0].coverage
    assert first[0].legacy_chunk_id != second[0].legacy_chunk_id
