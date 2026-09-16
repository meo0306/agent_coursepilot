from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from courserag.chunking.tokenizer import TokenCounter
from courserag.context.models import ContextProfile, ExpansionSource
from courserag.contracts.common import RequestContext, ResponseMeta
from courserag.contracts.retrieval import (
    ContextEvidenceSegment,
    ContextItem,
    ContextPackage,
    EvidenceSummary,
    PackingReport,
    SearchResponse,
)
from courserag.domain.evidence import EvidenceRecord


@dataclass(frozen=True)
class _PackingCandidate:
    evidence_id: str
    source: ExpansionSource
    hit_rank: int | None
    evidence_ordinal: int


@dataclass(frozen=True)
class _ResolvedCandidate:
    record: EvidenceRecord
    source: ExpansionSource
    hit_rank: int | None
    evidence_ordinal: int


@dataclass(frozen=True)
class _ResolvedGroup:
    records: tuple[EvidenceRecord, ...]
    source: ExpansionSource
    hit_rank: int | None
    evidence_ordinal: int


class ContextPacker:
    def __init__(
        self,
        *,
        resolve_evidence: Callable[[str], EvidenceRecord],
        tokenizer: TokenCounter,
        profile: ContextProfile | None = None,
    ) -> None:
        self.resolve_evidence = resolve_evidence
        self.tokenizer = tokenizer
        self.profile = profile or ContextProfile()

    def pack(
        self,
        *,
        context: RequestContext,
        query: str,
        purpose: str,
        search: SearchResponse,
        intent_route: str = "fact",
        max_tokens: int | None = None,
        max_items: int | None = None,
    ) -> ContextPackage:
        token_limit = min(self.profile.max_tokens, max_tokens or self.profile.max_tokens)
        item_limit = min(self.profile.max_items, max_items or self.profile.max_items)
        candidates = _retrieval_candidates(search)
        records, missing = self._resolve_unique(candidates)
        if intent_route in self.profile.include_neighbors_for:
            neighbor_candidates: list[_PackingCandidate] = []
            for candidate in records:
                record = candidate.record
                if record.previous_evidence_id:
                    neighbor_candidates.append(
                        _PackingCandidate(
                            evidence_id=record.previous_evidence_id,
                            source=ExpansionSource.PREVIOUS_NEIGHBOR,
                            hit_rank=candidate.hit_rank,
                            evidence_ordinal=candidate.evidence_ordinal,
                        )
                    )
                if record.next_evidence_id:
                    neighbor_candidates.append(
                        _PackingCandidate(
                            evidence_id=record.next_evidence_id,
                            source=ExpansionSource.NEXT_NEIGHBOR,
                            hit_rank=candidate.hit_rank,
                            evidence_ordinal=candidate.evidence_ordinal,
                        )
                    )
            neighbors, neighbor_missing = self._resolve_unique(neighbor_candidates)
            missing.extend(neighbor_missing)
            known = {candidate.record.evidence_id for candidate in records}
            records.extend(
                candidate for candidate in neighbors if candidate.record.evidence_id not in known
            )
        groups = _group_resolved_candidates(records)

        selected: list[ContextItem] = []
        evidence_map: dict[str, EvidenceSummary] = {}
        token_count = 0
        discarded_for_item_limit = 0
        discarded_for_token_limit = 0
        oversized = 0
        selected_evidence_count = 0
        for group in groups:
            group_text = _group_text(group.records)
            item_tokens = self.tokenizer.count(group_text)
            if item_tokens > token_limit:
                oversized += len(group.records)
                continue
            if len(selected) >= item_limit:
                discarded_for_item_limit += len(group.records)
                continue
            if token_count + item_tokens > token_limit:
                discarded_for_token_limit += len(group.records)
                continue
            evidence_ids = [record.evidence_id for record in group.records]
            selected.append(
                ContextItem(
                    context_item_id=f"ctxgrp_{_digest(evidence_ids)[:32]}",
                    text=group_text,
                    document_id=_common_document_id(group.records),
                    section_path=_common_section_path(group.records),
                    page_start=_group_page_start(group.records),
                    page_end=_group_page_end(group.records),
                    evidence_ids=evidence_ids,
                    evidence_segments=[
                        ContextEvidenceSegment(
                            evidence_id=record.evidence_id,
                            text=record.text,
                            ordinal=index,
                            search_hit_rank=group.hit_rank,
                            content_sha256=record.content_sha256,
                        )
                        for index, record in enumerate(group.records)
                    ],
                    token_count=item_tokens,
                    truncated=False,
                    expansion_source=group.source.value,
                    search_hit_rank=group.hit_rank,
                    evidence_ordinal=group.evidence_ordinal,
                    content_sha256=_digest([record.content_sha256 for record in group.records]),
                )
            )
            token_count += item_tokens
            selected_evidence_count += len(group.records)
            for record in group.records:
                evidence_map[record.evidence_id] = _summary(record)

        warnings = [f"MISSING_EVIDENCE:{value}" for value in missing]
        if oversized:
            warnings.append("OVERSIZED_EVIDENCE_DROPPED")
        report = PackingReport(
            candidate_count=len(candidates),
            selected_count=len(selected),
            selected_evidence_count=selected_evidence_count,
            deduplicated_count=max(
                0, len(candidates) - len({value.evidence_id for value in candidates})
            ),
            discarded_for_budget=discarded_for_item_limit + discarded_for_token_limit,
            discarded_for_item_limit=discarded_for_item_limit,
            discarded_for_token_limit=discarded_for_token_limit,
            oversized_evidence_count=oversized,
            neighbor_expansion_count=sum(
                item.expansion_source != ExpansionSource.RETRIEVAL.value for item in selected
            ),
            core_selected_count=sum(
                item.expansion_source == ExpansionSource.RETRIEVAL.value for item in selected
            ),
            expansion_selected_count=sum(
                item.expansion_source != ExpansionSource.RETRIEVAL.value for item in selected
            ),
            selected_by_hit_rank=_selected_by_hit_rank(selected),
            token_budget=token_limit,
            token_count=token_count,
            tokenizer_id=self.tokenizer.tokenizer_id,
            tokenizer_sha256=self.tokenizer.tokenizer_sha256,
            warnings=warnings,
        )
        payload = {
            "query": query,
            "purpose": purpose,
            "items": [item.model_dump(mode="json") for item in selected],
            "evidence_map": {
                key: value.model_dump(mode="json") for key, value in evidence_map.items()
            },
            "index_version": search.retrieval.index_version,
            "verified_overlay_version": search.retrieval.verified_overlay_version,
            "retrieval_snapshot_id": search.retrieval.retrieval_snapshot_id,
            "packing_report": report.model_dump(mode="json"),
        }
        result_sha256 = _digest(payload)
        return ContextPackage(
            meta=ResponseMeta.from_context(context, warnings=warnings),
            query=query,
            purpose=purpose,
            items=selected,
            token_count=token_count,
            evidence_map=evidence_map,
            retrieval_trace_id=search.retrieval.run_id or context.trace_id,
            index_version=search.retrieval.index_version,
            packing_report=report,
            context_package_id=f"ctxpkg_{result_sha256[:32]}",
            result_sha256=result_sha256,
            verified_overlay_version=search.retrieval.verified_overlay_version,
            retrieval_snapshot_id=search.retrieval.retrieval_snapshot_id,
        )

    def _resolve_unique(
        self, candidates: Iterable[_PackingCandidate]
    ) -> tuple[list[_ResolvedCandidate], list[str]]:
        records: list[_ResolvedCandidate] = []
        missing: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            evidence_id = candidate.evidence_id
            if evidence_id in seen:
                continue
            seen.add(evidence_id)
            try:
                record = self.resolve_evidence(evidence_id)
            except LookupError:
                missing.append(evidence_id)
                continue
            records.append(
                _ResolvedCandidate(
                    record=record,
                    source=candidate.source,
                    hit_rank=candidate.hit_rank,
                    evidence_ordinal=candidate.evidence_ordinal,
                )
            )
        return records, missing


def _retrieval_candidates(search: SearchResponse) -> list[_PackingCandidate]:
    hits = sorted(search.hits, key=lambda value: (value.rank, value.chunk_id))
    candidates: list[_PackingCandidate] = []
    for hit in hits:
        for evidence_ordinal, evidence_id in enumerate(hit.evidence_ids):
            candidates.append(
                _PackingCandidate(
                    evidence_id=evidence_id,
                    source=ExpansionSource.RETRIEVAL,
                    hit_rank=hit.rank,
                    evidence_ordinal=evidence_ordinal,
                )
            )
    return candidates


def _group_resolved_candidates(
    candidates: Iterable[_ResolvedCandidate],
) -> list[_ResolvedGroup]:
    grouped: dict[tuple[ExpansionSource, int | None], list[_ResolvedCandidate]] = {}
    for candidate in candidates:
        key = (candidate.source, candidate.hit_rank)
        grouped.setdefault(key, []).append(candidate)
    return [
        _ResolvedGroup(
            records=tuple(item.record for item in values),
            source=source,
            hit_rank=hit_rank,
            evidence_ordinal=min(item.evidence_ordinal for item in values),
        )
        for (source, hit_rank), values in grouped.items()
    ]


def _group_text(records: tuple[EvidenceRecord, ...]) -> str:
    if len(records) == 1:
        return records[0].text
    return "\n\n".join(f"[{index}] {record.text}" for index, record in enumerate(records, 1))


def _common_document_id(records: tuple[EvidenceRecord, ...]) -> str | None:
    values = {record.document_id for record in records}
    return next(iter(values)) if len(values) == 1 else None


def _common_section_path(records: tuple[EvidenceRecord, ...]) -> list[str]:
    if not records:
        return []
    prefix = list(records[0].section_path)
    for record in records[1:]:
        common_length = 0
        for left, right in zip(prefix, record.section_path, strict=False):
            if left != right:
                break
            common_length += 1
        prefix = prefix[:common_length]
    return prefix


def _group_page_start(records: tuple[EvidenceRecord, ...]) -> int | None:
    values = [value for record in records if (value := _page_start(record)) is not None]
    return min(values) if values else None


def _group_page_end(records: tuple[EvidenceRecord, ...]) -> int | None:
    values = [value for record in records if (value := _page_end(record)) is not None]
    return max(values) if values else None


def _selected_by_hit_rank(items: list[ContextItem]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        if item.search_hit_rank is None:
            continue
        key = str(item.search_hit_rank)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _summary(record: EvidenceRecord) -> EvidenceSummary:
    return EvidenceSummary(
        evidence_id=record.evidence_id,
        document_id=record.document_id,
        document_version_id=record.document_version_id,
        section_id=record.section_id,
        section_path=list(record.section_path),
        page_start=_page_start(record),
        page_end=_page_end(record),
        page_bboxes=[value.model_dump(mode="json") for value in record.page_bboxes],
        source_spans=[value.model_dump(mode="json") for value in record.source_units],
        content_sha256=record.content_sha256,
        source_mode=record.source_mode,
        warning_codes=list(record.warning_codes),
    )


def _page_start(record: EvidenceRecord) -> int | None:
    values = [
        value.physical_page_index for value in record.page_bboxes if value.physical_page_index
    ]
    return min(values) if values else None


def _page_end(record: EvidenceRecord) -> int | None:
    values = [
        value.physical_page_index for value in record.page_bboxes if value.physical_page_index
    ]
    return max(values) if values else None


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
