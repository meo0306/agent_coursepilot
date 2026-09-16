"""Deterministic semantic Evidence construction over the Canonical Document IR."""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import JsonValue

from courserag.domain.document import BlockIR, PageIR, ParsedDocumentIR, SectionIR, sha256_text
from courserag.domain.evidence import (
    EvidenceArtifact,
    EvidenceOCRProvenance,
    EvidenceRecord,
    EvidenceSourceMode,
    EvidenceSourceUnit,
    EvidenceType,
    PageBBox,
    normalize_evidence_text,
    stable_evidence_id,
)

_NON_BODY_TYPES = {"header", "footer", "page_number", "page_break", "section_break", "figure"}
_NON_BODY_ROLES = {"header", "footer", "page_number", "qr", "qr_text", "embedded_image_text"}
_DEFINITION_MARKERS = ("是指", "定义为", "称为", "means", "defined as")
_EXAMPLE_MARKERS = ("例如", "比如", "举例", "example")
_STEP_MARKERS = ("步骤", "第一步", "第二步", "首先", "其次", "最后")
_TERMINAL_PUNCTUATION = frozenset("。！？!?；;.")


@dataclass(frozen=True)
class EvidenceBuilderProfile:
    name: str = "semantic_units_v1"
    low_confidence_threshold: float = 0.75

    @property
    def sha256(self) -> str:
        return sha256_text(
            f"{self.name}\nlow_confidence_threshold={self.low_confidence_threshold:.6f}"
        )


@dataclass(frozen=True)
class _LocatedBlock:
    block: BlockIR
    page: PageIR
    section: SectionIR | None


class EvidenceBuilder:
    def __init__(self, profile: EvidenceBuilderProfile | None = None) -> None:
        self.profile = profile or EvidenceBuilderProfile()

    def build(self, document: ParsedDocumentIR) -> EvidenceArtifact:
        located = self._located_body_blocks(document)
        groups = self._semantic_groups(located)
        records = [self._make_record(document, group) for group in groups]
        records = self._deduplicate(records)
        linked = self._add_adjacency(records)
        return EvidenceArtifact(
            document_id=document.document_id,
            document_version_id=document.document_version_id,
            parsed_document_sha256=self._semantic_document_sha256(document),
            builder_profile=self.profile.name,
            builder_profile_sha256=self.profile.sha256,
            records=tuple(linked),
            warning_codes=tuple(
                sorted({code for record in linked for code in record.warning_codes})
            ),
        )

    @staticmethod
    def _semantic_document_sha256(document: ParsedDocumentIR) -> str:
        identity = document.metadata.get("prompt_injection_profile")
        if isinstance(identity, dict):
            source_sha256 = identity.get("input_content_sha256")
            if (
                isinstance(source_sha256, str)
                and len(source_sha256) == 64
                and all(character in "0123456789abcdef" for character in source_sha256)
            ):
                return source_sha256
        return document.content_sha256

    def _located_body_blocks(self, document: ParsedDocumentIR) -> list[_LocatedBlock]:
        section_by_block = {
            block_id: section for section in document.sections for block_id in section.block_ids
        }
        located: list[_LocatedBlock] = []
        for page in document.pages:
            for block in sorted(page.blocks, key=lambda item: item.order_index):
                role = str(block.style.get("content_role", block.style.get("role", ""))).casefold()
                ocr_boundary_noise = (
                    str(block.style.get("content_source", "")).casefold() == "ocr"
                    and block.bbox is not None
                    and page.height is not None
                    and (block.bbox[1] <= page.height * 0.12 or block.bbox[3] >= page.height * 0.90)
                )
                if (
                    block.block_type in _NON_BODY_TYPES
                    or role in _NON_BODY_ROLES
                    or ocr_boundary_noise
                    or block.noise_labels
                    or not block.text.strip()
                ):
                    continue
                located.append(
                    _LocatedBlock(
                        block=block, page=page, section=section_by_block.get(block.block_id)
                    )
                )
        return located

    def _semantic_groups(self, blocks: list[_LocatedBlock]) -> list[tuple[_LocatedBlock, ...]]:
        groups: list[tuple[_LocatedBlock, ...]] = []
        index = 0
        while index < len(blocks):
            current = blocks[index]
            block = current.block
            if block.block_type in {"heading", "title"} and index + 1 < len(blocks):
                following: list[_LocatedBlock] = [current]
                cursor = index + 1
                while cursor < len(blocks):
                    candidate = blocks[cursor]
                    if candidate.section != current.section:
                        break
                    allowed = {"list_item", "table", "formula"}
                    if not self._ends_semantic_unit(following[-1].block.text):
                        allowed.add("paragraph")
                    if candidate.block.block_type not in allowed:
                        break
                    following.append(candidate)
                    cursor += 1
                    if sum(len(item.block.text) for item in following) >= 2000:
                        break
                if len(following) > 1:
                    groups.append(tuple(following))
                    index = cursor
                    continue
            if block.block_type == "paragraph":
                following = [current]
                cursor = index + 1
                while not self._ends_semantic_unit(following[-1].block.text) and cursor < len(
                    blocks
                ):
                    candidate = blocks[cursor]
                    if (
                        candidate.section != current.section
                        or candidate.block.block_type != "paragraph"
                    ):
                        break
                    following.append(candidate)
                    cursor += 1
                    if sum(len(item.block.text) for item in following) >= 2000:
                        break
                groups.append(tuple(following))
                index = cursor
                continue
            if block.block_type == "list_item":
                following = [current]
                cursor = index + 1
                while cursor < len(blocks):
                    candidate = blocks[cursor]
                    if (
                        candidate.section != current.section
                        or candidate.block.block_type != "list_item"
                    ):
                        break
                    following.append(candidate)
                    cursor += 1
                groups.append(tuple(following))
                index = cursor
                continue
            if block.block_type in {"table", "formula"} and groups:
                previous = groups[-1]
                if (
                    len(previous) == 1
                    and previous[0].section == current.section
                    and previous[0].block.block_type == "paragraph"
                    and len(previous[0].block.text) <= 300
                ):
                    groups[-1] = (*previous, current)
                    index += 1
                    continue
            groups.append((current,))
            index += 1
        return groups

    @staticmethod
    def _ends_semantic_unit(text: str) -> bool:
        stripped = text.rstrip()
        return bool(stripped and stripped[-1] in _TERMINAL_PUNCTUATION)

    def _make_record(
        self, document: ParsedDocumentIR, group: tuple[_LocatedBlock, ...]
    ) -> EvidenceRecord:
        texts = [item.block.text.strip() for item in group]
        text = "\n\n".join(texts)
        content_sha256 = sha256_text(text)
        units = tuple(
            EvidenceSourceUnit(
                block_id=item.block.block_id,
                block_type=item.block.block_type,
                ordinal=ordinal,
                char_start=0,
                char_end=len(item.block.text),
                text=item.block.text,
                text_sha256=item.block.content_sha256,
            )
            for ordinal, item in enumerate(group)
        )
        source_mode = self._source_mode(group)
        confidences = [item.block.confidence for item in group if item.block.confidence is not None]
        confidence = min(confidences) if confidences else None
        warning_codes: set[str] = set()
        for item in group:
            style_warnings = item.block.style.get("warning_codes", [])
            if isinstance(style_warnings, list):
                warning_codes.update(str(code) for code in style_warnings)
        if confidence is not None and confidence < self.profile.low_confidence_threshold:
            warning_codes.add("LOW_SOURCE_CONFIDENCE")
        if any(self._uses_coarse_docx_page_bbox(item) for item in group):
            warning_codes.add("COARSE_DOCX_PAGE_BBOX")
        ocr = self._ocr_provenance(group, confidence, warning_codes)
        return EvidenceRecord(
            evidence_id=stable_evidence_id(document.document_version_id, units, content_sha256),
            document_id=document.document_id,
            document_version_id=document.document_version_id,
            section_id=group[0].section.section_id if group[0].section is not None else None,
            section_path=group[0].section.section_path if group[0].section is not None else (),
            evidence_type=self._evidence_type(group),
            source_mode=source_mode,
            text=text,
            content_sha256=content_sha256,
            normalized_sha256=sha256_text(normalize_evidence_text(text)),
            source_units=units,
            page_bboxes=tuple(self._page_bbox(item) for item in group if self._has_page_bbox(item)),
            confidence=confidence,
            ocr=ocr,
            warning_codes=tuple(sorted(warning_codes)),
        )

    @staticmethod
    def _source_mode(group: tuple[_LocatedBlock, ...]) -> EvidenceSourceMode:
        sources = {
            str(item.block.style.get("content_source", "native")).casefold() for item in group
        }
        if sources == {"ocr"}:
            return "ocr"
        if "ocr" in sources:
            return "hybrid"
        return "native"

    @staticmethod
    def _style_string(style: dict[str, JsonValue], key: str, default: str) -> str:
        value = style.get(key)
        return value if isinstance(value, str) and value else default

    def _ocr_provenance(
        self,
        group: tuple[_LocatedBlock, ...],
        confidence: float | None,
        warning_codes: set[str],
    ) -> EvidenceOCRProvenance | None:
        if self._source_mode(group) == "native":
            return None
        styles = [item.block.style for item in group]
        return EvidenceOCRProvenance(
            engine=self._style_string(styles[0], "engine", "unknown"),
            model_name=self._style_string(styles[0], "model_name", "unknown"),
            profile_sha256=self._style_string(styles[0], "profile_sha256", "0" * 64),
            image_sha256=self._style_string(styles[0], "image_sha256", "0" * 64),
            confidence=confidence if confidence is not None else 0.0,
            warning_codes=tuple(sorted(warning_codes)),
        )

    @staticmethod
    def _uses_coarse_docx_page_bbox(item: _LocatedBlock) -> bool:
        anchor = item.block.page_anchor
        return bool(
            item.block.bbox is None
            and anchor is not None
            and anchor.page_width is not None
            and anchor.page_height is not None
        )

    @classmethod
    def _has_page_bbox(cls, item: _LocatedBlock) -> bool:
        precise = (
            item.block.bbox is not None
            and item.page.width is not None
            and item.page.height is not None
        )
        return precise or cls._uses_coarse_docx_page_bbox(item)

    @classmethod
    def _page_bbox(cls, item: _LocatedBlock) -> PageBBox:
        anchor = item.block.page_anchor
        if cls._uses_coarse_docx_page_bbox(item):
            assert anchor is not None
            assert anchor.page_width is not None
            assert anchor.page_height is not None
            bbox = (0.0, 0.0, anchor.page_width, anchor.page_height)
            page_width = anchor.page_width
            page_height = anchor.page_height
            coordinate_space = "docx_rendered_pdf_points_top_left"
        else:
            assert item.block.bbox is not None
            assert item.page.width is not None
            assert item.page.height is not None
            bbox = item.block.bbox
            page_width = item.page.width
            page_height = item.page.height
            coordinate_space = (
                "docx_rendered_pdf_points_top_left" if anchor is not None else "pdf_points_top_left"
            )
        return PageBBox(
            page_id=item.page.page_id,
            physical_page_index=(
                anchor.physical_page_index if anchor is not None else item.page.physical_page_index
            ),
            display_page_label=(
                anchor.display_page_label if anchor is not None else item.page.display_page_label
            ),
            bbox=bbox,
            coordinate_space=coordinate_space,
            page_width=page_width,
            page_height=page_height,
            source_region_id=(
                str(item.block.style.get("ocr_region_id"))
                if item.block.style.get("ocr_region_id") is not None
                else None
            ),
        )

    @staticmethod
    def _evidence_type(group: tuple[_LocatedBlock, ...]) -> EvidenceType:
        block_types = {item.block.block_type for item in group}
        text = " ".join(item.block.text for item in group).casefold()
        if "table" in block_types:
            return "table"
        if "formula" in block_types:
            return "formula"
        if block_types == {"list_item"} or "list_item" in block_types:
            return "steps" if any(marker in text for marker in _STEP_MARKERS) else "list"
        if any(marker in text for marker in _DEFINITION_MARKERS):
            return "definition"
        if any(marker in text for marker in _EXAMPLE_MARKERS):
            return "example"
        if block_types <= {"paragraph", "heading", "title"}:
            return "paragraph"
        return "other"

    @staticmethod
    def _deduplicate(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        seen: set[tuple[str | None, str]] = set()
        deduplicated: list[EvidenceRecord] = []
        for record in records:
            key = (record.section_id, record.normalized_sha256)
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(record)
        return deduplicated

    @staticmethod
    def _add_adjacency(records: list[EvidenceRecord]) -> list[EvidenceRecord]:
        linked: list[EvidenceRecord] = []
        for index, record in enumerate(records):
            previous = records[index - 1] if index > 0 else None
            following = records[index + 1] if index + 1 < len(records) else None
            linked.append(
                record.model_copy(
                    update={
                        "previous_evidence_id": (
                            previous.evidence_id
                            if previous is not None and previous.section_id == record.section_id
                            else None
                        ),
                        "next_evidence_id": (
                            following.evidence_id
                            if following is not None and following.section_id == record.section_id
                            else None
                        ),
                    }
                )
            )
        return linked
