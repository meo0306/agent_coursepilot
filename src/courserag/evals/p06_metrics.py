"""Source-grounded P06 Evidence/Chunk metrics without LLM judging."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from courserag.domain.chunk import ChunkArtifact, ChunkRecord
from courserag.domain.evidence import EvidenceArtifact, EvidenceRecord, normalize_evidence_text
from courserag.evals.schemas import EvidenceRecord as GoldEvidenceRecord
from evaluation.contracts import MetricResult


@dataclass(frozen=True)
class EvidenceMatch:
    gold_evidence_id: str
    system_evidence_id: str
    match_basis: str


def map_gold_to_system_evidence(
    gold: Sequence[GoldEvidenceRecord],
    system: Sequence[EvidenceRecord],
    *,
    document_aliases: Mapping[str, str] | None = None,
) -> tuple[EvidenceMatch, ...]:
    aliases = document_aliases or {}
    matches: list[EvidenceMatch] = []
    for gold_record in gold:
        best: tuple[int, EvidenceRecord, str] | None = None
        gold_units = {unit.source_unit_id for unit in gold_record.source_units}
        gold_normalized = normalize_evidence_text(gold_record.gold_text)
        for system_record in system:
            logical_document_id = aliases.get(system_record.document_id, system_record.document_id)
            if logical_document_id != gold_record.source_span.document_id:
                continue
            score = 0
            basis = ""
            if system_record.normalized_sha256 == gold_record.normalized_content_sha256:
                score = 4
                basis = "normalized_hash"
            elif gold_normalized in normalize_evidence_text(system_record.text):
                score = 3
                basis = "normalized_text_containment"
            elif gold_units & {unit.block_id for unit in system_record.source_units}:
                score = 2
                basis = "source_unit_overlap"
            if score and gold_record.source_type == "ocr_derived":
                score += int(system_record.source_mode in {"ocr", "hybrid"})
            elif score:
                score += int(system_record.source_mode == "native")
            if score and (best is None or score > best[0]):
                best = (score, system_record, basis)
        if best is not None:
            matches.append(
                EvidenceMatch(
                    gold_evidence_id=gold_record.evidence_id,
                    system_evidence_id=best[1].evidence_id,
                    match_basis=best[2],
                )
            )
    return tuple(matches)


def evidence_resolving_rate(evidence: EvidenceArtifact, chunks: ChunkArtifact) -> MetricResult:
    by_id = {record.evidence_id: record for record in evidence.records}
    references = [link.evidence_id for chunk in chunks.chunks for link in chunk.evidence_links]
    resolved = sum(
        reference in by_id and by_id[reference].document_version_id == chunks.document_version_id
        for reference in references
    )
    return MetricResult.ratio("evidence_resolving_rate", resolved, len(references))


def evidence_text_consistency(
    gold: Sequence[GoldEvidenceRecord],
    evidence: Sequence[EvidenceRecord],
    matches: Sequence[EvidenceMatch],
) -> MetricResult:
    gold_by_id = {record.evidence_id: record for record in gold}
    evidence_by_id = {record.evidence_id: record for record in evidence}
    consistent = 0
    for match in matches:
        gold_text = normalize_evidence_text(gold_by_id[match.gold_evidence_id].gold_text)
        system_text = normalize_evidence_text(evidence_by_id[match.system_evidence_id].text)
        consistent += gold_text in system_text
    return MetricResult.ratio("evidence_text_consistency", consistent, len(gold))


def chunk_evidence_coverage(
    gold: Sequence[GoldEvidenceRecord],
    chunks: Sequence[ChunkRecord],
) -> MetricResult:
    covered_gold = sum(
        any(
            normalize_evidence_text(record.gold_text) in normalize_evidence_text(chunk.text)
            for chunk in chunks
        )
        for record in gold
    )
    return MetricResult.ratio("chunk_evidence_coverage", covered_gold, len(gold))


def runtime_evidence_full_coverage(
    evidence: Sequence[EvidenceRecord], chunks: Sequence[ChunkRecord]
) -> MetricResult:
    evidence_by_id = {record.evidence_id: record for record in evidence}
    fully_covered = {
        link.evidence_id
        for chunk in chunks
        for link in chunk.evidence_links
        if link.evidence_id in evidence_by_id
        and link.evidence_char_start == 0
        and link.evidence_char_end == len(evidence_by_id[link.evidence_id].text)
    }
    return MetricResult.ratio(
        "runtime_evidence_full_coverage", len(fully_covered), len(evidence_by_id)
    )


def complete_semantic_unit_rate(
    gold: Sequence[GoldEvidenceRecord], chunks: Sequence[ChunkRecord]
) -> MetricResult:
    complete = sum(
        any(
            normalize_evidence_text(record.gold_text) in normalize_evidence_text(chunk.text)
            for chunk in chunks
        )
        for record in gold
    )
    return MetricResult.ratio("complete_semantic_unit_rate", complete, len(gold))


def cross_boundary_split_error_rate(
    gold: Sequence[GoldEvidenceRecord], chunks: Sequence[ChunkRecord]
) -> MetricResult:
    errors = sum(
        not any(
            normalize_evidence_text(record.gold_text) in normalize_evidence_text(chunk.text)
            for chunk in chunks
        )
        for record in gold
    )
    return MetricResult.ratio("cross_boundary_split_error_rate", errors, len(gold))


def chunk_redundancy_rate(
    chunks: Sequence[ChunkRecord],
    tokenize: Callable[[str], Sequence[int | str]],
) -> MetricResult:
    children = sorted(
        (chunk for chunk in chunks if chunk.kind == "child"),
        key=lambda chunk: (chunk.parent_chunk_id or "", chunk.ordinal),
    )
    duplicate = 0
    total = sum(len(tokenize(chunk.text)) for chunk in children)
    for first, second in zip(children, children[1:]):
        if first.parent_chunk_id != second.parent_chunk_id:
            continue
        duplicate += _suffix_prefix_overlap(tokenize(first.text), tokenize(second.text))
    return MetricResult.ratio("chunk_redundancy_rate", duplicate, total)


def parent_expansion_sufficiency(
    gold: Sequence[GoldEvidenceRecord], chunks: Sequence[ChunkRecord]
) -> MetricResult:
    parents = {chunk.chunk_id: chunk for chunk in chunks if chunk.kind == "parent"}
    children = [chunk for chunk in chunks if chunk.kind == "child"]
    required = [record for record in gold if record.requires_parent]
    sufficient = 0
    for record in required:
        required_texts = [record.gold_text, *record.necessary_neighbor_text]
        for child in children:
            if normalize_evidence_text(record.gold_text) not in normalize_evidence_text(child.text):
                continue
            parent = parents.get(child.parent_chunk_id or "")
            if parent is not None and all(
                normalize_evidence_text(text) in normalize_evidence_text(parent.text)
                for text in required_texts
            ):
                sufficient += 1
                break
    return MetricResult.ratio("parent_expansion_sufficiency", sufficient, len(required))


def page_bbox_consistency(
    gold: Sequence[GoldEvidenceRecord],
    evidence: Sequence[EvidenceRecord],
    matches: Sequence[EvidenceMatch],
) -> MetricResult:
    gold_by_id = {record.evidence_id: record for record in gold}
    evidence_by_id = {record.evidence_id: record for record in evidence}
    consistent = 0
    for match in matches:
        gold_pages = {bbox.page_number for bbox in gold_by_id[match.gold_evidence_id].bboxes}
        system_pages = {
            bbox.physical_page_index
            for bbox in evidence_by_id[match.system_evidence_id].page_bboxes
            if bbox.physical_page_index is not None
        }
        consistent += bool(gold_pages & system_pages)
    return MetricResult.ratio("page_bbox_consistency", consistent, len(gold))


def ocr_provenance_preservation(
    gold: Sequence[GoldEvidenceRecord],
    evidence: Sequence[EvidenceRecord],
    matches: Sequence[EvidenceMatch],
) -> MetricResult:
    gold_by_id = {record.evidence_id: record for record in gold}
    evidence_by_id = {record.evidence_id: record for record in evidence}
    ocr_matches = [
        match
        for match in matches
        if gold_by_id[match.gold_evidence_id].source_type == "ocr_derived"
    ]
    preserved = sum(
        evidence_by_id[match.system_evidence_id].source_mode in {"ocr", "hybrid"}
        and evidence_by_id[match.system_evidence_id].ocr is not None
        for match in ocr_matches
    )
    denominator = sum(record.source_type == "ocr_derived" for record in gold)
    return MetricResult.ratio("ocr_provenance_preservation", preserved, denominator)


def _suffix_prefix_overlap(first: Sequence[int | str], second: Sequence[int | str]) -> int:
    limit = min(len(first), len(second))
    for size in range(limit, 0, -1):
        if first[-size:] == second[:size]:
            return size
    return 0
