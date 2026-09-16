"""Evidence-first parent-child chunking with semantic and sentence boundaries."""

from __future__ import annotations

import re
from dataclasses import dataclass

from courserag.chunking.tokenizer import TokenCounter
from courserag.domain.chunk import (
    ChunkArtifact,
    ChunkEvidenceLink,
    ChunkProfile,
    ChunkRecord,
    stable_chunk_id,
    stable_chunk_set_id,
)
from courserag.domain.document import sha256_text
from courserag.domain.evidence import EvidenceArtifact, EvidenceRecord

_SENTENCE_END = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+")


@dataclass(frozen=True)
class _Segment:
    evidence: EvidenceRecord
    start: int
    end: int
    warning_codes: tuple[str, ...] = ()

    @property
    def text(self) -> str:
        return self.evidence.text[self.start : self.end]


class ParentChildChunker:
    def __init__(self, profile: ChunkProfile, tokenizer: TokenCounter) -> None:
        if tokenizer.tokenizer_id != profile.tokenizer_id:
            raise ValueError("Tokenizer ID differs from Chunk Profile")
        if tokenizer.tokenizer_sha256 != profile.tokenizer_sha256:
            raise ValueError("Tokenizer hash differs from Chunk Profile")
        self.profile = profile
        self.tokenizer = tokenizer

    def build(self, evidence: EvidenceArtifact) -> ChunkArtifact:
        chunk_set_id = stable_chunk_set_id(
            evidence.document_version_id,
            evidence.chunk_identity_sha256,
            self.profile.profile_sha256,
        )
        parents: list[ChunkRecord] = []
        children: list[ChunkRecord] = []
        for parent_evidence in self._parent_groups(evidence.records):
            parent = self._make_parent(
                chunk_set_id,
                evidence.document_version_id,
                len(parents),
                parent_evidence,
            )
            parents.append(parent)
            child_segments = self._child_groups(parent_evidence)
            for segments in child_segments:
                children.append(
                    self._make_child(
                        chunk_set_id,
                        evidence.document_version_id,
                        len(children),
                        parent,
                        segments,
                    )
                )
        chunks = tuple([*parents, *children])
        warnings = tuple(sorted({code for chunk in chunks for code in chunk.warning_codes}))
        return ChunkArtifact(
            chunk_set_id=chunk_set_id,
            document_id=evidence.document_id,
            document_version_id=evidence.document_version_id,
            evidence_artifact_sha256=evidence.content_sha256,
            profile=self.profile,
            chunks=chunks,
            warning_codes=warnings,
        )

    def _parent_groups(
        self, records: tuple[EvidenceRecord, ...]
    ) -> list[tuple[EvidenceRecord, ...]]:
        groups: list[tuple[EvidenceRecord, ...]] = []
        current: list[EvidenceRecord] = []
        current_tokens = 0
        for record in records:
            tokens = self.tokenizer.count(record.text)
            section_changed = bool(current and record.section_id != current[0].section_id)
            exceeds = bool(current and current_tokens + tokens > self.profile.parent_target_tokens)
            if section_changed or exceeds:
                groups.append(tuple(current))
                current = []
                current_tokens = 0
            current.append(record)
            current_tokens += tokens
            if current_tokens >= self.profile.parent_max_tokens:
                groups.append(tuple(current))
                current = []
                current_tokens = 0
        if current:
            groups.append(tuple(current))
        return groups

    def _make_parent(
        self,
        chunk_set_id: str,
        document_version_id: str,
        ordinal: int,
        records: tuple[EvidenceRecord, ...],
    ) -> ChunkRecord:
        text = "\n\n".join(record.text for record in records)
        links = tuple(
            self._link(record, 0, len(record.text), ordinal=index)
            for index, record in enumerate(records)
        )
        warnings = set(code for record in records for code in record.warning_codes)
        token_count = self.tokenizer.count(text)
        if token_count > self.profile.parent_max_tokens:
            warnings.add("OVERSIZE_SEMANTIC_UNIT")
        content_hash = sha256_text(text)
        chunk_id = stable_chunk_id(chunk_set_id, "parent", None, links, content_hash)
        return ChunkRecord(
            chunk_id=chunk_id,
            chunk_set_id=chunk_set_id,
            document_version_id=document_version_id,
            section_id=records[0].section_id,
            kind="parent",
            ordinal=ordinal,
            text=text,
            content_sha256=content_hash,
            token_count=token_count,
            profile_sha256=self.profile.profile_sha256,
            evidence_links=links,
            warning_codes=tuple(sorted(warnings)),
        )

    def _child_groups(self, records: tuple[EvidenceRecord, ...]) -> list[tuple[_Segment, ...]]:
        segments = [segment for record in records for segment in self._segments(record)]
        groups: list[tuple[_Segment, ...]] = []
        current: list[_Segment] = []
        current_tokens = 0
        for segment in segments:
            tokens = self.tokenizer.count(segment.text)
            if current and current_tokens + tokens > self.profile.child_target_tokens:
                groups.append(tuple(current))
                overlap = current[-1]
                overlap_tokens = self.tokenizer.count(overlap.text)
                current = (
                    [overlap]
                    if overlap_tokens <= self.profile.child_overlap_tokens
                    and overlap_tokens + tokens <= self.profile.child_max_tokens
                    else []
                )
                current_tokens = sum(self.tokenizer.count(item.text) for item in current)
            current.append(segment)
            current_tokens += tokens
            if current_tokens >= self.profile.child_max_tokens:
                groups.append(tuple(current))
                current = []
                current_tokens = 0
        if current:
            groups.append(tuple(current))
        return groups

    def _segments(self, evidence: EvidenceRecord) -> tuple[_Segment, ...]:
        if self.tokenizer.count(evidence.text) <= self.profile.child_max_tokens:
            return (_Segment(evidence, 0, len(evidence.text)),)
        sentence_ranges = self._sentence_ranges(evidence.text)
        segments: list[_Segment] = []
        for start, end in sentence_ranges:
            text = evidence.text[start:end]
            spans = self.tokenizer.token_spans(text)
            if len(spans) <= self.profile.child_max_tokens:
                segments.append(_Segment(evidence, start, end))
                continue
            for offset in range(0, len(spans), self.profile.child_max_tokens):
                window = spans[offset : offset + self.profile.child_max_tokens]
                local_start = window[0][0]
                local_end = window[-1][1]
                segments.append(
                    _Segment(
                        evidence,
                        start + local_start,
                        start + local_end,
                        ("ATOMIC_TOKEN_SPLIT",),
                    )
                )
        return tuple(segments)

    @staticmethod
    def _sentence_ranges(text: str) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        cursor = 0
        for match in _SENTENCE_END.finditer(text):
            end = match.end()
            if end > cursor:
                ranges.append((cursor, end))
            cursor = end
        if cursor < len(text):
            ranges.append((cursor, len(text)))
        return [(start, end) for start, end in ranges if text[start:end].strip()]

    def _make_child(
        self,
        chunk_set_id: str,
        document_version_id: str,
        ordinal: int,
        parent: ChunkRecord,
        segments: tuple[_Segment, ...],
    ) -> ChunkRecord:
        text = "\n\n".join(segment.text for segment in segments)
        ranges: dict[str, tuple[EvidenceRecord, int, int]] = {}
        order: list[str] = []
        for segment in segments:
            evidence_id = segment.evidence.evidence_id
            if evidence_id not in ranges:
                ranges[evidence_id] = (segment.evidence, segment.start, segment.end)
                order.append(evidence_id)
            else:
                record, start, end = ranges[evidence_id]
                ranges[evidence_id] = (record, min(start, segment.start), max(end, segment.end))
        links = tuple(
            self._link(*ranges[evidence_id], ordinal=index)
            for index, evidence_id in enumerate(order)
        )
        warnings = {
            code
            for segment in segments
            for code in (*segment.evidence.warning_codes, *segment.warning_codes)
        }
        token_count = self.tokenizer.count(text)
        if token_count > self.profile.child_max_tokens:
            warnings.add("OVERSIZE_SEMANTIC_UNIT")
        content_hash = sha256_text(text)
        chunk_id = stable_chunk_id(chunk_set_id, "child", parent.chunk_id, links, content_hash)
        return ChunkRecord(
            chunk_id=chunk_id,
            chunk_set_id=chunk_set_id,
            document_version_id=document_version_id,
            section_id=parent.section_id,
            kind="child",
            parent_chunk_id=parent.chunk_id,
            ordinal=ordinal,
            text=text,
            content_sha256=content_hash,
            token_count=token_count,
            profile_sha256=self.profile.profile_sha256,
            evidence_links=links,
            warning_codes=tuple(sorted(warnings)),
        )

    @staticmethod
    def _link(evidence: EvidenceRecord, start: int, end: int, *, ordinal: int) -> ChunkEvidenceLink:
        return ChunkEvidenceLink(
            evidence_id=evidence.evidence_id,
            ordinal=ordinal,
            evidence_char_start=start,
            evidence_char_end=end,
            coverage_sha256=sha256_text(evidence.text[start:end]),
        )
