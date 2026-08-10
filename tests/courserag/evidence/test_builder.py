from courserag.domain.document import (
    BlockIR,
    DocxPageAnchor,
    PageIR,
    ParsedDocumentIR,
    SectionIR,
    SourceSpan,
    sha256_text,
)
from courserag.evidence.builder import EvidenceBuilder


def _document() -> ParsedDocumentIR:
    blocks = (
        _block("head", "header", "课程教材", 0, noise=("repeated_header",)),
        _block("title", "heading", "1.1 搜索", 1),
        _block("step1", "list_item", "第一步：定义状态。", 2),
        _block("step2", "list_item", "第二步：扩展节点。", 3),
        _block("definition", "paragraph", "启发式函数是指对剩余代价的估计。", 4),
    )
    page_text = "\n".join(block.text for block in blocks)
    page = PageIR(
        page_id="page-1",
        physical_page_index=1,
        width=600,
        height=800,
        source_mode="native_text",
        blocks=blocks,
        content_sha256=sha256_text(page_text),
    )
    section = SectionIR(
        section_id="section-1",
        level=1,
        title="搜索",
        section_path=("搜索",),
        order_index=0,
        block_ids=tuple(block.block_id for block in blocks),
        source_span=_span("head"),
        content_sha256=sha256_text(page_text),
    )
    return ParsedDocumentIR(
        document_id="doc-1",
        document_version_id="version-1",
        document_sha256="a" * 64,
        source_format="pdf",
        parser_profile="test",
        parser_version="1",
        pages=(page,),
        sections=(section,),
    )


def _span(block_id: str) -> SourceSpan:
    return SourceSpan(
        document_id="doc-1",
        document_version_id="version-1",
        page_start=1,
        page_end=1,
        block_start_id=block_id,
        block_end_id=block_id,
    )


def _block(
    block_id: str,
    block_type: str,
    text: str,
    order: int,
    *,
    noise: tuple[str, ...] = (),
) -> BlockIR:
    return BlockIR(
        block_id=block_id,
        block_type=block_type,
        text=text,
        order_index=order,
        bbox=(10, 10 + 50 * order, 400, 40 + 50 * order),
        source_span=_span(block_id),
        noise_labels=noise,
        content_sha256=sha256_text(text),
    )


def test_builder_creates_stable_semantic_evidence_and_filters_noise() -> None:
    document = _document()
    first = EvidenceBuilder().build(document)
    second = EvidenceBuilder().build(document)

    assert first == second
    assert first.content_sha256 == second.content_sha256
    assert len(first.records) == 2
    assert first.records[0].evidence_type == "steps"
    assert [unit.block_id for unit in first.records[0].source_units] == [
        "title",
        "step1",
        "step2",
    ]
    assert first.records[1].evidence_type == "definition"
    assert all(
        "head" not in [unit.block_id for unit in record.source_units] for record in first.records
    )
    assert first.records[0].next_evidence_id == first.records[1].evidence_id
    assert first.records[1].previous_evidence_id == first.records[0].evidence_id


def test_evidence_identity_is_independent_of_builder_threshold() -> None:
    from courserag.evidence.builder import EvidenceBuilderProfile

    document = _document()
    first = EvidenceBuilder(EvidenceBuilderProfile(low_confidence_threshold=0.75)).build(document)
    second = EvidenceBuilder(EvidenceBuilderProfile(low_confidence_threshold=0.9)).build(document)

    assert [record.evidence_id for record in first.records] == [
        record.evidence_id for record in second.records
    ]


def test_docx_page_anchor_produces_explicit_coarse_page_bbox() -> None:
    document = _document()
    anchor = DocxPageAnchor(
        physical_page_index=3,
        display_page_label="1",
        section_page_index=1,
        renderer_provider="libreoffice-headless",
        renderer_version="test",
        render_profile_sha256="b" * 64,
        canonical_pdf_sha256="c" * 64,
        alignment_confidence=0.99,
        page_width=595,
        page_height=842,
    )
    blocks = tuple(
        block.model_copy(update={"bbox": None, "page_anchor": anchor})
        for block in document.pages[0].blocks
    )
    page = document.pages[0].model_copy(
        update={"source_mode": "logical_docx", "width": None, "height": None, "blocks": blocks}
    )
    docx_document = document.model_copy(update={"source_format": "docx", "pages": (page,)})

    artifact = EvidenceBuilder().build(docx_document)

    assert artifact.records
    assert all(record.page_bboxes for record in artifact.records)
    assert all("COARSE_DOCX_PAGE_BBOX" in record.warning_codes for record in artifact.records)
    assert artifact.records[0].page_bboxes[0].bbox == (0.0, 0.0, 595.0, 842.0)
