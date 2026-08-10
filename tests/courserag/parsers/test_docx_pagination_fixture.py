from pathlib import Path

from courserag.domain.document import sha256_bytes
from courserag.parsers.docx import StructuredDOCXParser
from courserag.parsers.pagination import (
    DocxPaginationRenderer,
    RendererProfile,
    align_docx_blocks,
)

CORPUS_ROOT = Path("storage_eval/courserag_corpus/v1")
DOCX_PATH = CORPUS_ROOT / "doc_ai_algorithms_systems_structure_stress.docx"
PDF_RUN_1 = CORPUS_ROOT / "docx_qa_render_r3" / "doc_ai_algorithms_systems_structure_stress.pdf"
PDF_RUN_2 = CORPUS_ROOT / "docx_qa_render_r4" / "doc_ai_algorithms_systems_structure_stress.pdf"
PROFILE_PATH = Path("resources/renderers/libreoffice_headless_v1/profile.json")


def test_real_layout_stress_snapshot_is_canonical_and_anchor_reproducible() -> None:
    renderer = DocxPaginationRenderer(
        RendererProfile.load(PROFILE_PATH),
        font_resolver=lambda font: font,
    )
    first = renderer.build_snapshot(PDF_RUN_1.read_bytes())
    second = renderer.build_snapshot(PDF_RUN_2.read_bytes())
    assert first.manifest.raw_pdf_sha256 != second.manifest.raw_pdf_sha256
    assert first.manifest.canonical_pdf_sha256 == second.manifest.canonical_pdf_sha256
    assert first.manifest.page_manifest_sha256 == second.manifest.page_manifest_sha256
    assert first.manifest.page_count == second.manifest.page_count == 128

    content = DOCX_PATH.read_bytes()
    parsed = (
        StructuredDOCXParser()
        .parse(
            content,
            document_id="doc-ai-algorithms-systems-structure-stress",
            document_version_id="p04-layout-stress-v1",
            document_sha256=sha256_bytes(content),
        )
        .document
    )
    first_aligned = align_docx_blocks(parsed, first, low_confidence_threshold=0.75)
    second_aligned = align_docx_blocks(parsed, second, low_confidence_threshold=0.75)
    first_anchors = {
        block.source_span.source_unit: block.page_anchor
        for block in first_aligned.pages[0].blocks
        if block.source_span.source_unit in {"docx:paragraph:19", "docx:paragraph:144"}
    }
    second_anchors = {
        block.source_span.source_unit: block.page_anchor
        for block in second_aligned.pages[0].blocks
        if block.source_span.source_unit in first_anchors
    }
    assert set(first_anchors) == {"docx:paragraph:19", "docx:paragraph:144"}
    assert first_anchors == second_anchors
    assert all(
        anchor is not None and anchor.physical_page_index is not None
        for anchor in first_anchors.values()
    )
