from __future__ import annotations

from courserag.domain.knowledge_point import WindowEvidence, WindowProfile, sha256_text
from courserag.knowledge_points.windows import SectionSource, SectionWindowBuilder


class CharacterTokenizer:
    tokenizer_id = "test-character-v1"
    tokenizer_sha256 = "c" * 64

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))

    def token_ids(self, text: str) -> tuple[int | str, ...]:
        return tuple(text)

    def count(self, text: str) -> int:
        return len(text)


def evidence(index: int, text: str | None = None) -> WindowEvidence:
    value = text or f"知识点证据{index}" * 4
    return WindowEvidence(
        evidence_id=f"ev1_{index:064x}",
        text=value,
        content_sha256=sha256_text(value),
        ordinal=index,
    )


def windows(*items: WindowEvidence, maximum: int = 80, minimum: int = 40):
    profile = WindowProfile(
        name="test",
        version="v1",
        tokenizer_id="test-character-v1",
        tokenizer_sha256="c" * 64,
        min_tokens=minimum,
        max_tokens=maximum,
    )
    return SectionWindowBuilder(profile, CharacterTokenizer()).build(
        SectionSource(
            knowledge_base_id="kb-1",
            course_id="course-1",
            section_id="section-1",
            section_title="第一节",
            evidence=tuple(items),
        )
    )
