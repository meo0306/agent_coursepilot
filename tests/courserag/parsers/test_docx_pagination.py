from __future__ import annotations

from pathlib import Path

import fitz
import pytest

from courserag.domain.document import (
    BlockIR,
    PageIR,
    ParsedDocumentIR,
    SourceSpan,
    sha256_bytes,
    sha256_text,
)
from courserag.parsers.pagination import (
    CommandResult,
    DocxPaginationRenderer,
    RendererError,
    RendererProfile,
    align_docx_blocks,
)


def _profile() -> RendererProfile:
    return RendererProfile.load(Path("resources/renderers/libreoffice_headless_v1/profile.json"))


def _rendered_pdf(*, creation_date: str) -> bytes:
    document = fitz.open()
    first = document.new_page(width=400, height=500)
    first.insert_text((40, 50), "First paragraph lives on page one.")
    first.insert_text((195, 475), "1")
    second = document.new_page(width=400, height=500)
    second.insert_text((40, 50), "Second paragraph lives on page two.")
    second.insert_text((195, 475), "2")
    document.set_metadata({"creationDate": creation_date, "producer": "LibreOffice 7.4.7.2"})
    content = document.tobytes()
    document.close()
    return content


def _logical_docx() -> ParsedDocumentIR:
    blocks = []
    for index, text in enumerate(
        ("First paragraph lives on page one.", "Second paragraph lives on page two.")
    ):
        block_id = f"block-{index}"
        blocks.append(
            BlockIR(
                block_id=block_id,
                block_type="paragraph",
                text=text,
                order_index=index,
                source_span=SourceSpan(
                    document_id="docx-doc",
                    document_version_id="docx-v1",
                    block_start_id=block_id,
                    block_end_id=block_id,
                    source_unit=f"docx:paragraph:{index}",
                ),
                content_sha256=sha256_text(text),
            )
        )
    page_text = "\n".join(block.text for block in blocks)
    return ParsedDocumentIR(
        document_id="docx-doc",
        document_version_id="docx-v1",
        document_sha256="a" * 64,
        source_format="docx",
        parser_profile="structured_docx_v1",
        parser_version="1.0",
        pages=(
            PageIR(
                page_id="logical-page",
                physical_page_index=None,
                source_mode="logical_docx",
                blocks=tuple(blocks),
                content_sha256=sha256_text(page_text),
            ),
        ),
        sections=(),
    )


def test_canonical_snapshot_hash_ignores_volatile_metadata() -> None:
    renderer = DocxPaginationRenderer(_profile(), font_resolver=lambda font: font)
    first = renderer.build_snapshot(_rendered_pdf(creation_date="D:20260101000000Z"))
    second = renderer.build_snapshot(_rendered_pdf(creation_date="D:20260102000000Z"))
    assert first.manifest.raw_pdf_sha256 != second.manifest.raw_pdf_sha256
    assert first.manifest.canonical_pdf_sha256 == second.manifest.canonical_pdf_sha256
    assert first.manifest.page_manifest_sha256 == second.manifest.page_manifest_sha256
    assert first.manifest.page_count == 2


def test_alignment_assigns_physical_and_source_visible_page_labels() -> None:
    renderer = DocxPaginationRenderer(_profile(), font_resolver=lambda font: font)
    snapshot = renderer.build_snapshot(_rendered_pdf(creation_date="D:20260101000000Z"))
    aligned = align_docx_blocks(
        _logical_docx(),
        snapshot,
        low_confidence_threshold=0.75,
    )
    anchors = [block.page_anchor for block in aligned.pages[0].blocks]
    assert anchors[0] is not None and anchors[0].physical_page_index == 1
    assert anchors[0].display_page_label == "1"
    assert anchors[1] is not None and anchors[1].physical_page_index == 2
    assert anchors[1].display_page_label == "2"
    assert aligned.renderer_manifest is not None
    assert aligned.renderer_manifest.canonical_pdf_sha256 == sha256_bytes(snapshot.canonical_pdf)


def test_missing_font_and_low_alignment_never_guess_a_page() -> None:
    renderer = DocxPaginationRenderer(_profile(), font_resolver=lambda font: "Noto Sans CJK SC")
    snapshot = renderer.build_snapshot(
        _rendered_pdf(creation_date="D:20260101000000Z"),
        requested_fonts=("Missing Font",),
    )
    mismatched = _logical_docx()
    original = mismatched.pages[0].blocks[0]
    changed_text = "This sentence does not occur in the rendered PDF."
    changed = original.model_copy(
        update={"text": changed_text, "content_sha256": sha256_text(changed_text)}
    )
    page = mismatched.pages[0].model_copy(
        update={
            "blocks": (changed, *mismatched.pages[0].blocks[1:]),
            "content_sha256": sha256_text(
                "\n".join(block.text for block in (changed, *mismatched.pages[0].blocks[1:]))
            ),
        }
    )
    aligned = align_docx_blocks(
        mismatched.model_copy(update={"pages": (page,)}),
        snapshot,
        low_confidence_threshold=0.75,
    )
    anchor = aligned.pages[0].blocks[0].page_anchor
    assert anchor is not None and anchor.physical_page_index is None
    assert {warning.code for warning in aligned.warnings} >= {
        "FONT_SUBSTITUTION",
        "LOW_DOCX_ALIGNMENT_CONFIDENCE",
    }


def test_render_fails_closed_when_required_font_is_missing() -> None:
    def executor(arguments, *, timeout_seconds, environment):
        del timeout_seconds, environment
        if "--version" in arguments:
            return CommandResult(0, "LibreOffice 7.4.7.2", "")
        return CommandResult(0, "1:20220127+repack1-1", "")

    renderer = DocxPaginationRenderer(
        _profile(),
        command_executor=executor,
        font_resolver=lambda font: None,
    )
    with pytest.raises(RendererError, match="font family"):
        renderer.render(b"not reached")
