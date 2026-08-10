"""Non-destructive noise labels, continuation groups, and SectionIR construction."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

from courserag.domain.document import (
    BlockIR,
    PageIR,
    ParsedDocumentIR,
    SectionIR,
    SourceSpan,
    sha256_text,
    stable_ir_id,
)

_TERMINAL_PUNCTUATION = frozenset("。！？.!?；;：:")
_PAGE_NUMBER = re.compile(r"^(?:[-—– ]*)?(?:第\s*)?(?:[ivxlcdm]+|\d+)(?:\s*页)?(?:[-—– ]*)?$", re.I)
_NUMBERED_HEADING = re.compile(r"^(?P<number>\d+(?:\.\d+){0,8})[\s、.．]+\S")
_TOC_LINE = re.compile(r"^.{2,120}(?:\.{2,}|…{2,}|\s{2,})(?:\d+|[ivxlcdm]+)$", re.I)


def _normalized(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", text).casefold()
        if not character.isspace()
    )


def _font_size(block: BlockIR) -> float:
    sizes = [
        span.font_size for line in block.lines for span in line.spans if span.font_size is not None
    ]
    return max(sizes, default=0.0)


def _is_bold(block: BlockIR) -> bool:
    spans = [span for line in block.lines for span in line.spans if span.text.strip()]
    return bool(spans) and sum(span.bold for span in spans) / len(spans) >= 0.5


def _heading_level(block: BlockIR, body_font_size: float, toc_titles: set[str]) -> int | None:
    explicit = block.style.get("heading_level")
    if isinstance(explicit, int) and 1 <= explicit <= 12:
        return explicit
    text = block.text.strip()
    if not text or len(text) > 200 or block.block_type not in {"paragraph", "title", "heading"}:
        return None
    number_match = _NUMBERED_HEADING.match(text)
    if number_match is not None:
        return min(12, number_match.group("number").count(".") + 1)
    prominent = _font_size(block) >= max(1.0, body_font_size * 1.2) or _is_bold(block)
    if prominent and len(block.lines) <= 2:
        return 1
    if _normalized(text) in toc_titles and (_is_bold(block) or _font_size(block) > body_font_size):
        return 2
    return None


def _toc_candidates(document: ParsedDocumentIR) -> set[str]:
    candidates: set[str] = set()
    for page in document.pages:
        text = "\n".join(block.text for block in page.blocks)
        if "目录" not in text and "contents" not in text.casefold():
            continue
        for line in text.splitlines():
            stripped = line.strip()
            if not _TOC_LINE.match(stripped):
                continue
            title = re.sub(r"(?:\.{2,}|…{2,}|\s{2,})(?:\d+|[ivxlcdm]+)$", "", stripped, flags=re.I)
            if title:
                candidates.add(_normalized(title))
    return candidates


def _label_noise(document: ParsedDocumentIR) -> tuple[PageIR, ...]:
    page_count = len(document.pages)
    boundary_texts: Counter[str] = Counter()
    for page in document.pages:
        seen: set[str] = set()
        for block in page.blocks:
            if block.bbox is None or page.height is None:
                continue
            if block.bbox[1] <= page.height * 0.12 or block.bbox[3] >= page.height * 0.88:
                normalized = _normalized(block.text)
                if normalized:
                    seen.add(normalized)
        boundary_texts.update(seen)
    repeat_threshold = max(2, (page_count + 1) // 2)
    pages: list[PageIR] = []
    previous_last: BlockIR | None = None
    for page in document.pages:
        updated: list[BlockIR] = []
        for block in page.blocks:
            labels = list(block.noise_labels)
            normalized = _normalized(block.text)
            at_page_boundary = (
                block.bbox is not None
                and page.height is not None
                and (block.bbox[1] <= page.height * 0.12 or block.bbox[3] >= page.height * 0.88)
            )
            if _PAGE_NUMBER.fullmatch(block.text.strip()) and at_page_boundary:
                labels.append("page_number")
            if normalized and boundary_texts[normalized] >= repeat_threshold:
                labels.append("repeated_header_footer")
            updated.append(block.model_copy(update={"noise_labels": tuple(sorted(set(labels)))}))
        first_index = next(
            (
                index
                for index, block in enumerate(updated)
                if block.block_type == "paragraph" and block.text.strip() and not block.noise_labels
            ),
            None,
        )
        if previous_last is not None and first_index is not None:
            first = updated[first_index]
            if _continues(previous_last, first):
                updated[first_index] = first.model_copy(
                    update={"continuation_of_block_id": previous_last.block_id}
                )
        previous_last = next(
            (
                block
                for block in reversed(updated)
                if block.block_type == "paragraph" and block.text.strip() and not block.noise_labels
            ),
            None,
        )
        pages.append(page.model_copy(update={"blocks": tuple(updated)}))
    return tuple(pages)


def _continues(previous: BlockIR, current: BlockIR) -> bool:
    if previous.block_type != "paragraph" or current.block_type != "paragraph":
        return False
    if previous.noise_labels or current.noise_labels:
        return False
    if not previous.text.rstrip() or previous.text.rstrip()[-1] in _TERMINAL_PUNCTUATION:
        return False
    previous_size = _font_size(previous)
    current_size = _font_size(current)
    return not previous_size or not current_size or abs(previous_size - current_size) <= 0.5


def enrich_document_structure(document: ParsedDocumentIR) -> ParsedDocumentIR:
    pages = _label_noise(document)
    temporary = document.model_copy(update={"pages": pages})
    text_sizes = [
        _font_size(block)
        for page in pages
        for block in page.blocks
        if block.block_type == "paragraph" and _font_size(block) > 0
    ]
    body_size = sorted(text_sizes)[len(text_sizes) // 2] if text_sizes else 0.0
    toc_titles = _toc_candidates(temporary)
    stack: list[SectionIR] = []
    sections: list[SectionIR] = []
    current_blocks: list[str] = []
    current_index: int | None = None
    order_index = 0
    rebuilt_pages: list[PageIR] = []
    for page in pages:
        rebuilt_blocks: list[BlockIR] = []
        for block in page.blocks:
            level = _heading_level(block, body_size, toc_titles)
            if level is not None:
                if current_index is not None:
                    section = sections[current_index]
                    sections[current_index] = section.model_copy(
                        update={
                            "block_ids": tuple(current_blocks),
                            "content_sha256": sha256_text("\n".join(current_blocks)),
                        }
                    )
                current_blocks = [block.block_id]
                while stack and stack[-1].level >= level:
                    stack.pop()
                parent = stack[-1] if stack else None
                path = (
                    (*parent.section_path, block.text.strip()) if parent else (block.text.strip(),)
                )
                section_id = stable_ir_id(
                    "sec", document.document_version_id, order_index, block.block_id
                )
                section = SectionIR(
                    section_id=section_id,
                    parent_section_id=parent.section_id if parent else None,
                    level=level,
                    title=block.text.strip(),
                    section_path=path,
                    order_index=order_index,
                    block_ids=(block.block_id,),
                    source_span=SourceSpan(
                        document_id=document.document_id,
                        document_version_id=document.document_version_id,
                        page_start=block.source_span.page_start,
                        page_end=block.source_span.page_end,
                        block_start_id=block.block_id,
                        block_end_id=block.block_id,
                        source_unit="section-builder",
                    ),
                    content_sha256=sha256_text(block.block_id),
                )
                sections.append(section)
                stack.append(section)
                current_index = len(sections) - 1
                order_index += 1
                style = dict(block.style)
                style["heading_level"] = level
                block = block.model_copy(
                    update={
                        "block_type": "heading",
                        "style": style,
                        "confidence": block.confidence or 0.8,
                    }
                )
            elif current_index is not None:
                current_blocks.append(block.block_id)
            rebuilt_blocks.append(block)
        rebuilt_pages.append(page.model_copy(update={"blocks": tuple(rebuilt_blocks)}))
    if current_index is not None:
        section = sections[current_index]
        sections[current_index] = section.model_copy(
            update={
                "block_ids": tuple(current_blocks),
                "content_sha256": sha256_text("\n".join(current_blocks)),
            }
        )
    return document.model_copy(update={"pages": tuple(rebuilt_pages), "sections": tuple(sections)})
