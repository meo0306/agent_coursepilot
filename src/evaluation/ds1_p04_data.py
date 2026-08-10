"""Build the source-grounded P04 DS1 Candidate and its offline review pack.

This module deliberately reads owner source files and fixed rendered snapshots directly. It never
imports or consumes the P04 structured Parser output, and it never promotes Candidate records to
Approved Gold.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import unicodedata
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz
from docx import Document
from docx.table import Table as DocxTable
from docx.table import _Cell
from docx.text.paragraph import Paragraph
from PIL import Image, ImageDraw

from courserag.evals.schemas import (
    DocxPaginationGold,
    DocxRenderProfile,
    DS0CorpusDataset,
    DS1CandidateManifest,
    DS1ParsingDataset,
    DS1ReviewDecisions,
    P04InputWorkPackage,
    PageGold,
    PageRegion,
    ParsingGoldRecord,
    SectionGold,
    TableGold,
    TablePageFragment,
)
from courserag.parsers.pagination import RendererProfile, canonicalize_pdf
from evaluation.contracts import HashedArtifact, ReviewStatus, SourceSpan
from evaluation.corpus_fixtures import sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_json, atomic_write_text

DATASET_ROOT = Path("datasets/courserag_eval/v1")
APPROVED_DS0 = DATASET_ROOT / "approved/ds0/pilot.json"
APPROVED_WORK_PACKAGE = DATASET_ROOT / "approved/work_packages/p04_input.json"
REVIEW_DECISIONS_R3 = DATASET_ROOT / "reviews/ds1_p04_review_decisions_r3.json"
R3_CANDIDATE = DATASET_ROOT / "candidates/ds1/p04_native_docx_r3.json"
R3_CANDIDATE_SHA256 = "abbaf5114408990783dd209c3189e5ecfa4332a00aaab8b0e02ec892bdce1ac3"
R3_REVIEW_SOURCE_FILENAME = "ds1_p04_review_decisions_abbaf5114408.json"
R3_REVIEW_SOURCE_SHA256 = "0b38ca0e699acc3063a69b27fc530688585e1dc0ab5c32693a0376dd26d2f28e"
REVIEW_DECISIONS_R4 = DATASET_ROOT / "reviews/ds1_p04_review_decisions_r4.json"
R4_CANDIDATE = DATASET_ROOT / "candidates/ds1/p04_native_docx_r4.json"
R4_CANDIDATE_SHA256 = "8fd5fbefbcbe40c90f65c35cd3e0166cb6d62800e4927e4ed7c6cb1c661973cb"
TABLE_020_RECORD_ID = "ds1-table-docx-020"
RENDERER_PROFILE = Path("resources/renderers/libreoffice_headless_v1/profile.json")
RENDERER_FONT_LOCK = Path("resources/renderers/libreoffice_headless_v1/fonts.lock.json")
PDF_PRIMARY = Path("data/sample_files/人工智能通识教程.pdf")
DOCX_PRIMARY = Path("data/sample_files/教材-人工智能：从算法到系统.docx")
PRIMARY_RENDER_RUNS = (
    Path("storage_eval/p04_primary_render/run1/教材-人工智能：从算法到系统.pdf"),
    Path("storage_eval/p04_primary_render/run2/教材-人工智能：从算法到系统.pdf"),
)
STRESS_RENDER_RUNS = (
    Path(
        "storage_eval/courserag_corpus/v1/docx_qa_render_r3/"
        "doc_ai_algorithms_systems_structure_stress.pdf"
    ),
    Path(
        "storage_eval/courserag_corpus/v1/docx_qa_render_r4/"
        "doc_ai_algorithms_systems_structure_stress.pdf"
    ),
)
PDF_QA_DIR = Path("storage_eval/pre_p04/pdf_qa")
POPPLER_BBOX_DIR = Path("storage_eval/ds1_p04_poppler_bbox")
WORD_CROSSCHECK_PDF = Path(
    "storage_eval/ds1_p04_word_crosscheck/doc_ai_algorithms_systems_word2021.pdf"
)
WORD_ANCHOR_FIRST_MATCH_PAGES = {
    "1.1.1 类人行为智能：图灵测试法": 4,
    "2.2 感知机与多层感知机": 2,
    "3.5.3 注意力机制和Transformer": 90,
    "5.3 大模型的微调与对齐": 2,
    "9.7 全面融入人类生活的大模型技术": 3,
}

PDF_COMPLEX_LAYOUT_PAGES = {5, 10, 15, 20, 27, 31}
SECOND_REVIEW_SECTION_SELECTIONS = {
    "p04-section-pdf-1.1.1",
    "p04-section-pdf-1.3.4",
    "p04-section-docx-2.2",
    "p04-section-docx-3.5.3",
    "p04-section-docx-9.7",
}
HEADING_NUMBER = re.compile(r"^(?P<number>\d+(?:\.\d+)+)(?:\s|\u3000|$)")
VISIBLE_PAGE_LABEL = re.compile(r"^(?:[ivxlcdm]+|\d+)$", re.IGNORECASE)
LIST_PREFIX = re.compile(r"^(?:[（(]?\d+[）).]|[①②③④⑤⑥⑦⑧⑨⑩]|[一二三四五六七八九十]+、)")


@dataclass(frozen=True)
class SourceBlock:
    page_number: int
    block_number: int
    bbox: tuple[float, float, float, float]
    text: str
    block_type: Literal["text", "image"]

    @property
    def source_id(self) -> str:
        return f"poppler:p{self.page_number:03d}:b{self.block_number:04d}"


def _bbox4(values: Sequence[float | str]) -> tuple[float, float, float, float]:
    if len(values) != 4:
        raise ValueError(f"expected four BBox coordinates, received {len(values)}")
    return (
        round(float(values[0]), 4),
        round(float(values[1]), 4),
        round(float(values[2]), 4),
        round(float(values[3]), 4),
    )


@dataclass(frozen=True)
class RenderPair:
    document_id: str
    run_paths: tuple[Path, Path]
    raw_sha256: tuple[str, str]
    canonical_pdf_sha256: str
    canonical_pdf: bytes
    page_count: int


def _normalize(text: str) -> str:
    value = unicodedata.normalize("NFKC", text).casefold()
    return "".join(character for character in value if not character.isspace())


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json_sha256(value: object) -> str:
    content = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha256_bytes(content.encode("utf-8"))


def _relative(repository_root: Path, path: Path) -> str:
    resolved = path.resolve()
    root = repository_root.resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"path is outside the repository: {resolved}")
    return resolved.relative_to(root).as_posix()


def _artifact(repository_root: Path, path: Path, media_type: str) -> HashedArtifact:
    resolved = (repository_root / path).resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root):
        raise FileNotFoundError(path)
    return HashedArtifact(
        path=_relative(repository_root, resolved),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type=media_type,
    )


def _load_inputs(repository_root: Path) -> tuple[DS0CorpusDataset, P04InputWorkPackage]:
    approved_ds0 = DS0CorpusDataset.model_validate_json(
        (repository_root / APPROVED_DS0).read_text(encoding="utf-8")
    )
    work_package = P04InputWorkPackage.model_validate_json(
        (repository_root / APPROVED_WORK_PACKAGE).read_text(encoding="utf-8")
    )
    if any(
        document.review_status is not ReviewStatus.APPROVED for document in approved_ds0.documents
    ):
        raise ValueError("formal DS1 Candidate requires six Approved DS0 documents")
    if (
        work_package.review_status is not ReviewStatus.APPROVED
        or work_package.approval_scope != "p04_input_selection_only"
        or work_package.gold_status != "no_ds1_gold"
    ):
        raise ValueError("formal DS1 Candidate requires the exact Approved P04 input package")
    if len(work_package.native_pdf_pages) != 15 or len(work_package.docx_pagination_anchors) != 10:
        raise ValueError("Approved P04 input package has unexpected fixed counts")
    for document in approved_ds0.documents:
        if document.repository_relative_path is None:
            raise ValueError(f"DS0 document has no repository path: {document.document_id}")
        path = (repository_root / document.repository_relative_path).resolve()
        if sha256_file(path) != document.sha256:
            raise ValueError(f"DS0 source Hash changed: {document.document_id}")
    return approved_ds0, work_package


def _document_versions(approved_ds0: DS0CorpusDataset) -> dict[str, tuple[str, str]]:
    return {
        document.document_id: (document.document_version, document.sha256)
        for document in approved_ds0.documents
    }


def _verify_render_pair(
    repository_root: Path,
    *,
    document_id: str,
    run_paths: tuple[Path, Path],
    expected_page_count: int,
) -> RenderPair:
    resolved = tuple((repository_root / path).resolve() for path in run_paths)
    if any(not path.is_file() for path in resolved):
        raise FileNotFoundError(f"fixed Renderer runs are missing for {document_id}")
    raw = tuple(path.read_bytes() for path in resolved)
    canonical = tuple(canonicalize_pdf(content) for content in raw)
    canonical_hashes = tuple(_sha256_bytes(content) for content in canonical)
    if canonical_hashes[0] != canonical_hashes[1]:
        raise ValueError(f"canonical Renderer PDF is not repeatable for {document_id}")
    with fitz.open(stream=canonical[0], filetype="pdf") as document:
        page_count = len(document)
    if page_count != expected_page_count:
        raise ValueError(f"fixed Renderer page count changed for {document_id}: {page_count}")
    return RenderPair(
        document_id=document_id,
        run_paths=run_paths,
        raw_sha256=(_sha256_bytes(raw[0]), _sha256_bytes(raw[1])),
        canonical_pdf_sha256=canonical_hashes[0],
        canonical_pdf=canonical[0],
        page_count=page_count,
    )


def _source_blocks(page: fitz.Page, page_number: int) -> list[SourceBlock]:
    values = page.get_text("dict", sort=False)
    result: list[SourceBlock] = []
    for fallback_number, block in enumerate(values.get("blocks", [])):
        block_number = int(block.get("number", fallback_number))
        bbox = _bbox4(block["bbox"])
        if int(block.get("type", 0)) == 1:
            result.append(SourceBlock(page_number, block_number, bbox, "", "image"))
            continue
        lines: list[str] = []
        for line in block.get("lines", []):
            text = "".join(str(span.get("text", "")) for span in line.get("spans", []))
            if text.strip():
                lines.append(text.rstrip())
        text = "\n".join(lines).strip()
        if text:
            result.append(SourceBlock(page_number, block_number, bbox, text, "text"))
    return result


def _join_poppler_words(words: list[str]) -> str:
    result = ""
    for word in words:
        if not word:
            continue
        if (
            result
            and result[-1].isascii()
            and word[0].isascii()
            and result[-1].isalnum()
            and word[0].isalnum()
        ):
            result += " "
        result += word
    return result


def _poppler_page(
    repository_root: Path, page_number: int
) -> tuple[float, float, list[SourceBlock]]:
    path = repository_root / POPPLER_BBOX_DIR / f"page-{page_number:03d}.html"
    if not path.is_file():
        raise FileNotFoundError(f"independent Poppler BBox source is missing: {path}")
    root = ET.fromstring(path.read_text(encoding="utf-8"))
    namespace = {"x": "http://www.w3.org/1999/xhtml"}
    page = root.find(".//x:page", namespace)
    if page is None:
        raise ValueError(f"Poppler BBox output has no page element: {path}")
    width = round(float(page.attrib["width"]), 4)
    height = round(float(page.attrib["height"]), 4)
    blocks: list[SourceBlock] = []
    for block_number, block in enumerate(page.findall(".//x:block", namespace)):
        lines: list[str] = []
        for line in block.findall("./x:line", namespace):
            words = [word.text or "" for word in line.findall("./x:word", namespace)]
            text = _join_poppler_words(words).strip()
            if text:
                lines.append(text)
        text = "\n".join(lines).strip()
        if not text:
            continue
        bbox = _bbox4([block.attrib[name] for name in ("xMin", "yMin", "xMax", "yMax")])
        blocks.append(SourceBlock(page_number, block_number, bbox, text, "text"))
    return width, height, blocks


def _intersection_ratio(
    left: tuple[float, float, float, float], right: tuple[float, float, float, float]
) -> float:
    width = max(0.0, min(left[2], right[2]) - max(left[0], right[0]))
    height = max(0.0, min(left[3], right[3]) - max(left[1], right[1]))
    intersection = width * height
    area = max(0.0, left[2] - left[0]) * max(0.0, left[3] - left[1])
    return intersection / area if area else 0.0


def _region_kind(
    block: SourceBlock,
    *,
    page_height: float,
) -> tuple[str, bool]:
    x0, y0, x1, y1 = block.bbox
    del x0, x1
    stripped = " ".join(block.text.split())
    if y1 <= page_height * 0.085:
        return "header", True
    if y0 >= page_height * 0.92:
        if VISIBLE_PAGE_LABEL.fullmatch(stripped):
            return "page_number", True
        return "footer", True
    if block.block_type == "image":
        return "figure", False
    if HEADING_NUMBER.match(stripped):
        return "title", False
    if LIST_PREFIX.match(stripped):
        return "list", False
    return "body", False


def _reading_order(regions: list[PageRegion], *, page_number: int, page_width: float) -> list[str]:
    with_bbox = [region for region in regions if region.bbox is not None]

    def bbox(region: PageRegion) -> tuple[float, float, float, float]:
        if region.bbox is None:  # pragma: no cover - guarded by with_bbox
            raise ValueError("reading-order Region has no BBox")
        return region.bbox

    if page_number == 5:
        title_band = [region for region in with_bbox if bbox(region)[1] < 210]
        columns = [region for region in with_bbox if region not in title_band]
        left = [region for region in columns if bbox(region)[0] < page_width / 2]
        right = [region for region in columns if region not in left]
        ordered = (
            sorted(title_band, key=lambda region: (bbox(region)[1], bbox(region)[0]))
            + sorted(left, key=lambda region: (bbox(region)[1], bbox(region)[0]))
            + sorted(right, key=lambda region: (bbox(region)[1], bbox(region)[0]))
        )
    else:
        ordered = sorted(with_bbox, key=lambda region: (bbox(region)[1], bbox(region)[0]))
    return [region.region_id for region in ordered]


def _native_pdf_pages(
    repository_root: Path,
    work_package: P04InputWorkPackage,
    versions: dict[str, tuple[str, str]],
) -> tuple[list[PageGold], dict[int, tuple[float, float, float, float]]]:
    path = repository_root / PDF_PRIMARY
    document_version, _ = versions["doc_ai_general_education_excerpt"]
    records: list[PageGold] = []
    table_bboxes: dict[int, tuple[float, float, float, float]] = {}
    with fitz.open(path) as document:
        for selection in work_package.native_pdf_pages:
            page_number = selection.page_number
            page = document[page_number - 1]
            page_width, page_height, source_blocks = _poppler_page(repository_root, page_number)
            image_blocks = [
                SourceBlock(
                    page_number,
                    10_000 + block.block_number,
                    block.bbox,
                    "",
                    "image",
                )
                for block in _source_blocks(page, page_number)
                if block.block_type == "image"
            ]
            source_blocks.extend(image_blocks)
            table_bbox: tuple[float, float, float, float] | None = None
            if page_number == 20:
                tables = page.find_tables().tables
                if len(tables) != 1:
                    raise ValueError("PDF page 20 must contain exactly one source table")
                table_bbox = _bbox4(tables[0].bbox)
                table_bboxes[page_number] = table_bbox
            regions: list[PageRegion] = []
            noise_regions: list[PageRegion] = []
            sequence = 0
            for block in source_blocks:
                if table_bbox is not None and _intersection_ratio(block.bbox, table_bbox) > 0.5:
                    continue
                kind, noise = _region_kind(block, page_height=page_height)
                region = PageRegion(
                    region_id=f"pdf-p{page_number:03d}-r{sequence:03d}",
                    region_type=kind,
                    text=block.text or None,
                    bbox=block.bbox,
                    block_id=block.source_id,
                )
                sequence += 1
                (noise_regions if noise else regions).append(region)
            if page_number == 5 and not any(
                region.region_type == "page_number" for region in noise_regions
            ):
                noise_regions.append(
                    PageRegion(
                        region_id="pdf-p005-visual-page-number",
                        region_type="page_number",
                        text="001",
                        bbox=(260.0, 724.0, 281.0, 742.0),
                        block_id="visual:p005:page-number",
                    )
                )
            if table_bbox is not None:
                regions.append(
                    PageRegion(
                        region_id=f"pdf-p{page_number:03d}-table-000",
                        region_type="table",
                        text="表1-1 部分职业的被淘汰概率",
                        bbox=table_bbox,
                        block_id="pdf:p020:table:000",
                    )
                )
            reading_order = _reading_order(
                regions,
                page_number=page_number,
                page_width=page_width,
            )
            order_by_id = {region_id: index for index, region_id in enumerate(reading_order)}
            regions = [
                region.model_copy(update={"order_index": order_by_id.get(region.region_id)})
                for region in regions
            ]
            records.append(
                PageGold(
                    record_id=f"ds1-page-pdf-{page_number:03d}",
                    candidate_source="source_grounded_assisted",
                    document_id="doc_ai_general_education_excerpt",
                    document_version=document_version,
                    page_number=page_number,
                    page_type=(
                        "complex_layout"
                        if page_number in PDF_COMPLEX_LAYOUT_PAGES
                        else "native_text"
                    ),
                    needs_ocr=False,
                    page_width=page_width,
                    page_height=page_height,
                    bbox_coordinate_space="pdf_points_top_left",
                    reading_order=reading_order,
                    noise_types=sorted({region.region_type for region in noise_regions}),
                    regions=regions,
                    noise_regions=noise_regions,
                )
            )
    return records, table_bboxes


def _section_path(number: str) -> list[str]:
    parts = number.split(".")
    return [".".join(parts[:index]) for index in range(1, len(parts) + 1)]


def _section_id(document_id: str, number: str) -> str:
    return f"gold-sec-{document_id.replace('_', '-')}-{number.replace('.', '-')}"


def _parent_section_id(document_id: str, number: str) -> str | None:
    parts = number.split(".")
    if len(parts) <= 1:
        return None
    return _section_id(document_id, ".".join(parts[:-1]))


def _last_nonempty_paragraph(paragraphs: Sequence[Paragraph], start: int, end: int) -> int:
    for index in range(end, start - 1, -1):
        text = paragraphs[index].text.strip()
        if text:
            return index
    return start


def _docx_sections(
    repository_root: Path,
    work_package: P04InputWorkPackage,
    versions: dict[str, tuple[str, str]],
) -> list[SectionGold]:
    path = repository_root / DOCX_PRIMARY
    document = Document(str(path))
    paragraphs = list(document.paragraphs)
    document_id = "doc_ai_algorithms_systems"
    document_version, document_sha256 = versions[document_id]
    result: list[SectionGold] = []
    selections = [
        selection for selection in work_package.sections if selection.document_id == document_id
    ]
    for selection in selections:
        if selection.source_paragraph_index is None:
            raise ValueError(f"DOCX Section has no paragraph index: {selection.selection_id}")
        start = selection.source_paragraph_index
        actual_title = paragraphs[start].text.strip()
        if actual_title != selection.source_title:
            raise ValueError(f"DOCX Section source title changed: {selection.selection_id}")
        level = len(selection.section_anchor.split("."))
        boundary = len(paragraphs)
        for index in range(start + 1, len(paragraphs)):
            text = paragraphs[index].text.strip()
            match = HEADING_NUMBER.match(text)
            if match is None:
                continue
            candidate_level = len(match.group("number").split("."))
            style_name = str(getattr(paragraphs[index].style, "name", ""))
            if candidate_level <= level and (style_name.startswith("Heading") or len(text) <= 160):
                boundary = index
                break
        end = _last_nonempty_paragraph(paragraphs, start, boundary - 1)
        last_text = paragraphs[end].text.strip()
        if len(last_text) > 4000:
            raise ValueError(
                f"DOCX Section final paragraph exceeds Gold limit: {selection.selection_id}"
            )
        result.append(
            SectionGold(
                record_id=f"ds1-section-docx-{selection.section_anchor.replace('.', '-')}",
                candidate_source="source_grounded_assisted",
                document_id=document_id,
                document_version=document_version,
                section_id=_section_id(document_id, selection.section_anchor),
                title=selection.source_title,
                level=level,
                parent_section_id=_parent_section_id(document_id, selection.section_anchor),
                source_span=SourceSpan(
                    document_id=document_id,
                    document_version=document_version,
                    document_sha256=document_sha256,
                    section_path=_section_path(selection.section_anchor),
                    block_start=f"paragraph:{start}",
                    block_end=f"paragraph:{end}",
                ),
                first_text=selection.source_title,
                last_text=last_text,
            )
        )
    return result


def _semantic_pdf_blocks(repository_root: Path, document: fitz.Document) -> list[SourceBlock]:
    result: list[SourceBlock] = []
    for page_number, page in enumerate(document, start=1):
        _, page_height, blocks = _poppler_page(repository_root, page_number)
        for block in blocks:
            if block.bbox[1] < page_height * 0.085:
                continue
            if block.bbox[1] > page_height * 0.92:
                continue
            result.append(block)
    return result


def _find_pdf_section_start(blocks: list[SourceBlock], *, number: str, title: str) -> int:
    normalized_number = _normalize(number)
    normalized_title = _normalize(title)
    for index, block in enumerate(blocks):
        if block.page_number < 10:
            continue
        block_text = _normalize(block.text)
        following = _normalize("".join(item.text for item in blocks[index : index + 3]))
        if normalized_number in block_text and normalized_title in following:
            return index
    raise ValueError(f"PDF Section title is not present in the owner source: {title}")


def _pdf_sections(
    repository_root: Path,
    work_package: P04InputWorkPackage,
    versions: dict[str, tuple[str, str]],
) -> list[SectionGold]:
    document_id = "doc_ai_general_education_excerpt"
    document_version, document_sha256 = versions[document_id]
    result: list[SectionGold] = []
    with fitz.open(repository_root / PDF_PRIMARY) as document:
        blocks = _semantic_pdf_blocks(repository_root, document)
        selections = [
            selection for selection in work_package.sections if selection.document_id == document_id
        ]
        for selection in selections:
            start = _find_pdf_section_start(
                blocks,
                number=selection.section_anchor,
                title=selection.source_title,
            )
            level = len(selection.section_anchor.split("."))
            boundary = len(blocks)
            for index in range(start + 1, len(blocks)):
                match = HEADING_NUMBER.match(" ".join(blocks[index].text.split()))
                if match is None:
                    continue
                number = match.group("number")
                if number == selection.section_anchor:
                    continue
                if len(number.split(".")) <= level:
                    boundary = index
                    break
            end = max(start, boundary - 1)
            result.append(
                SectionGold(
                    record_id=f"ds1-section-pdf-{selection.section_anchor.replace('.', '-')}",
                    candidate_source="source_grounded_assisted",
                    document_id=document_id,
                    document_version=document_version,
                    section_id=_section_id(document_id, selection.section_anchor),
                    title=selection.source_title,
                    level=level,
                    parent_section_id=_parent_section_id(document_id, selection.section_anchor),
                    source_span=SourceSpan(
                        document_id=document_id,
                        document_version=document_version,
                        document_sha256=document_sha256,
                        section_path=_section_path(selection.section_anchor),
                        page_start=blocks[start].page_number,
                        page_end=blocks[end].page_number,
                        block_start=blocks[start].source_id,
                        block_end=blocks[end].source_id,
                    ),
                    first_text=selection.source_title,
                    last_text=blocks[end].text,
                )
            )
    return result


def _cell_text(cell: _Cell) -> str:
    return "\n".join(paragraph.text.rstrip() for paragraph in cell.paragraphs).strip()


def _docx_table_grid(table: DocxTable) -> list[list[str]]:
    rows = list(table.rows)
    column_count = max((len(row.cells) for row in rows), default=0)
    if not rows or column_count == 0:
        raise ValueError("Gold table cannot be empty")
    seen_cells: set[object] = set()
    grid: list[list[str]] = []
    for row in rows:
        values: list[str] = []
        for cell in row.cells:
            cell_key = cell._tc
            values.append("" if cell_key in seen_cells else _cell_text(cell))
            seen_cells.add(cell_key)
        values.extend([""] * (column_count - len(values)))
        grid.append(values)
    return grid


def _table_020_visible_grid(
    render_pair: RenderPair,
    source_ooxml_grid: list[list[str]],
) -> tuple[list[list[str]], list[TablePageFragment]]:
    if len(source_ooxml_grid) != 6 or any(len(row) != 4 for row in source_ooxml_grid):
        raise ValueError("DOCX table 20 logical source grid must remain 6x4")
    first_fragment = [["种类", "中型卡车", "小轿车", "人员"]]
    second_fragment = [
        ["距离", "6.8m*2.7m", "4.3m*1.5m", "1.7m*0.5m"],
        *source_ooxml_grid[1:],
    ]
    for column_index in range(4):
        source_lines = source_ooxml_grid[0][column_index].splitlines()
        rendered_lines = [first_fragment[0][column_index], second_fragment[0][column_index]]
        if source_lines != rendered_lines:
            raise ValueError("DOCX table 20 header fragments differ from the OOXML cell paragraphs")
    with fitz.open(stream=render_pair.canonical_pdf, filetype="pdf") as rendered:
        page_text = {
            547: rendered[546].get_text(),
            548: rendered[547].get_text(),
        }
    for page_number, rows in ((547, first_fragment), (548, second_fragment)):
        normalized_page = _normalize(page_text[page_number])
        for row in rows:
            for value in row:
                if value and _normalize(value) not in normalized_page:
                    raise ValueError(
                        f"DOCX table 20 rendered fragment text is missing on page {page_number}: "
                        f"{value}"
                    )
    visible_grid = [*first_fragment, *second_fragment]
    if len(visible_grid) != 7 or any(len(row) != 4 for row in visible_grid):
        raise ValueError("DOCX table 20 rendered-visible Gold grid must be 7x4")
    return (
        visible_grid,
        [
            TablePageFragment(
                physical_page_index=547,
                row_indices=[0],
                visible_cells=first_fragment,
                continuation_to_next_page=True,
            ),
            TablePageFragment(
                physical_page_index=548,
                row_indices=list(range(1, 7)),
                visible_cells=second_fragment,
                continuation_from_previous_page=True,
            ),
        ],
    )


def _table_records(
    repository_root: Path,
    work_package: P04InputWorkPackage,
    versions: dict[str, tuple[str, str]],
    primary_render_pair: RenderPair,
) -> list[TableGold]:
    result: list[TableGold] = []
    document_id = "doc_ai_algorithms_systems"
    document_version, document_sha256 = versions[document_id]
    source = Document(str(repository_root / DOCX_PRIMARY))
    for selection in work_package.tables:
        if selection.document_id != document_id:
            continue
        if selection.source_table_index is None:
            raise ValueError(f"DOCX Table has no source index: {selection.selection_id}")
        index = selection.source_table_index
        source_ooxml_grid = _docx_table_grid(source.tables[index])
        if index == 20:
            grid, fragments = _table_020_visible_grid(primary_render_pair, source_ooxml_grid)
        else:
            grid, fragments = source_ooxml_grid, []
        result.append(
            TableGold(
                record_id=f"ds1-table-docx-{index:03d}",
                candidate_source="source_grounded_assisted",
                table_id=f"gold-table-{document_id.replace('_', '-')}-{index:03d}",
                source_span=SourceSpan(
                    document_id=document_id,
                    document_version=document_version,
                    document_sha256=document_sha256,
                    section_path=[selection.source_anchor_text],
                    page_start=547 if index == 20 else None,
                    page_end=548 if index == 20 else None,
                    block_start=f"table:{index}",
                    block_end=f"table:{index}",
                ),
                row_count=len(grid),
                column_count=len(grid[0]),
                cells=grid,
                rendered_page_fragments=fragments,
            )
        )
    pdf_id = "doc_ai_general_education_excerpt"
    pdf_version, pdf_sha256 = versions[pdf_id]
    with fitz.open(repository_root / PDF_PRIMARY) as document:
        tables = document[19].find_tables().tables
        if len(tables) != 1:
            raise ValueError("PDF Page 20 must contain exactly one source table")
        extracted = tables[0].extract()
        grid = [["" if value is None else str(value) for value in row] for row in extracted]
    result.append(
        TableGold(
            record_id="ds1-table-pdf-020-000",
            candidate_source="source_grounded_assisted",
            table_id="gold-table-doc-ai-general-education-excerpt-020-000",
            source_span=SourceSpan(
                document_id=pdf_id,
                document_version=pdf_version,
                document_sha256=pdf_sha256,
                section_path=["1.2.2"],
                page_start=20,
                page_end=20,
                block_start="pdf:p020:table:000",
                block_end="pdf:p020:table:000",
            ),
            row_count=len(grid),
            column_count=len(grid[0]),
            cells=grid,
        )
    )
    return result


def _pages_containing(document: fitz.Document, text: str) -> list[int]:
    expected = _normalize(text)
    return [
        index
        for index, page in enumerate(document, start=1)
        if expected in _normalize(page.get_text("text"))
    ]


def _visible_page_label(page: fitz.Page) -> str | None:
    height = float(page.rect.height)
    candidates: list[tuple[float, str]] = []
    for block in page.get_text("blocks", sort=False):
        text = " ".join(str(block[4]).split())
        if not VISIBLE_PAGE_LABEL.fullmatch(text):
            continue
        y0, y1 = float(block[1]), float(block[3])
        if y0 >= height * 0.88 or y1 <= height * 0.12:
            candidates.append((max(y0, height - y1), text))
    return min(candidates, default=(0.0, None), key=lambda item: item[0])[1]


def _pagination_records(
    work_package: P04InputWorkPackage,
    versions: dict[str, tuple[str, str]],
    renderer_profile: DocxRenderProfile,
    render_pairs: dict[str, RenderPair],
) -> list[DocxPaginationGold]:
    result: list[DocxPaginationGold] = []
    opened = {
        document_id: fitz.open(stream=pair.canonical_pdf, filetype="pdf")
        for document_id, pair in render_pairs.items()
    }
    try:
        for anchor in work_package.docx_pagination_anchors:
            document_id = anchor.document_id
            document_version, _ = versions[document_id]
            document = opened[document_id]
            matches = _pages_containing(document, anchor.source_text)
            if not matches:
                raise ValueError(f"DOCX anchor is absent from the fixed PDF: {anchor.selection_id}")
            physical_page = max(matches)
            page = document[physical_page - 1]
            display_label = _visible_page_label(page)
            section_page_index = (
                int(display_label)
                if display_label is not None and display_label.isdigit()
                else None
            )
            source_unit_id = anchor.mapped_source_unit
            result.append(
                DocxPaginationGold(
                    record_id=f"ds1-pagination-{anchor.selection_id.removeprefix('p04-docx-anchor-')}",
                    candidate_source="source_grounded_assisted",
                    document_id=document_id,
                    document_version=document_version,
                    render_profile=renderer_profile,
                    section_path=_section_path(anchor.section_anchor),
                    block_id=source_unit_id,
                    source_unit_id=source_unit_id,
                    source_text=anchor.source_text,
                    source_text_sha256=anchor.source_text_sha256,
                    paragraph_index=anchor.source_paragraph_index,
                    char_start=0,
                    char_end=len(anchor.source_text),
                    expected_physical_page_index=physical_page,
                    expected_display_page_label=display_label,
                    expected_section_page_index=section_page_index,
                    rendered_pdf_sha256=render_pairs[document_id].canonical_pdf_sha256,
                    rendered_pdf_hash_basis="canonical_pdf_without_volatile_metadata",
                )
            )
    finally:
        for document in opened.values():
            document.close()
    return result


def _copy_pdf_review_images(
    repository_root: Path, review_assets: Path, pages: list[PageGold]
) -> dict[str, str]:
    result: dict[str, str] = {}
    review_assets.mkdir(parents=True, exist_ok=True)
    for record in pages:
        source = repository_root / PDF_QA_DIR / f"page-{record.page_number:02d}.png"
        if not source.is_file():
            raise FileNotFoundError(f"Poppler review image is missing: {source}")
        destination = review_assets / f"{record.record_id}.png"
        shutil.copy2(source, destination)
        result[record.record_id] = f"assets/{destination.name}"
    return result


def _render_anchor_images(
    review_assets: Path,
    pagination_records: list[DocxPaginationGold],
    render_pairs: dict[str, RenderPair],
) -> dict[str, str]:
    result: dict[str, str] = {}
    opened = {
        document_id: fitz.open(stream=pair.canonical_pdf, filetype="pdf")
        for document_id, pair in render_pairs.items()
    }
    try:
        for record in pagination_records:
            page = opened[record.document_id][record.expected_physical_page_index - 1]
            pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            destination = review_assets / f"{record.record_id}.png"
            pixmap.save(destination)
            result[record.record_id] = f"assets/{destination.name}"
    finally:
        for document in opened.values():
            document.close()
    return result


def _render_table_fragment_images(
    review_assets: Path,
    table_records: list[TableGold],
    primary_render_pair: RenderPair,
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    with fitz.open(stream=primary_render_pair.canonical_pdf, filetype="pdf") as rendered:
        for record in table_records:
            if not record.rendered_page_fragments:
                continue
            paths: list[str] = []
            for fragment in record.rendered_page_fragments:
                page = rendered[fragment.physical_page_index - 1]
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                destination = review_assets / (
                    f"{record.record_id}-page-{fragment.physical_page_index}.png"
                )
                pixmap.save(destination)
                paths.append(f"assets/{destination.name}")
            result[record.record_id] = paths
    return result


def _contact_sheet(paths: list[Path], destination: Path) -> None:
    thumbnails: list[Image.Image] = []
    for path in paths:
        image = Image.open(path).convert("RGB")
        image.thumbnail((320, 420))
        thumbnails.append(image.copy())
        image.close()
    columns = 2
    rows = (len(thumbnails) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * 340, rows * 455), "#e5e7eb")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(thumbnails):
        x = (index % columns) * 340 + 10
        y = (index // columns) * 455 + 25
        sheet.paste(image, (x, y))
        draw.text((x, 5 + (index // columns) * 455), paths[index].stem, fill="#111827")
    sheet.save(destination)


def _page_overlay_previews(
    *,
    review_dir: Path,
    page_records: list[PageGold],
    page_images: dict[str, str],
) -> None:
    overlay_paths: list[Path] = []
    for record in page_records:
        source = review_dir / page_images[record.record_id]
        image = Image.open(source).convert("RGB")
        draw = ImageDraw.Draw(image)
        scale_x = image.width / float(record.page_width or image.width)
        scale_y = image.height / float(record.page_height or image.height)
        for region, color in [
            *((region, "#2563eb") for region in record.regions),
            *((region, "#dc2626") for region in record.noise_regions),
        ]:
            if region.bbox is None:
                continue
            x0, y0, x1, y1 = region.bbox
            draw.rectangle(
                (x0 * scale_x, y0 * scale_y, x1 * scale_x, y1 * scale_y),
                outline=color,
                width=2,
            )
        destination = source.with_name(f"{source.stem}-overlay.png")
        image.save(destination)
        image.close()
        overlay_paths.append(destination)
    _contact_sheet(overlay_paths, review_dir / "assets/pdf_page_overlay_contact_sheet.png")


def _record_details(record: ParsingGoldRecord) -> str:
    values = record.model_dump(mode="json")
    return html.escape(json.dumps(values, ensure_ascii=False, indent=2, sort_keys=True))


def _page_card(record: PageGold, image_path: str) -> str:
    overlays: list[str] = []
    for region in [*record.regions, *record.noise_regions]:
        if region.bbox is None:
            continue
        x0, y0, x1, y1 = region.bbox
        css_class = "noise" if region in record.noise_regions else "content"
        label = html.escape(f"{region.region_id} · {region.region_type}")
        overlays.append(
            f'<rect class="overlay {css_class}" x="{x0}" y="{y0}" '
            f'width="{x1 - x0}" height="{y1 - y0}"><title>{label}</title></rect>'
        )
    return f"""
    <article class="card" data-type="page" id="{record.record_id}">
      <header><h2>{record.record_id}</h2><span>PDF PageGold · physical {record.page_number}</span></header>
      <label class="review"><input type="checkbox" data-review="{record.record_id}"> 已核对</label>
      <div class="page-wrap">
        <img src="{image_path}" alt="PDF physical page {record.page_number}">
        <svg viewBox="0 0 {record.page_width} {record.page_height}" preserveAspectRatio="none">
          {"".join(overlays)}
        </svg>
      </div>
      <p><b>page_type</b>: {record.page_type} · <b>needs_ocr</b>: false · <b>reading regions</b>: {len(record.reading_order)} · <b>noise</b>: {", ".join(record.noise_types) or "none"}</p>
      <details><summary>完整 Candidate JSON</summary><pre>{_record_details(record)}</pre></details>
    </article>"""


def _pagination_card(record: DocxPaginationGold, image_path: str) -> str:
    label = record.expected_display_page_label or "null"
    section_page = record.expected_section_page_index or "null"
    return f"""
    <article class="card" data-type="docx_pagination" id="{record.record_id}">
      <header><h2>{record.record_id}</h2><span>DOCX PaginationGold</span></header>
      <label class="review"><input type="checkbox" data-review="{record.record_id}"> 已核对</label>
      <img class="anchor-page" src="{image_path}" alt="fixed Renderer anchor page">
      <blockquote>{html.escape(record.source_text or "")}</blockquote>
      <p><b>document</b>: {record.document_id}<br><b>source unit</b>: {record.source_unit_id}<br><b>physical page</b>: {record.expected_physical_page_index}<br><b>display label</b>: {label}<br><b>section page</b>: {section_page}</p>
      <details><summary>完整 Candidate JSON</summary><pre>{_record_details(record)}</pre></details>
    </article>"""


def _section_card(record: SectionGold) -> str:
    return f"""
    <article class="card" data-type="section" id="{record.record_id}">
      <header><h2>{record.record_id}</h2><span>SectionGold · level {record.level}</span></header>
      <label class="review"><input type="checkbox" data-review="{record.record_id}"> 已核对</label>
      <h3>{html.escape(record.title)}</h3>
      <p><b>parent</b>: {record.parent_section_id or "null"}<br><b>span</b>: {html.escape(str(record.source_span.block_start))} → {html.escape(str(record.source_span.block_end))}<br><b>pages</b>: {record.source_span.page_start or "DOCX structural"} → {record.source_span.page_end or "DOCX structural"}</p>
      <p><b>first</b>: {html.escape(record.first_text or "")}</p>
      <p><b>last</b>: {html.escape(record.last_text or "")}</p>
      <details><summary>完整 Candidate JSON</summary><pre>{_record_details(record)}</pre></details>
    </article>"""


def _table_card(
    record: TableGold,
    fragment_images: list[str],
    *,
    requires_rereview: bool,
) -> str:
    rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in record.cells
    )
    source_ooxml_cells = (
        [
            [f"{record.cells[0][index]}\n{record.cells[1][index]}" for index in range(4)],
            *record.cells[2:],
        ]
        if record.record_id == TABLE_020_RECORD_ID
        else []
    )
    source_rows = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
        for row in source_ooxml_cells
    )
    fragment_cards: list[str] = []
    for fragment, image_path in zip(
        record.rendered_page_fragments,
        fragment_images,
        strict=True,
    ):
        visible_rows = "".join(
            "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>"
            for row in fragment.visible_cells
        )
        fragment_cards.append(
            f'<section class="fragment"><h4>物理页 {fragment.physical_page_index} · '
            f'Gold 行 {fragment.row_indices}</h4><img class="anchor-page" src="{image_path}" '
            f'alt="table fragment page {fragment.physical_page_index}">'
            f'<div class="table-scroll"><table>{visible_rows}</table></div></section>'
        )
    css_class = "card wide rereview" if requires_rereview else "card wide"
    rereview_note = (
        '<p class="rereview-note"><b>必须重新审核：</b>r4 错把 6×4 OOXML 源结构当成最终 '
        "Gold；按两页可见边框和 course_owner 反馈，最终 Gold 应为 7×4。</p>"
        if requires_rereview
        else ""
    )
    source_grid = (
        f"<h4>源 OOXML 网格 · {len(source_ooxml_cells)}×"
        f'{record.column_count}</h4><div class="table-scroll"><table>{source_rows}</table></div>'
        if source_ooxml_cells
        else ""
    )
    return f"""
    <article class="{css_class}" data-type="table" id="{record.record_id}">
      <header><h2>{record.record_id}</h2><span>TableGold · {record.row_count}×{record.column_count}</span></header>
      <label class="review"><input type="checkbox" data-review="{record.record_id}"> 已核对</label>
      {rereview_note}
      {"".join(fragment_cards)}
      <h4>最终可见 TableGold 网格</h4>
      <div class="table-scroll"><table>{rows}</table></div>
      {source_grid}
      <details><summary>完整 Candidate JSON</summary><pre>{_record_details(record)}</pre></details>
    </article>"""


def _review_html(
    *,
    candidate_sha256: str,
    records: list[ParsingGoldRecord],
    page_images: dict[str, str],
    anchor_images: dict[str, str],
    table_fragment_images: dict[str, list[str]],
    pre_reviewed_record_ids: set[str],
    required_rereview_record_ids: list[str],
    word_crosscheck_status: str,
) -> str:
    cards: list[str] = []
    for record in records:
        if isinstance(record, PageGold):
            cards.append(_page_card(record, page_images[record.record_id]))
        elif isinstance(record, DocxPaginationGold):
            cards.append(_pagination_card(record, anchor_images[record.record_id]))
        elif isinstance(record, SectionGold):
            cards.append(_section_card(record))
        elif isinstance(record, TableGold):
            cards.append(
                _table_card(
                    record,
                    table_fragment_images.get(record.record_id, []),
                    requires_rereview=record.record_id in required_rereview_record_ids,
                )
            )
        else:  # pragma: no cover - union guarded by Pydantic
            raise TypeError(type(record))
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>P04 DS1 Candidate Review</title>
<style>
:root{{--ink:#111827;--muted:#6b7280;--blue:#2563eb;--red:#dc2626;--paper:#fff;--bg:#f3f4f6}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 system-ui,"Microsoft YaHei",sans-serif}}
.top{{position:sticky;top:0;z-index:5;background:#111827;color:white;padding:14px 22px;box-shadow:0 2px 8px #0004}}
.top h1{{font-size:20px;margin:0 0 6px}} .top code{{font-size:12px;word-break:break-all}}
.controls{{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}} button{{padding:7px 12px;border:0;border-radius:6px;cursor:pointer}}
main{{max-width:1500px;margin:20px auto;padding:0 18px}} .notice{{background:#fff7ed;border-left:5px solid #f97316;padding:12px 16px;margin-bottom:18px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(390px,1fr));gap:18px}}
.card{{position:relative;background:var(--paper);border-radius:10px;padding:16px;box-shadow:0 1px 5px #0002}}
.card.wide{{grid-column:1/-1}} .card header{{display:flex;justify-content:space-between;gap:12px;border-bottom:1px solid #e5e7eb;margin-bottom:12px}}
.card h2{{font-size:16px;margin:0 0 8px}} .card header span{{color:var(--muted);font-size:13px}}
.review{{position:absolute;right:16px;top:48px;background:#ecfdf5;padding:4px 8px;border-radius:5px}}
.page-wrap{{position:relative;width:100%;max-width:620px;margin:auto}} .page-wrap img{{display:block;width:100%;height:auto}}
.page-wrap svg{{position:absolute;inset:0;width:100%;height:100%}} .overlay{{fill:transparent;stroke-width:1.2;vector-effect:non-scaling-stroke}}
.overlay.content{{stroke:var(--blue)}} .overlay.noise{{stroke:var(--red);stroke-dasharray:4 3}}
.anchor-page{{display:block;max-width:100%;max-height:740px;margin:auto;border:1px solid #d1d5db}}
blockquote{{border-left:4px solid var(--blue);margin:12px 0;padding:8px 12px;background:#eff6ff}}
pre{{white-space:pre-wrap;word-break:break-word;background:#111827;color:#e5e7eb;padding:12px;border-radius:6px;max-height:420px;overflow:auto}}
.table-scroll{{overflow:auto}} table{{border-collapse:collapse;width:100%;font-size:13px}} td{{border:1px solid #9ca3af;padding:6px;vertical-align:top;white-space:pre-wrap}}
.rereview{{outline:4px solid #dc2626}} .rereview-note{{background:#fef2f2;border-left:5px solid #dc2626;padding:10px 12px}}
.fragment{{border:1px solid #d1d5db;border-radius:8px;padding:10px;margin:12px 0}} .fragment h4{{margin:0 0 8px}}
.hidden{{display:none!important}} .done{{outline:3px solid #16a34a}}
</style></head><body>
<section class="top"><h1>P04 正式 DS1 Candidate · 55 条</h1><code>Candidate SHA-256: {candidate_sha256}</code>
<div class="controls"><button data-filter="all">全部</button><button data-filter="page">15 Page</button><button data-filter="docx_pagination">10 Pagination</button><button data-filter="section">20 Section</button><button data-filter="table">10 Table</button><button id="export">导出审核勾选</button></div></section>
<main><div class="notice"><b>审批边界：</b>本页只展示 Candidate。Word 2021 交叉检查状态：{html.escape(word_crosscheck_status)}。正式分页仅绑定 LibreOffice 7.4.7.2；OCR Gold 不在本批。蓝框是课程内容候选区域，红色虚线是噪声区域。页面坐标与阅读顺序必须由 course_owner 核对。</div>
<div class="grid">{"".join(cards)}</div></main>
<script>
const sha={json.dumps(candidate_sha256)}; const key='ds1-p04-review-'+sha;
const priorReviewed=new Set({json.dumps(sorted(pre_reviewed_record_ids), ensure_ascii=False)});
let state=JSON.parse(localStorage.getItem(key)||'{{}}');
document.querySelectorAll('[data-review]').forEach(box=>{{if(state[box.dataset.review]===undefined&&priorReviewed.has(box.dataset.review))state[box.dataset.review]=true;box.checked=!!state[box.dataset.review];box.closest('.card').classList.toggle('done',box.checked);box.onchange=()=>{{state[box.dataset.review]=box.checked;localStorage.setItem(key,JSON.stringify(state));box.closest('.card').classList.toggle('done',box.checked)}}}});
document.querySelectorAll('[data-filter]').forEach(button=>button.onclick=()=>{{const type=button.dataset.filter;document.querySelectorAll('.card').forEach(card=>card.classList.toggle('hidden',type!=='all'&&card.dataset.type!==type))}});
document.getElementById('export').onclick=()=>{{const payload={{schema_version:'courserag.ds1-review-decisions.v1',candidate_file_sha256:sha,reviewed_record_ids:Object.keys(state).filter(id=>state[id]),record_count:55}};const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='ds1_p04_review_decisions_'+sha.slice(0,12)+'.json';a.click();URL.revokeObjectURL(a.href)}};
</script></body></html>"""


def _validate_review_pack(review_dir: Path) -> int:
    index_path = review_dir / "index.html"
    content = index_path.read_text(encoding="utf-8")
    if len(re.findall(r'<article class="card[^\"]*"', content)) != 55:
        raise ValueError("offline review pack must contain exactly 55 record cards")
    references = re.findall(r'(?:src|href)="([^"]+)"', content)
    local_assets: set[Path] = set()
    for reference in references:
        if reference.startswith(("http://", "https://", "//", "data:")):
            raise ValueError(f"offline review pack contains an external resource: {reference}")
        target = (review_dir / reference).resolve()
        if not target.is_relative_to(review_dir.resolve()) or not target.is_file():
            raise ValueError(f"offline review resource is missing or unsafe: {reference}")
        local_assets.add(target)
    if not local_assets:
        raise ValueError("offline review pack contains no source images")
    return len(local_assets)


def _word_crosscheck(repository_root: Path) -> dict[str, str | int | bool | None]:
    path = repository_root / WORD_CROSSCHECK_PDF
    if not path.is_file():
        return {
            "status": "anchor_presence_verified_full_pdf_unavailable",
            "reason": (
                "Word 2021 Find returned all five selected anchors; full PDF export was unavailable, "
                "and no Word page fact is used as Gold"
            ),
            "pdf_sha256": None,
            "page_count": None,
            "anchor_presence_count": len(WORD_ANCHOR_FIRST_MATCH_PAGES),
        }
    with fitz.open(path) as document:
        return {
            "status": "available_for_visual_crosscheck_only",
            "reason": "Word output is not used for pagination Gold",
            "pdf_sha256": sha256_file(path),
            "page_count": len(document),
        }


def _review_lineage(
    repository_root: Path,
    *,
    candidate_revision: int,
) -> tuple[
    set[str],
    HashedArtifact | None,
    str | None,
    list[str],
    str | None,
    str | None,
]:
    if candidate_revision <= 3:
        return set(), None, None, [], None, None
    if candidate_revision not in {4, 5, 6}:
        raise ValueError(
            "a new explicit review-lineage rule is required after Candidate revision 6"
        )
    if candidate_revision == 4:
        predecessor_relative_path = R3_CANDIDATE
        predecessor_sha256 = R3_CANDIDATE_SHA256
        review_relative_path = REVIEW_DECISIONS_R3
        source_filename = R3_REVIEW_SOURCE_FILENAME
        source_sha256 = R3_REVIEW_SOURCE_SHA256
    else:
        predecessor_relative_path = R4_CANDIDATE
        predecessor_sha256 = R4_CANDIDATE_SHA256
        review_relative_path = REVIEW_DECISIONS_R4
        source_filename = REVIEW_DECISIONS_R4.name
        source_sha256 = sha256_file(repository_root / REVIEW_DECISIONS_R4)
    predecessor_path = repository_root / predecessor_relative_path
    if sha256_file(predecessor_path) != predecessor_sha256:
        raise ValueError(
            f"r{candidate_revision - 1} predecessor Candidate Hash changed after course_owner review"
        )
    predecessor = DS1ParsingDataset.model_validate_json(
        predecessor_path.read_text(encoding="utf-8")
    )
    review_path = repository_root / review_relative_path
    decisions = DS1ReviewDecisions.model_validate_json(review_path.read_text(encoding="utf-8"))
    if decisions.candidate_file_sha256 != predecessor_sha256:
        raise ValueError("course_owner review decisions do not bind the exact predecessor")
    if decisions.record_count != len(predecessor.records):
        raise ValueError("course_owner review record_count differs from r3")
    predecessor_ids = {record.record_id for record in predecessor.records}
    expected_reviewed = predecessor_ids - {TABLE_020_RECORD_ID}
    if set(decisions.reviewed_record_ids) != expected_reviewed:
        raise ValueError("review decisions must leave only DOCX table 20 for correction")
    if candidate_revision == 4 and decisions.returned_record_ids:
        raise ValueError("r3 attachment did not encode an explicit returned-record field")
    if candidate_revision == 5 and decisions.returned_record_ids != [TABLE_020_RECORD_ID]:
        raise ValueError("r4 course_owner feedback must explicitly return DOCX table 20")
    return (
        set(decisions.reviewed_record_ids),
        _artifact(repository_root, review_relative_path, "application/json"),
        predecessor_sha256,
        [TABLE_020_RECORD_ID],
        source_filename,
        source_sha256,
    )


def build_ds1_p04_candidate(
    *,
    repository_root: Path,
    candidate_revision: int,
) -> dict[str, object]:
    repository_root = repository_root.resolve()
    dataset_root = repository_root / DATASET_ROOT
    candidate_path = dataset_root / "candidates/ds1" / f"p04_native_docx_r{candidate_revision}.json"
    provenance_path = dataset_root / "provenance/ds1_p04_candidate_manifest.json"
    approved_ds0, work_package = _load_inputs(repository_root)
    versions = _document_versions(approved_ds0)
    profile = RendererProfile.load(repository_root / RENDERER_PROFILE)
    renderer_gold = DocxRenderProfile(
        provider=profile.provider,
        renderer_version=profile.renderer_version,
        font_manifest_sha256=profile.font_manifest_sha256,
        profile_sha256=profile.profile_sha256,
    )
    primary_pair = _verify_render_pair(
        repository_root,
        document_id="doc_ai_algorithms_systems",
        run_paths=PRIMARY_RENDER_RUNS,
        expected_page_count=636,
    )
    stress_pair = _verify_render_pair(
        repository_root,
        document_id="doc_ai_algorithms_systems_structure_stress",
        run_paths=STRESS_RENDER_RUNS,
        expected_page_count=128,
    )
    render_pairs = {
        primary_pair.document_id: primary_pair,
        stress_pair.document_id: stress_pair,
    }
    (
        pre_reviewed_record_ids,
        review_decisions_artifact,
        predecessor_candidate_sha256,
        required_rereview_record_ids,
        review_decisions_source_filename,
        review_decisions_source_sha256,
    ) = _review_lineage(repository_root, candidate_revision=candidate_revision)
    page_records, _ = _native_pdf_pages(repository_root, work_package, versions)
    pagination_records = _pagination_records(
        work_package,
        versions,
        renderer_gold,
        render_pairs,
    )
    section_records = [
        *_pdf_sections(repository_root, work_package, versions),
        *_docx_sections(repository_root, work_package, versions),
    ]
    table_records = _table_records(repository_root, work_package, versions, primary_pair)
    records: list[ParsingGoldRecord] = [
        *page_records,
        *pagination_records,
        *section_records,
        *table_records,
    ]
    counts = {
        "page": len(page_records),
        "docx_pagination": len(pagination_records),
        "section": len(section_records),
        "table": len(table_records),
        "ocr": 0,
    }
    if counts != {"page": 15, "docx_pagination": 10, "section": 20, "table": 10, "ocr": 0}:
        raise ValueError(f"formal P04 DS1 Candidate counts changed: {counts}")
    dataset = DS1ParsingDataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        records=records,
    )
    if any(record.review_status is not ReviewStatus.CANDIDATE for record in dataset.records):
        raise ValueError("Candidate generation cannot create Approved DS1 records")
    if candidate_path.exists():
        current = DS1ParsingDataset.model_validate_json(candidate_path.read_text(encoding="utf-8"))
        if current != dataset:
            current_hashes = {record.record_id: record_digest(record) for record in current.records}
            new_hashes = {record.record_id: record_digest(record) for record in dataset.records}
            differences = sorted(
                record_id
                for record_id in current_hashes.keys() | new_hashes.keys()
                if current_hashes.get(record_id) != new_hashes.get(record_id)
            )
            raise ValueError(
                f"Candidate revision {candidate_revision} is immutable; create the next revision; "
                f"different records: {differences}"
            )
    else:
        atomic_write_json(candidate_path, dataset.model_dump(mode="json"))
    candidate_sha256 = sha256_file(candidate_path)
    review_dir = repository_root / "storage_eval/ds1_p04_review" / candidate_sha256
    review_assets = review_dir / "assets"
    page_images = _copy_pdf_review_images(repository_root, review_assets, page_records)
    _page_overlay_previews(
        review_dir=review_dir,
        page_records=page_records,
        page_images=page_images,
    )
    anchor_images = _render_anchor_images(review_assets, pagination_records, render_pairs)
    table_fragment_images = _render_table_fragment_images(
        review_assets,
        table_records,
        primary_pair,
    )
    _contact_sheet(
        [review_dir / relative for relative in anchor_images.values()],
        review_assets / "docx_anchor_contact_sheet.png",
    )
    crosscheck = _word_crosscheck(repository_root)
    html_text = _review_html(
        candidate_sha256=candidate_sha256,
        records=list(dataset.records),
        page_images=page_images,
        anchor_images=anchor_images,
        table_fragment_images=table_fragment_images,
        pre_reviewed_record_ids=pre_reviewed_record_ids,
        required_rereview_record_ids=required_rereview_record_ids,
        word_crosscheck_status=str(crosscheck["status"]),
    )
    atomic_write_text(review_dir / "index.html", html_text)
    review_asset_count = _validate_review_pack(review_dir)
    second_review_ids = [record.record_id for record in pagination_records] + [
        record.record_id
        for record in section_records
        if (
            f"p04-section-{'pdf' if record.document_id == 'doc_ai_general_education_excerpt' else 'docx'}-"
            f"{record.title.split()[0].replace('　', '')}"
        )
        in SECOND_REVIEW_SECTION_SELECTIONS
    ]
    if len(second_review_ids) != 15:
        raise ValueError(
            "the frozen second-review set must contain 10 pagination and 5 Section records"
        )
    source_artifacts = [
        _artifact(repository_root, PDF_PRIMARY, "application/pdf"),
        _artifact(
            repository_root,
            DOCX_PRIMARY,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        _artifact(repository_root, APPROVED_WORK_PACKAGE, "application/json"),
        _artifact(repository_root, RENDERER_PROFILE, "application/json"),
        _artifact(repository_root, RENDERER_FONT_LOCK, "application/json"),
    ]
    for pair in render_pairs.values():
        source_artifacts.extend(
            _artifact(repository_root, path, "application/pdf") for path in pair.run_paths
        )
    if review_decisions_artifact is not None:
        source_artifacts.append(review_decisions_artifact)
    if candidate_revision >= 5:
        source_artifacts.append(_artifact(repository_root, REVIEW_DECISIONS_R3, "application/json"))
    manifest_values = {
        "dataset_id": "courserag-eval",
        "dataset_version": "v1",
        "candidate_revision": candidate_revision,
        "candidate_relative_path": _relative(repository_root, candidate_path),
        "candidate_file_sha256": candidate_sha256,
        "candidate_record_sha256": {
            record.record_id: record_digest(record) for record in dataset.records
        },
        "source_artifacts": source_artifacts,
        "semantic_source_count": 2,
        "record_counts": counts,
        "renderer_profile": renderer_gold,
        "canonical_rendered_pdf_sha256": {
            document_id: pair.canonical_pdf_sha256 for document_id, pair in render_pairs.items()
        },
        "raw_rendered_pdf_run_sha256": {
            document_id: list(pair.raw_sha256) for document_id, pair in render_pairs.items()
        },
        "review_pack_relative_path": _relative(repository_root, review_dir / "index.html"),
        "second_review_record_ids": second_review_ids,
        "predecessor_candidate_file_sha256": predecessor_candidate_sha256,
        "review_decisions_artifact": review_decisions_artifact,
        "review_decisions_source_filename": review_decisions_source_filename,
        "review_decisions_source_sha256": review_decisions_source_sha256,
        "required_rereview_record_ids": required_rereview_record_ids,
        "constraints": [
            "Candidate only; exact course_owner approval is required before Approved DS1 exists.",
            "Only two independent semantic source lineages exist.",
            "The structure-stress DOCX is a non-retrievable derived fixture.",
            "OCR transcription and OCR Gold are deferred to P05.",
            "P04 Parser predictions were not used as Candidate labels.",
            (
                "DOCX table 20 has a 6x4 OOXML source grid but a course_owner-confirmed 7x4 "
                "rendered-visible Gold grid spanning physical pages 547-548."
            ),
            f"Word cross-render check: {crosscheck['status']}.",
        ],
    }
    manifest = DS1CandidateManifest.model_validate(manifest_values)
    atomic_write_json(provenance_path, manifest.model_dump(mode="json"))
    report_path = repository_root / "docs/refactor/phase_reports/ED_P04_DS1_candidate_review.md"
    report = f"""# ED-P04 DS1 Candidate Review Checkpoint

- Status: **Candidate generated; awaiting exact course_owner approval**
- Candidate: `{manifest.candidate_relative_path}`
- Candidate SHA-256: `{candidate_sha256}`
- Review pack: `{manifest.review_pack_relative_path}`
- Counts: Page 15 / DOCX Pagination 10 / Section 20 / Table 10 / OCR 0
- Renderer: `{profile.provider}` `{profile.renderer_version}`
- Canonical primary DOCX PDF: `{primary_pair.canonical_pdf_sha256}` (636 physical pages)
- Canonical stress DOCX PDF: `{stress_pair.canonical_pdf_sha256}` (128 physical pages)
- Word 2021 cross-check: `{crosscheck["status"]}` — {crosscheck["reason"]}
- Predecessor Candidate: `{predecessor_candidate_sha256 or "none"}`
- Current review source: `{review_decisions_source_filename or "none"}`
- Current review source SHA-256: `{review_decisions_source_sha256 or "none"}`
- Original r3 review attachment SHA-256: `{R3_REVIEW_SOURCE_SHA256 if candidate_revision >= 4 else "none"}`
- Required re-review: `{", ".join(required_rereview_record_ids) or "all original checks"}`

## Required course_owner review

1. PDF: physical page, page type, Region BBox/type, reading order and header/footer/page-number noise.
2. DOCX pagination: exact source text/unit, physical page and visible display/Section page labels; `null` must not be guessed.
3. Section: exact title, level, parent, source boundary, first and last text.
4. Table: row/column count, merged-cell blanks, line breaks and every visible cell value.
5. Global: no invented course content, source Hashes unchanged, only two semantic sources, no OCR Gold.

Second review is mandatory for all 10 pagination records and the five Section records listed in
`datasets/courserag_eval/v1/provenance/ds1_p04_candidate_manifest.json`.

For r{candidate_revision}, the 54 records accepted in the r3 review artifact are pre-checked in the offline package.
Only `ds1-table-docx-020` requires re-review. Its source OOXML grid is 6x4, while the fixed-renderer
physical pages 547 and 548 show seven visible rows in total; both page images, the 7x4 Gold grid
and the 6x4 source grid are shown in the review card.

Approval syntax: `批准正式 DS1 Candidate {candidate_sha256}`. A generic approval must not promote
this batch. Any correction creates the next revision; revisions 1 through {candidate_revision} are
retained and never silently overwritten.

## Current gate

Approved DS1 is still empty, `gold_status` remains `ds0_pilot_approved`, Dev/Test remain empty and
Test remains unlocked. Formal P04/B0 evaluation is prohibited until the exact Candidate Hash is
approved.
"""
    atomic_write_text(report_path, report)
    return {
        "candidate_path": _relative(repository_root, candidate_path),
        "candidate_file_sha256": candidate_sha256,
        "provenance_path": _relative(repository_root, provenance_path),
        "provenance_file_sha256": sha256_file(provenance_path),
        "review_pack": _relative(repository_root, review_dir / "index.html"),
        "review_pack_sha256": sha256_file(review_dir / "index.html"),
        "review_asset_count": review_asset_count,
        "report_path": _relative(repository_root, report_path),
        "record_counts": counts,
        "word_crosscheck": crosscheck,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the formal P04 DS1 Candidate review batch.")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--candidate-revision", type=int, default=1)
    args = parser.parse_args()
    result = build_ds1_p04_candidate(
        repository_root=args.repository_root,
        candidate_revision=args.candidate_revision,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
