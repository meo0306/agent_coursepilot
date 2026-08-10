"""Build deterministic Section/Parent extraction Windows from stable Evidence."""

from __future__ import annotations

from dataclasses import dataclass

from courserag.chunking.tokenizer import TokenCounter
from courserag.domain.knowledge_point import (
    SectionWindow,
    WindowEvidence,
    WindowProfile,
    sha256_text,
    stable_window_id,
)


@dataclass(frozen=True)
class SectionSource:
    knowledge_base_id: str
    course_id: str
    section_id: str
    section_title: str | None
    evidence: tuple[WindowEvidence, ...]


class SectionWindowBuilder:
    def __init__(self, profile: WindowProfile, tokenizer: TokenCounter) -> None:
        self.profile = profile
        self.tokenizer = tokenizer

    def build(self, source: SectionSource) -> tuple[SectionWindow, ...]:
        if not source.evidence:
            return ()
        ordered = tuple(sorted(source.evidence, key=lambda item: item.ordinal))
        counts = tuple(max(1, self.tokenizer.count(item.text)) for item in ordered)
        if sum(counts) <= self.profile.max_tokens:
            return (self._window(source, 0, ordered),)

        windows: list[SectionWindow] = []
        start = 0
        while start < len(ordered):
            end = start
            token_count = 0
            while end < len(ordered):
                candidate_count = token_count + counts[end]
                if end > start and candidate_count > self.profile.max_tokens:
                    break
                token_count = candidate_count
                end += 1
                if token_count >= self.profile.min_tokens:
                    if end == len(ordered) or token_count + counts[end] > self.profile.max_tokens:
                        break
            if end == start:
                end = start + 1
            windows.append(self._window(source, len(windows), ordered[start:end]))
            if end >= len(ordered):
                break
            start = max(start + 1, end - self.profile.overlap_evidence_count)
        return tuple(windows)

    def _window(
        self,
        source: SectionSource,
        ordinal: int,
        evidence: tuple[WindowEvidence, ...],
    ) -> SectionWindow:
        text = "\n\n".join(item.text for item in evidence)
        token_count = max(1, self.tokenizer.count(text))
        warnings = ("OVERSIZED_EVIDENCE",) if token_count > self.profile.max_tokens else ()
        content_sha256 = sha256_text(text)
        evidence_ids = tuple(item.evidence_id for item in evidence)
        return SectionWindow(
            window_id=stable_window_id(
                source.knowledge_base_id,
                source.course_id,
                source.section_id,
                ordinal,
                evidence_ids,
                content_sha256,
                self.profile.profile_sha256,
            ),
            knowledge_base_id=source.knowledge_base_id,
            course_id=source.course_id,
            section_id=source.section_id,
            section_title=source.section_title,
            ordinal=ordinal,
            evidence=evidence,
            token_count=token_count,
            content_sha256=content_sha256,
            profile_sha256=self.profile.profile_sha256,
            warning_codes=warnings,
        )
