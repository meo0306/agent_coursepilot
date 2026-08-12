"""Deterministic cross-block security windows with reversible source mapping."""

from __future__ import annotations

from dataclasses import dataclass

from courserag.domain.document import ParsedDocumentIR, stable_ir_id
from courserag.security.detector import OffsetTokenizer, SecurityTextWindow, WindowSegment


@dataclass(frozen=True)
class SecurityWindowProfile:
    max_tokens: int = 512
    content_tokens: int = 448
    stride_tokens: int = 128

    def __post_init__(self) -> None:
        if self.max_tokens < 8:
            raise ValueError("security model max tokens is too small")
        if not 1 <= self.content_tokens <= self.max_tokens:
            raise ValueError("security content window must fit model maximum")
        if not 1 <= self.stride_tokens < self.content_tokens:
            raise ValueError("security stride must be smaller than content window")


@dataclass(frozen=True)
class _BlockSlice:
    page_index: int | None
    block_id: str
    document_start: int
    document_end: int


class SecurityWindowBuilder:
    def __init__(
        self, tokenizer: OffsetTokenizer, profile: SecurityWindowProfile | None = None
    ) -> None:
        self.tokenizer = tokenizer
        self.profile = profile or SecurityWindowProfile()

    def build(self, document: ParsedDocumentIR) -> tuple[SecurityTextWindow, ...]:
        text, blocks = _document_text(document)
        if not text:
            return ()
        offsets = tuple((start, end) for start, end in self.tokenizer.offsets(text) if end > start)
        if not offsets:
            return ()
        windows: list[SecurityTextWindow] = []
        start_token = 0
        while start_token < len(offsets):
            end_token = min(start_token + self.profile.content_tokens, len(offsets))
            char_start = offsets[start_token][0]
            char_end = offsets[end_token - 1][1]
            window_text = text[char_start:char_end]
            segments = _window_segments(blocks, char_start, char_end)
            if segments and window_text.strip():
                windows.append(
                    SecurityTextWindow(
                        window_id=stable_ir_id(
                            "secwin",
                            document.document_version_id,
                            self.tokenizer.tokenizer_id,
                            start_token,
                            end_token,
                            window_text,
                        ),
                        text=window_text,
                        token_start=start_token,
                        token_end=end_token,
                        segments=segments,
                    )
                )
            if end_token == len(offsets):
                break
            start_token += self.profile.content_tokens - self.profile.stride_tokens
        return tuple(windows)


def _document_text(document: ParsedDocumentIR) -> tuple[str, tuple[_BlockSlice, ...]]:
    parts: list[str] = []
    blocks: list[_BlockSlice] = []
    cursor = 0
    for page in document.pages:
        for block in page.blocks:
            if not block.text:
                continue
            if parts:
                separator = "\n"
                parts.append(separator)
                cursor += len(separator)
            start = cursor
            parts.append(block.text)
            cursor += len(block.text)
            blocks.append(
                _BlockSlice(
                    page_index=page.physical_page_index,
                    block_id=block.block_id,
                    document_start=start,
                    document_end=cursor,
                )
            )
    return "".join(parts), tuple(blocks)


def _window_segments(
    blocks: tuple[_BlockSlice, ...], char_start: int, char_end: int
) -> tuple[WindowSegment, ...]:
    segments: list[WindowSegment] = []
    for block in blocks:
        overlap_start = max(char_start, block.document_start)
        overlap_end = min(char_end, block.document_end)
        if overlap_end <= overlap_start:
            continue
        segments.append(
            WindowSegment(
                page_index=block.page_index,
                block_id=block.block_id,
                block_char_start=overlap_start - block.document_start,
                block_char_end=overlap_end - block.document_start,
                window_char_start=overlap_start - char_start,
                window_char_end=overlap_end - char_start,
            )
        )
    return tuple(segments)
