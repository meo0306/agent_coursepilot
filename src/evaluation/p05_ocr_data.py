"""Build the source-grounded P05 OCR Candidate and offline review pack.

Revision 3 reuses exact Approved P04 PageGold annotations whenever available. It keeps raw page
text and every source region, but derives the OCR body projection from explicit region roles so
headers, page numbers, QR material, figures, captions, and embedded image text cannot silently
enter the body CER denominator.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
from pathlib import Path

import fitz

from courserag.evals.schemas import (
    BODY_OCR_REGION_ROLES,
    CorpusDocument,
    DS0CorpusDataset,
    DS1ParsingDataset,
    DS1ReviewDecisions,
    OCRGold,
    OCRRegion,
    OCRRegionRole,
    OCRRouteOnlyCandidate,
    P04InputWorkPackage,
    P05OCRCandidateManifest,
    PageGold,
    PageRegion,
)
from evaluation.contracts import (
    CandidateRevisionArtifact,
    CandidateRevisionHistory,
    HashedArtifact,
    ReviewStatus,
    SourceSpan,
)
from evaluation.corpus_fixtures import PDF_PRIMARY, sha256_file
from evaluation.datasets import record_digest
from evaluation.io import atomic_write_bytes, atomic_write_json, atomic_write_text

DATASET_ID = "courserag-eval"
DATASET_VERSION = "v1"
OCR_DPI = 200
R1_RELATIVE_PATH = "datasets/courserag_eval/v1/candidates/ds1/p05_ocr_r1.json"
R1_SHA256 = "2e48d78b1f48e9357bd32c02d7aa75b907318db2d71a5423a1da8cb348068865"
R2_RELATIVE_PATH = "datasets/courserag_eval/v1/candidates/ds1/p05_ocr_r2.json"
R2_SHA256 = "a497cc36cb599afcb77948821fe5a7e028041b0ade563c4b5d4062a0fc54b215"
R3_RELATIVE_PATH = "datasets/courserag_eval/v1/candidates/ds1/p05_ocr_r3.json"
R3_REVIEW_RELATIVE_PATH = "datasets/courserag_eval/v1/candidates/work_packages/p05_ocr_review_r3"
P04_APPROVED_RELATIVE_PATH = "datasets/courserag_eval/v1/approved/ds1/p04_native_docx.json"
R1_REVIEW_RELATIVE_PATH = "datasets/courserag_eval/v1/reviews/p05_ocr_review_decisions_r1.json"
R2_REVIEW_RELATIVE_PATH = "datasets/courserag_eval/v1/reviews/p05_ocr_review_decisions_r2.json"
R1_RETURNED_RECORD_IDS = {"ds1-ocr-01", "ds1-ocr-07", "ds1-ocr-12", "ds1-ocr-15"}
R2_RETURNED_RECORD_IDS = {
    "ds1-ocr-02",
    "ds1-ocr-05",
    "ds1-ocr-06",
    "ds1-ocr-07",
    "ds1-ocr-08",
    "ds1-ocr-09",
    "ds1-ocr-10",
}

_HEADING = re.compile(r"^\s*\d+(?:\.\d+)+(?:\s|\u3000|$)")
_LIST = re.compile(r"^\s*(?:\(?\d+\)?[.、]|[①②③④⑤⑥⑦⑧⑨⑩])")
_PAGE_NUMBER = re.compile(r"^(?:[ivxlcdm]+|\d+)$", re.IGNORECASE)
_FIGURE_CAPTION = re.compile(r"^\s*图\s*\d+(?:\s*[-－—]\s*\d+)?(?:\s|　|$)")
_FIGURE_NUMBER_ONLY = re.compile(r"^\s*图\s*\d+(?:\s*[-－—]\s*\d+)?\s*$")


def build_p05_ocr_candidate(
    *,
    repository_root: Path,
    dataset_root: Path,
    output_root: Path | None = None,
) -> dict[str, object]:
    repository_root = repository_root.resolve()
    dataset_root = dataset_root.resolve()
    output_root = (output_root or dataset_root).resolve()
    approved_ds0_path = dataset_root / "approved/ds0/pilot.json"
    work_package_path = dataset_root / "approved/work_packages/p04_input.json"
    p04_approved_path = _dataset_path(dataset_root, P04_APPROVED_RELATIVE_PATH)
    r1_path = _dataset_path(dataset_root, R1_RELATIVE_PATH)
    r2_path = _dataset_path(dataset_root, R2_RELATIVE_PATH)
    r1_review_decisions_path = _dataset_path(dataset_root, R1_REVIEW_RELATIVE_PATH)
    r2_review_decisions_path = _dataset_path(dataset_root, R2_REVIEW_RELATIVE_PATH)
    approved_ds0 = DS0CorpusDataset.model_validate_json(
        approved_ds0_path.read_text(encoding="utf-8")
    )
    work_package = P04InputWorkPackage.model_validate_json(
        work_package_path.read_text(encoding="utf-8")
    )
    if work_package.review_status is not ReviewStatus.APPROVED:
        raise ValueError("P05 Candidate requires the exact Approved P04 input package")
    if sha256_file(r1_path) != R1_SHA256:
        raise ValueError("P05 r1 Candidate differs from the owner-reviewed revision")
    if sha256_file(r2_path) != R2_SHA256:
        raise ValueError("P05 r2 Candidate differs from the owner-reviewed revision")
    r1_review_decisions = DS1ReviewDecisions.model_validate_json(
        r1_review_decisions_path.read_text(encoding="utf-8")
    )
    r2_review_decisions = DS1ReviewDecisions.model_validate_json(
        r2_review_decisions_path.read_text(encoding="utf-8")
    )
    _validate_review(
        r1_review_decisions,
        expected_candidate_sha256=R1_SHA256,
        expected_returned_ids=R1_RETURNED_RECORD_IDS,
        revision="r1",
    )
    _validate_review(
        r2_review_decisions,
        expected_candidate_sha256=R2_SHA256,
        expected_returned_ids=R2_RETURNED_RECORD_IDS,
        revision="r2",
    )
    p04_dataset = DS1ParsingDataset.model_validate_json(
        p04_approved_path.read_text(encoding="utf-8")
    )
    p04_pages = {
        record.page_number: record for record in p04_dataset.records if isinstance(record, PageGold)
    }
    if len(p04_pages) != 15 or any(
        record.review_status is not ReviewStatus.APPROVED for record in p04_pages.values()
    ):
        raise ValueError("P05 inheritance requires 15 exact Approved P04 PageGold records")

    documents = {document.document_id: document for document in approved_ds0.documents}
    source_document = documents[PDF_PRIMARY]
    source_path = _document_path(repository_root, source_document)
    _verify_document(source_path, source_document)

    candidate_path = output_root / "candidates/ds1/p05_ocr_r3.json"
    review_root = output_root / "candidates/work_packages/p05_ocr_review_r3"
    records: list[OCRGold] = []
    rendered_images: list[tuple[OCRGold, str]] = []
    inherited_hashes: dict[str, str] = {}
    newly_annotated: list[str] = []
    with fitz.open(source_path) as source_pdf:
        for index, selection in enumerate(work_package.ocr_route_only_pages, start=1):
            input_document = documents[selection.document_id]
            input_path = _document_path(repository_root, input_document)
            _verify_document(input_path, input_document)
            source_page = source_pdf[selection.source_page_number - 1]
            with fitz.open(input_path) as input_pdf:
                input_page = input_pdf[selection.document_page_number - 1]
                _validate_page_geometry(source_page, input_page)
                image = input_page.get_pixmap(
                    matrix=fitz.Matrix(OCR_DPI / 72.0, OCR_DPI / 72.0),
                    alpha=False,
                )
                png = image.tobytes("png")
            filename = f"{index:02d}-{selection.document_id}-p{selection.document_page_number}.png"
            atomic_write_bytes(review_root / filename, png)
            page_gold = p04_pages.get(selection.source_page_number)
            if page_gold is None:
                source_regions, source_reading_order = _new_page_annotation(
                    source_page,
                    selection.source_page_number,
                )
                inherited_id = None
                inherited_hash = None
                candidate_source = "native_pdf_geometry_plus_owner_policy"
                newly_annotated.append(f"ds1-ocr-{index:02d}")
            else:
                source_regions = [*page_gold.regions, *page_gold.noise_regions]
                source_reading_order = page_gold.reading_order
                inherited_id = page_gold.record_id
                inherited_hash = record_digest(page_gold)
                inherited_hashes[inherited_id] = inherited_hash
                candidate_source = "p04_page_gold_plus_owner_policy"
            record = _ocr_record(
                index=index,
                selection=selection,
                source_document=source_document,
                input_document=input_document,
                source_page=source_page,
                image_width=image.width,
                image_height=image.height,
                image_sha256=hashlib.sha256(png).hexdigest(),
                source_regions=source_regions,
                source_reading_order=source_reading_order,
                inherited_page_gold_record_id=inherited_id,
                inherited_page_gold_record_sha256=inherited_hash,
                candidate_source=candidate_source,
            )
            records.append(record)
            rendered_images.append((record, filename))
    if len(inherited_hashes) != 11 or len(newly_annotated) != 4:
        raise ValueError("P05 r3 must inherit 11 P04 pages and newly annotate exactly four pages")

    candidate = DS1ParsingDataset(
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        records=records,
    )
    atomic_write_json(candidate_path, candidate.model_dump(mode="json"))
    review_index = review_root / "index.html"
    atomic_write_text(review_index, _review_html(rendered_images))

    source_artifacts = [
        _hashed_artifact(_document_path(repository_root, document), repository_root)
        for document in [
            source_document,
            *[
                documents[document_id]
                for document_id in sorted(
                    {selection.document_id for selection in work_package.ocr_route_only_pages}
                )
            ],
        ]
    ]
    source_artifacts.extend(
        [
            _hashed_artifact(p04_approved_path, repository_root, "application/json"),
            _hashed_artifact(r1_path, repository_root, "application/json"),
            _hashed_artifact(r1_review_decisions_path, repository_root, "application/json"),
            _hashed_artifact(r2_path, repository_root, "application/json"),
            _hashed_artifact(r2_review_decisions_path, repository_root, "application/json"),
        ]
    )
    manifest = P05OCRCandidateManifest(
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        candidate_relative_path=R3_RELATIVE_PATH,
        candidate_file_sha256=sha256_file(candidate_path),
        candidate_record_sha256={record.record_id: record_digest(record) for record in records},
        previous_candidate_file_sha256=R2_SHA256,
        p04_work_package_sha256=sha256_file(work_package_path),
        p04_approved_ds1_sha256=sha256_file(p04_approved_path),
        inherited_page_gold_record_sha256=inherited_hashes,
        newly_annotated_record_ids=newly_annotated,
        review_decisions_sha256=sha256_file(r2_review_decisions_path),
        source_artifacts=source_artifacts,
        review_pack_relative_path=R3_REVIEW_RELATIVE_PATH,
        review_pack_index_sha256=sha256_file(review_index),
    )
    manifest_path = output_root / "provenance/p05_ocr_candidate_manifest.json"
    atomic_write_json(manifest_path, manifest.model_dump(mode="json"))
    history = CandidateRevisionHistory(
        dataset_id=DATASET_ID,
        dataset_version=DATASET_VERSION,
        revisions=[
            CandidateRevisionArtifact(
                revision=1,
                candidate_relative_path=R1_RELATIVE_PATH,
                candidate_file_sha256=R1_SHA256,
                status="superseded",
                reason=(
                    "Returned after Course Owner review: body text mixed headers, page numbers, "
                    "QR-related text, embedded image text, and ambiguous figure/text ordering."
                ),
            ),
            CandidateRevisionArtifact(
                revision=2,
                candidate_relative_path=R2_RELATIVE_PATH,
                candidate_file_sha256=R2_SHA256,
                status="superseded",
                reason=(
                    "Returned after Course Owner review: seven split captions marked only their "
                    "figure numbers as captions while adjacent figure names remained body text."
                ),
            ),
            CandidateRevisionArtifact(
                revision=3,
                candidate_relative_path=R3_RELATIVE_PATH,
                candidate_file_sha256=manifest.candidate_file_sha256,
                status="pending_course_owner_review",
                reason=(
                    "Preserves the accepted raw/body policy and groups same-baseline figure "
                    "numbers plus adjacent figure names into complete captions."
                ),
            ),
        ],
    )
    history_path = output_root / "provenance/p05_ocr_candidate_revision_history.json"
    atomic_write_json(history_path, history.model_dump(mode="json"))
    return {
        "candidate_file_sha256": manifest.candidate_file_sha256,
        "candidate_record_count": len(records),
        "inherited_page_gold_count": len(inherited_hashes),
        "new_page_annotation_count": len(newly_annotated),
        "manifest_sha256": sha256_file(manifest_path),
        "review_pack_index_sha256": manifest.review_pack_index_sha256,
        "approval_status": "pending_course_owner_review",
    }


def _validate_review(
    review: DS1ReviewDecisions,
    *,
    expected_candidate_sha256: str,
    expected_returned_ids: set[str],
    revision: str,
) -> None:
    all_ids = {f"ds1-ocr-{index:02d}" for index in range(1, 16)}
    if review.candidate_file_sha256 != expected_candidate_sha256:
        raise ValueError(f"P05 {revision} review decisions bind a different Candidate")
    if set(review.returned_record_ids) != expected_returned_ids:
        raise ValueError(f"P05 {revision} returned-record set differs from Course Owner feedback")
    if set(review.reviewed_record_ids) | set(review.returned_record_ids) != all_ids:
        raise ValueError(f"P05 {revision} review decisions must cover all 15 records")


def _ocr_record(
    *,
    index: int,
    selection: OCRRouteOnlyCandidate,
    source_document: CorpusDocument,
    input_document: CorpusDocument,
    source_page: fitz.Page,
    image_width: int,
    image_height: int,
    image_sha256: str,
    source_regions: list[PageRegion],
    source_reading_order: list[str],
    inherited_page_gold_record_id: str | None,
    inherited_page_gold_record_sha256: str | None,
    candidate_source: str,
) -> OCRGold:
    record_id = f"ds1-ocr-{index:02d}"
    page_width = float(source_page.rect.width)
    page_height = float(source_page.rect.height)
    regions, reading_order = _project_regions(
        record_id=record_id,
        source_regions=source_regions,
        source_reading_order=source_reading_order,
        page_width=page_width,
        page_height=page_height,
        image_width=image_width,
        image_height=image_height,
    )
    by_id = {region.region_id: region for region in regions}
    body_text = "\n".join(by_id[region_id].gold_text or "" for region_id in reading_order).strip()
    raw_text = source_page.get_text("text", sort=True).strip()
    if not body_text or not raw_text or not regions:
        raise ValueError(
            f"native source page {selection.source_page_number} has no P05 body projection"
        )
    return OCRGold(
        record_id=record_id,
        review_status="candidate",
        candidate_source=candidate_source,
        source_span=SourceSpan(
            document_id=source_document.document_id,
            document_version=source_document.document_version,
            document_sha256=source_document.sha256,
            page_start=selection.source_page_number,
            page_end=selection.source_page_number,
        ),
        ocr_input_document_id=selection.document_id,
        ocr_input_document_version=input_document.document_version,
        ocr_input_document_sha256=input_document.sha256,
        ocr_input_page_number=selection.document_page_number,
        image_sha256=image_sha256,
        image_width=image_width,
        image_height=image_height,
        dpi=OCR_DPI,
        source_page_width_points=page_width,
        source_page_height_points=page_height,
        raw_text=raw_text,
        raw_text_sha256=hashlib.sha256(raw_text.encode("utf-8")).hexdigest(),
        gold_text=body_text,
        gold_text_sha256=hashlib.sha256(body_text.encode("utf-8")).hexdigest(),
        regions=regions,
        reading_order=reading_order,
        inherited_page_gold_record_id=inherited_page_gold_record_id,
        inherited_page_gold_record_sha256=inherited_page_gold_record_sha256,
    )


def _project_regions(
    *,
    record_id: str,
    source_regions: list[PageRegion],
    source_reading_order: list[str],
    page_width: float,
    page_height: float,
    image_width: int,
    image_height: int,
) -> tuple[list[OCRRegion], list[str]]:
    if any(region.bbox is None for region in source_regions):
        raise ValueError("P05 source Regions require exact page coordinates")
    figures = [region for region in source_regions if region.region_type == "figure"]
    qr_labels = [region for region in source_regions if region.text and "拓展阅读" in region.text]
    qr_figure_ids: set[str] = set()
    for label in qr_labels:
        if not figures:
            continue
        nearest = min(figures, key=lambda figure: _bbox_gap(_bbox(label), _bbox(figure)))
        if _bbox_gap(_bbox(label), _bbox(nearest)) <= page_width * 0.18:
            qr_figure_ids.add(nearest.region_id)
    figure_caption_ids = _figure_caption_region_ids(source_regions, figures)

    role_by_source_id: dict[str, OCRRegionRole] = {}
    for region in source_regions:
        role_by_source_id[region.region_id] = _region_role(
            region,
            figures=figures,
            qr_figure_ids=qr_figure_ids,
            figure_caption_ids=figure_caption_ids,
        )
    known_order = [
        region_id for region_id in source_reading_order if region_id in role_by_source_id
    ]
    body_source_ids = [
        region_id
        for region_id in known_order
        if role_by_source_id[region_id] in BODY_OCR_REGION_ROLES
    ]
    missing_body = [
        region
        for region in source_regions
        if role_by_source_id[region.region_id] in BODY_OCR_REGION_ROLES
        and region.region_id not in body_source_ids
    ]
    body_source_ids.extend(
        region.region_id
        for region in sorted(
            missing_body,
            key=lambda item: (_bbox(item)[1], _bbox(item)[0]),
        )
    )
    body_index_by_source = {
        region_id: order_index for order_index, region_id in enumerate(body_source_ids)
    }
    ocr_id_by_source: dict[str, str] = {}
    regions: list[OCRRegion] = []
    scale_x = image_width / page_width
    scale_y = image_height / page_height
    for index, source_region in enumerate(source_regions):
        source_bbox = _bbox(source_region)
        pixel_bbox = (
            round(source_bbox[0] * scale_x),
            round(source_bbox[1] * scale_y),
            round(source_bbox[2] * scale_x),
            round(source_bbox[3] * scale_y),
        )
        if pixel_bbox[2] <= pixel_bbox[0] or pixel_bbox[3] <= pixel_bbox[1]:
            raise ValueError("P05 source Region produced an empty image-pixel BBox")
        region_id = f"{record_id}-region-{index:03d}"
        ocr_id_by_source[source_region.region_id] = region_id
        role = role_by_source_id[source_region.region_id]
        body_index = body_index_by_source.get(source_region.region_id)
        regions.append(
            OCRRegion(
                region_id=region_id,
                bbox=pixel_bbox,
                source_bbox_pdf_points=source_bbox,
                role=role,
                gold_text=source_region.text,
                include_in_body_text=role in BODY_OCR_REGION_ROLES,
                body_order_index=body_index,
                source_page_region_id=source_region.region_id,
            )
        )
    reading_order = [ocr_id_by_source[region_id] for region_id in body_source_ids]
    return regions, reading_order


def _region_role(
    region: PageRegion,
    *,
    figures: list[PageRegion],
    qr_figure_ids: set[str],
    figure_caption_ids: set[str],
) -> OCRRegionRole:
    text = " ".join((region.text or "").split())
    if region.region_type == "figure":
        return "qr_related" if region.region_id in qr_figure_ids else "figure"
    if region.region_type in {"header", "footer", "page_number", "noise"}:
        return region.region_type
    if "拓展阅读" in text:
        return "qr_related"
    qr_figures = [figure for figure in figures if figure.region_id in qr_figure_ids]
    if qr_figures and any(
        _near_or_inside(_bbox(region), _bbox(figure), margin=18) for figure in qr_figures
    ):
        return "qr_related"
    if region.region_id in figure_caption_ids:
        return "figure_caption"
    if any(_inside_or_overlaps(_bbox(region), _bbox(figure)) for figure in figures):
        return "figure_embedded_text"
    if region.region_type in BODY_OCR_REGION_ROLES:
        return region.region_type
    if region.region_type in {"formula", "other"}:
        return region.region_type
    return "other"


def _figure_caption_region_ids(
    regions: list[PageRegion],
    figures: list[PageRegion],
) -> set[str]:
    caption_ids: set[str] = set()
    text_regions = [region for region in regions if region.text and region.bbox is not None]
    for marker in text_regions:
        marker_text = " ".join((marker.text or "").split())
        if not _looks_like_figure_caption(marker_text, _bbox(marker), figures):
            continue
        caption_ids.add(marker.region_id)
        if _FIGURE_NUMBER_ONLY.fullmatch(marker_text) is None:
            continue
        adjacent_names = [
            candidate
            for candidate in text_regions
            if candidate.region_id != marker.region_id
            and _is_adjacent_caption_name(_bbox(marker), _bbox(candidate))
            and any(
                _near_or_inside(_bbox(candidate), _bbox(figure), margin=28) for figure in figures
            )
        ]
        if adjacent_names:
            nearest = min(
                adjacent_names,
                key=lambda candidate: _bbox(candidate)[0] - _bbox(marker)[2],
            )
            caption_ids.add(nearest.region_id)
    return caption_ids


def _is_adjacent_caption_name(
    marker: tuple[float, float, float, float],
    candidate: tuple[float, float, float, float],
) -> bool:
    marker_center_y = (marker[1] + marker[3]) / 2
    candidate_center_y = (candidate[1] + candidate[3]) / 2
    height = max(marker[3] - marker[1], candidate[3] - candidate[1])
    horizontal_gap = candidate[0] - marker[2]
    return 0 <= horizontal_gap <= 36 and abs(marker_center_y - candidate_center_y) <= max(
        4, height * 0.75
    )


def _looks_like_figure_caption(
    text: str,
    text_bbox: tuple[float, float, float, float],
    figures: list[PageRegion],
) -> bool:
    if not text or len(text) > 120 or _FIGURE_CAPTION.match(text) is None:
        return False
    return any(_near_or_inside(text_bbox, _bbox(figure), margin=24) for figure in figures)


def _inside_or_overlaps(
    inner: tuple[float, float, float, float],
    outer: tuple[float, float, float, float],
) -> bool:
    center_x = (inner[0] + inner[2]) / 2
    center_y = (inner[1] + inner[3]) / 2
    if outer[0] <= center_x <= outer[2] and outer[1] <= center_y <= outer[3]:
        return True
    intersection = max(0.0, min(inner[2], outer[2]) - max(inner[0], outer[0])) * max(
        0.0, min(inner[3], outer[3]) - max(inner[1], outer[1])
    )
    inner_area = (inner[2] - inner[0]) * (inner[3] - inner[1])
    return intersection / inner_area >= 0.50 if inner_area else False


def _near_or_inside(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
    *,
    margin: float,
) -> bool:
    expanded = (
        right[0] - margin,
        right[1] - margin,
        right[2] + margin,
        right[3] + margin,
    )
    return _inside_or_overlaps(left, expanded)


def _bbox_gap(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> float:
    horizontal = max(0.0, max(left[0], right[0]) - min(left[2], right[2]))
    vertical = max(0.0, max(left[1], right[1]) - min(left[3], right[3]))
    return horizontal + vertical


def _bbox(region: PageRegion) -> tuple[float, float, float, float]:
    if region.bbox is None:
        raise ValueError("P05 source Region has no BBox")
    return region.bbox


def _new_page_annotation(
    page: fitz.Page,
    page_number: int,
) -> tuple[list[PageRegion], list[str]]:
    page_height = float(page.rect.height)
    regions: list[PageRegion] = []
    payload = page.get_text("dict", sort=False)
    for fallback_index, block in enumerate(payload.get("blocks", [])):
        block_number = int(block.get("number", fallback_index))
        if int(block.get("type", 0)) == 1:
            bbox = tuple(float(value) for value in block["bbox"])
            region_type = "figure"
            text = None
        else:
            visible_lines = [
                (
                    "".join(str(span.get("text", "")) for span in line.get("spans", [])),
                    tuple(float(value) for value in line["bbox"]),
                )
                for line in block.get("lines", [])
                if "".join(str(span.get("text", "")) for span in line.get("spans", [])).strip()
            ]
            text = "\n".join(line_text.rstrip() for line_text, _ in visible_lines).strip()
            if not text:
                continue
            bbox = (
                min(line_bbox[0] for _, line_bbox in visible_lines),
                min(line_bbox[1] for _, line_bbox in visible_lines),
                max(line_bbox[2] for _, line_bbox in visible_lines),
                max(line_bbox[3] for _, line_bbox in visible_lines),
            )
            region_type = _basic_region_type(text, bbox, page_height)
        regions.append(
            PageRegion(
                region_id=f"p05-source-p{page_number:03d}-r{len(regions):03d}",
                region_type=region_type,
                text=text,
                bbox=bbox,
                block_id=f"pymupdf:p{page_number:03d}:b{block_number:04d}",
            )
        )
    content = [
        region
        for region in regions
        if region.region_type not in {"header", "footer", "page_number", "noise"}
    ]
    ordered = sorted(content, key=lambda region: (_bbox(region)[1], _bbox(region)[0]))
    reading_order = [region.region_id for region in ordered]
    order_by_id = {region_id: index for index, region_id in enumerate(reading_order)}
    return [
        region.model_copy(update={"order_index": order_by_id.get(region.region_id)})
        for region in regions
    ], reading_order


def _basic_region_type(
    text: str,
    bbox: tuple[float, float, float, float],
    page_height: float,
) -> str:
    normalized = " ".join(text.split())
    if bbox[3] <= page_height * 0.085:
        return "header"
    if bbox[1] >= page_height * 0.92:
        return "page_number" if _PAGE_NUMBER.fullmatch(normalized) else "footer"
    if _HEADING.match(normalized):
        return "title"
    if _LIST.match(normalized):
        return "list"
    return "body"


def _validate_page_geometry(source_page: fitz.Page, input_page: fitz.Page) -> None:
    source = (float(source_page.rect.width), float(source_page.rect.height))
    target = (float(input_page.rect.width), float(input_page.rect.height))
    if any(abs(left - right) > 0.05 for left, right in zip(source, target, strict=True)):
        raise ValueError("OCR fixture page geometry differs from its native source page")


def _document_path(repository_root: Path, document: CorpusDocument) -> Path:
    if document.repository_relative_path is None:
        raise ValueError(f"document has no repository path: {document.document_id}")
    path = (repository_root / Path(document.repository_relative_path)).resolve()
    if not path.is_relative_to(repository_root):
        raise ValueError("dataset document path escapes repository root")
    return path


def _dataset_path(dataset_root: Path, repository_relative_path: str) -> Path:
    prefix = "datasets/courserag_eval/v1/"
    path = (dataset_root / repository_relative_path.removeprefix(prefix)).resolve()
    if not path.is_relative_to(dataset_root):
        raise ValueError("P05 dataset path escapes the dataset root")
    return path


def _verify_document(path: Path, document: CorpusDocument) -> None:
    if not path.is_file() or sha256_file(path) != document.sha256:
        raise ValueError(f"document Hash differs from Approved DS0: {document.document_id}")


def _hashed_artifact(
    path: Path,
    repository_root: Path,
    media_type: str = "application/pdf",
) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_relative_to(repository_root):
        raise ValueError("P05 lineage Artifact is outside the repository")
    return HashedArtifact(
        path=resolved.relative_to(repository_root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type=media_type,
    )


def _review_html(records: list[tuple[OCRGold, str]]) -> str:
    sections: list[str] = []
    for record, filename in records:
        boxes = "".join(_review_box(record, region) for region in record.regions)
        excluded = "".join(
            f"<li><code>{html.escape(region.role)}</code> — "
            f"{html.escape((region.gold_text or '[image region]')[:240])}</li>"
            for region in record.regions
            if not region.include_in_body_text
        )
        inherited = (
            f"inherited={html.escape(record.inherited_page_gold_record_id or 'new annotation')}"
        )
        sections.append(
            f"<section><h2>{record.record_id}</h2>"
            f"<p>input={record.ocr_input_document_id} page={record.ocr_input_page_number}; "
            f"source page={record.source_span.page_start}; {inherited}; "
            f"image sha256={record.image_sha256}</p>"
            f'<div class="page"><img src="{html.escape(filename)}">{boxes}</div>'
            f"<h3>正文投影（CER Gold）</h3><pre>{html.escape(record.gold_text)}</pre>"
            f"<h3>不进入正文的区域</h3><ul>{excluded}</ul></section>"
        )
    return (
        """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>P05 OCR Candidate r3 review</title><style>
body{font-family:system-ui,sans-serif;margin:24px;max-width:1200px}section{border-top:2px solid #333;padding:24px 0}
.page{position:relative;display:inline-block;max-width:100%}.page img{display:block;max-width:100%;height:auto}
.box{position:absolute;border:2px solid #2e7d32;box-sizing:border-box;pointer-events:none}.box.excluded{border-color:#c62828}.box.figure,.box.figure_caption{border-color:#1565c0}.box.qr_related{border-color:#6a1b9a}
pre{white-space:pre-wrap;background:#f5f5f5;padding:12px}code{font-weight:700}
</style></head><body><h1>P05 OCR Candidate r3（未批准）</h1>
<p>绿框进入正文 CER；红/蓝/紫框保留原始坐标但不进入正文。请重点核对角色、正文投影和图文阅读顺序。</p>
"""
        + "".join(sections)
        + "</body></html>\n"
    )


def _review_box(record: OCRGold, region: OCRRegion) -> str:
    classes = f"box {html.escape(region.role)}"
    if not region.include_in_body_text:
        classes += " excluded"
    title = f"{region.role}: {(region.gold_text or '[image region]')[:200]}"
    return (
        f'<div class="{classes}" style="left:{region.bbox[0] * 100 / record.image_width:.6f}%;'
        f"top:{region.bbox[1] * 100 / record.image_height:.6f}%;"
        f"width:{(region.bbox[2] - region.bbox[0]) * 100 / record.image_width:.6f}%;"
        f"height:{(region.bbox[3] - region.bbox[1]) * 100 / record.image_height:.6f}%"
        f' title="{html.escape(title, quote=True)}"></div>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the source-grounded P05 OCR Candidate r3.")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    result = build_p05_ocr_candidate(
        repository_root=args.repository_root,
        dataset_root=args.dataset_root,
        output_root=args.output_root,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
