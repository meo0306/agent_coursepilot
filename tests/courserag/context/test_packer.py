from hashlib import sha256

from courserag.context import ContextPacker, ContextProfile
from courserag.contracts.common import RequestContext, ResponseMeta
from courserag.contracts.retrieval import (
    QueryTrace,
    RetrievalTrace,
    ScoreBreakdown,
    SearchHit,
    SearchResponse,
    SourceTier,
)
from courserag.domain.evidence import (
    EvidenceRecord,
    EvidenceSourceUnit,
    normalize_evidence_text,
    stable_evidence_id,
)


class Tokenizer:
    tokenizer_id = "test"
    tokenizer_sha256 = "1" * 64

    def count(self, text: str) -> int:
        return len(text.split())

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index, _value in enumerate(text.split()))

    def token_ids(self, text: str) -> tuple[int | str, ...]:
        return tuple(text.split())


def _evidence(label: str, text: str, *, previous: str | None = None) -> EvidenceRecord:
    content_hash = sha256(text.encode()).hexdigest()
    unit = EvidenceSourceUnit(
        block_id=f"block-{label}",
        block_type="paragraph",
        ordinal=0,
        char_start=0,
        char_end=len(text),
        text=text,
        text_sha256=content_hash,
    )
    return EvidenceRecord(
        evidence_id=stable_evidence_id("version-1", (unit,), content_hash),
        document_id="document-1",
        document_version_id="version-1",
        section_id="section-1",
        section_path=("第一章",),
        evidence_type="paragraph",
        source_mode="native",
        text=text,
        content_sha256=content_hash,
        normalized_sha256=sha256(normalize_evidence_text(text).encode()).hexdigest(),
        source_units=(unit,),
        previous_evidence_id=previous,
    )


def test_context_deduplicates_and_preserves_complete_evidence() -> None:
    first = _evidence("a", "alpha beta")
    second = _evidence("b", "gamma delta", previous=first.evidence_id)
    records = {first.evidence_id: first, second.evidence_id: second}
    request_context = RequestContext(request_id="req", trace_id="trace")
    search = SearchResponse(
        meta=ResponseMeta.from_context(request_context),
        query=QueryTrace(original="q", normalized="q"),
        hits=[
            SearchHit(
                rank=1,
                chunk_id="chunk-1",
                document_version="version-1",
                text="ignored chunk text",
                scores=ScoreBreakdown(),
                evidence_ids=[second.evidence_id, second.evidence_id],
                source_tier=SourceTier.PRIMARY_SOURCE,
            )
        ],
        retrieval=RetrievalTrace(
            retrieval_config_version="v1",
            index_version="index-1",
            candidate_count=1,
            returned_count=1,
            run_id="run-1",
        ),
    )
    package = ContextPacker(
        resolve_evidence=lambda evidence_id: records[evidence_id],
        tokenizer=Tokenizer(),
        profile=ContextProfile(max_items=8, max_tokens=10),
    ).pack(
        context=request_context,
        query="q",
        purpose="question_answering",
        search=search,
        intent_route="procedure",
    )
    assert [item.evidence_ids[0] for item in package.items] == [
        second.evidence_id,
        first.evidence_id,
    ]
    assert package.packing_report.deduplicated_count == 1
    assert package.packing_report.neighbor_expansion_count == 1
    assert all(not item.truncated for item in package.items)
    assert set(package.evidence_map) == {first.evidence_id, second.evidence_id}


def test_oversized_evidence_is_dropped_not_truncated() -> None:
    record = _evidence("large", "one two three four five")
    context = RequestContext(request_id="req", trace_id="trace")
    search = SearchResponse(
        meta=ResponseMeta.from_context(context),
        query=QueryTrace(original="q", normalized="q"),
        hits=[
            SearchHit(
                rank=1,
                chunk_id="chunk",
                document_version="version-1",
                text="",
                scores=ScoreBreakdown(),
                evidence_ids=[record.evidence_id],
                source_tier=SourceTier.PRIMARY_SOURCE,
            )
        ],
        retrieval=RetrievalTrace(
            retrieval_config_version="v1",
            index_version="index",
            candidate_count=1,
            returned_count=1,
        ),
    )
    package = ContextPacker(
        resolve_evidence=lambda _value: record,
        tokenizer=Tokenizer(),
        profile=ContextProfile(max_tokens=3),
    ).pack(context=context, query="q", purpose="question_answering", search=search)
    assert package.items == []
    assert package.packing_report.oversized_evidence_count == 1
    assert "OVERSIZED_EVIDENCE_DROPPED" in package.meta.warnings


def test_item_limit_groups_evidence_by_search_hit_without_losing_citation_ids() -> None:
    first_a = _evidence("first-a", "first a")
    first_b = _evidence("first-b", "first b")
    second_a = _evidence("second-a", "second a")
    second_b = _evidence("second-b", "second b")
    records = {value.evidence_id: value for value in (first_a, first_b, second_a, second_b)}
    context = RequestContext(request_id="req", trace_id="trace")
    search = SearchResponse(
        meta=ResponseMeta.from_context(context),
        query=QueryTrace(original="q", normalized="q"),
        hits=[
            SearchHit(
                rank=1,
                chunk_id="chunk-1",
                document_version="version-1",
                text="",
                scores=ScoreBreakdown(),
                evidence_ids=[first_a.evidence_id, first_b.evidence_id],
                source_tier=SourceTier.PRIMARY_SOURCE,
            ),
            SearchHit(
                rank=2,
                chunk_id="chunk-2",
                document_version="version-1",
                text="",
                scores=ScoreBreakdown(),
                evidence_ids=[second_a.evidence_id, second_b.evidence_id],
                source_tier=SourceTier.PRIMARY_SOURCE,
            ),
        ],
        retrieval=RetrievalTrace(
            retrieval_config_version="v1",
            index_version="index",
            candidate_count=2,
            returned_count=2,
        ),
    )
    package = ContextPacker(
        resolve_evidence=lambda evidence_id: records[evidence_id],
        tokenizer=Tokenizer(),
        profile=ContextProfile(max_items=2, max_tokens=20),
    ).pack(context=context, query="q", purpose="question_answering", search=search)
    assert [item.evidence_ids for item in package.items] == [
        [first_a.evidence_id, first_b.evidence_id],
        [second_a.evidence_id, second_b.evidence_id],
    ]
    assert package.packing_report.selected_by_hit_rank == {"1": 1, "2": 1}
    assert package.packing_report.selected_evidence_count == 4
    assert package.packing_report.discarded_for_item_limit == 0
    assert package.packing_report.discarded_for_token_limit == 0
    assert [segment.evidence_id for segment in package.items[0].evidence_segments] == [
        first_a.evidence_id,
        first_b.evidence_id,
    ]
    assert [segment.text for segment in package.items[0].evidence_segments] == [
        first_a.text,
        first_b.text,
    ]

    generation_limited = ContextPacker(
        resolve_evidence=lambda evidence_id: records[evidence_id],
        tokenizer=Tokenizer(),
        profile=ContextProfile(max_items=2, max_tokens=20),
    ).pack(
        context=context,
        query="q",
        purpose="generation:lesson",
        search=search,
        max_items=1,
        max_tokens=10,
    )
    assert len(generation_limited.items) == 1
    assert generation_limited.packing_report.token_budget == 10
    assert generation_limited.packing_report.discarded_for_item_limit == 2
