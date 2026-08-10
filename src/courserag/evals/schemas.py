from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, model_validator

from evaluation.contracts import (
    HashedArtifact,
    HumanReviewMetadata,
    ReviewableRecord,
    Sha256,
    SourceSpan,
    StrictModel,
)


class DatasetEnvelope(StrictModel):
    schema_version: str
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)


class CorpusDocument(ReviewableRecord):
    course_id: str | None = Field(default=None, min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    filename: str = Field(min_length=1, max_length=512)
    repository_relative_path: str | None = Field(default=None, min_length=1, max_length=1024)
    document_role: Literal["primary", "derived_fixture"] = "primary"
    parent_document_id: str | None = Field(default=None, min_length=1, max_length=160)
    mime_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    sha256: Sha256
    document_version: str = Field(min_length=1, max_length=120)
    page_count: int | None = Field(default=None, ge=1)
    page_count_basis: Literal[
        "verified_pdf_page_tree",
        "derived_manifest",
        "file_property_candidate",
        "pending_fixed_renderer",
        "unverified",
    ] = "unverified"
    file_property_page_count: int | None = Field(default=None, ge=1)
    derivation_manifest_sha256: Sha256 | None = None
    mutually_exclusive_variant_group: str | None = Field(default=None, min_length=1, max_length=160)
    included_in: list[str] = Field(default_factory=list)
    redistribution_status: str = Field(default="local_only_unverified", max_length=80)

    @model_validator(mode="after")
    def validate_document_role(self) -> CorpusDocument:
        if self.document_role == "derived_fixture":
            if self.parent_document_id is None or self.derivation_manifest_sha256 is None:
                raise ValueError(
                    "derived fixtures require parent_document_id and derivation_manifest_sha256"
                )
            if self.mutually_exclusive_variant_group is None:
                raise ValueError("derived fixtures require a mutually exclusive variant group")
        elif self.parent_document_id is not None or self.derivation_manifest_sha256 is not None:
            raise ValueError("primary documents cannot declare derivation metadata")
        return self


class DS0CorpusDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds0.v1"] = "courserag.ds0.v1"
    documents: list[CorpusDocument] = Field(default_factory=list)


BBox = tuple[float, float, float, float]


class PageRegion(StrictModel):
    region_id: str = Field(min_length=1, max_length=160)
    region_type: Literal[
        "title",
        "body",
        "list",
        "table",
        "figure",
        "formula",
        "header",
        "footer",
        "page_number",
        "noise",
        "other",
    ]
    text: str | None = Field(default=None, max_length=20_000)
    bbox: BBox | None = None
    block_id: str | None = Field(default=None, max_length=160)
    order_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_bbox(self) -> PageRegion:
        if self.bbox is not None:
            x0, y0, x1, y1 = self.bbox
            if x1 <= x0 or y1 <= y0:
                raise ValueError("region BBox must have positive width and height")
        return self


class PageGold(ReviewableRecord):
    record_type: Literal["page"] = "page"
    document_id: str
    document_version: str
    page_number: int = Field(ge=1)
    page_type: Literal["native_text", "scanned", "hybrid", "complex_layout"]
    needs_ocr: bool
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)
    bbox_coordinate_space: Literal["pdf_points_top_left"] | None = None
    reading_order: list[str] = Field(default_factory=list)
    noise_types: list[str] = Field(default_factory=list)
    regions: list[PageRegion] = Field(default_factory=list)
    noise_regions: list[PageRegion] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_page_annotation(self) -> PageGold:
        dimensions = (self.page_width, self.page_height)
        if (dimensions[0] is None) != (dimensions[1] is None):
            raise ValueError("page_width and page_height must be supplied together")
        if dimensions[0] is not None and self.bbox_coordinate_space is None:
            raise ValueError("page dimensions require an explicit BBox coordinate space")
        all_regions = [*self.regions, *self.noise_regions]
        region_ids = [region.region_id for region in all_regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("Page Gold region IDs must be unique")
        if len(self.reading_order) != len(set(self.reading_order)):
            raise ValueError("Page Gold reading order cannot contain duplicates")
        content_region_ids = {region.region_id for region in self.regions}
        unknown = set(self.reading_order) - content_region_ids
        if unknown:
            raise ValueError("reading order must reference content regions only")
        if self.page_width is not None and self.page_height is not None:
            for region in all_regions:
                if region.bbox is None:
                    continue
                x0, y0, x1, y1 = region.bbox
                if x0 < 0 or y0 < 0 or x1 > self.page_width or y1 > self.page_height:
                    raise ValueError("Page Gold region BBox is outside the page")
        return self


class SectionGold(ReviewableRecord):
    record_type: Literal["section"] = "section"
    document_id: str
    document_version: str
    section_id: str
    title: str
    level: int = Field(ge=1)
    parent_section_id: str | None = None
    source_span: SourceSpan
    first_text: str | None = Field(default=None, max_length=4000)
    last_text: str | None = Field(default=None, max_length=4000)


class TablePageFragment(StrictModel):
    physical_page_index: int = Field(ge=1)
    row_indices: list[int] = Field(min_length=1)
    visible_cells: list[list[str]] = Field(min_length=1)
    continuation_from_previous_page: bool = False
    continuation_to_next_page: bool = False

    @model_validator(mode="after")
    def validate_fragment_rows(self) -> TablePageFragment:
        if len(self.row_indices) != len(self.visible_cells):
            raise ValueError("table page-fragment rows must match row_indices")
        if len(self.row_indices) != len(set(self.row_indices)):
            raise ValueError("table page-fragment row indices must be unique")
        return self


class TableGold(ReviewableRecord):
    record_type: Literal["table"] = "table"
    table_id: str
    source_span: SourceSpan
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    cells: list[list[str]] = Field(min_length=1)
    rendered_page_fragments: list[TablePageFragment] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_rectangular_cells(self) -> TableGold:
        if len(self.cells) != self.row_count:
            raise ValueError("table row_count must equal the number of Gold rows")
        if any(len(row) != self.column_count for row in self.cells):
            raise ValueError("every Gold table row must match column_count")
        if self.rendered_page_fragments:
            if self.source_span.page_start is None or self.source_span.page_end is None:
                raise ValueError("rendered table fragments require a physical page span")
            fragment_pages = [
                fragment.physical_page_index for fragment in self.rendered_page_fragments
            ]
            if len(fragment_pages) != len(set(fragment_pages)):
                raise ValueError("rendered table fragment pages must be unique")
            if min(fragment_pages) != self.source_span.page_start:
                raise ValueError("first table fragment must match source page_start")
            if max(fragment_pages) != self.source_span.page_end:
                raise ValueError("last table fragment must match source page_end")
            for fragment in self.rendered_page_fragments:
                if any(index < 0 or index >= self.row_count for index in fragment.row_indices):
                    raise ValueError("table page-fragment row index is outside the logical grid")
                if any(len(row) != self.column_count for row in fragment.visible_cells):
                    raise ValueError("table page-fragment rows must match column_count")
        return self


class DocxRenderProfile(StrictModel):
    provider: str = Field(min_length=1, max_length=160)
    renderer_version: str = Field(min_length=1, max_length=160)
    font_manifest_sha256: Sha256
    profile_sha256: Sha256


class DocxPaginationGold(ReviewableRecord):
    record_type: Literal["docx_pagination"] = "docx_pagination"
    document_id: str = Field(min_length=1, max_length=160)
    document_version: str = Field(min_length=1, max_length=120)
    render_profile: DocxRenderProfile
    section_path: list[str] = Field(default_factory=list)
    block_id: str = Field(min_length=1, max_length=160)
    source_unit_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_text: str | None = Field(default=None, min_length=1, max_length=4000)
    source_text_sha256: Sha256 | None = None
    paragraph_index: int = Field(ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)
    expected_physical_page_index: int = Field(ge=1)
    expected_display_page_label: str | None = Field(min_length=1, max_length=32)
    expected_section_page_index: int | None = Field(ge=1)
    rendered_pdf_sha256: Sha256
    rendered_pdf_hash_basis: Literal[
        "raw_pdf",
        "canonical_pdf_without_volatile_metadata",
    ] = "raw_pdf"

    @model_validator(mode="after")
    def validate_char_range(self) -> DocxPaginationGold:
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end <= self.char_start
        ):
            raise ValueError("char_end must be greater than char_start")
        if (self.source_text is None) != (self.source_text_sha256 is None):
            raise ValueError("source_text and source_text_sha256 must be supplied together")
        if self.source_text is not None and self.source_text_sha256 is not None:
            actual = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
            if actual != self.source_text_sha256:
                raise ValueError("DOCX pagination source text Hash does not match")
        return self


OCRRegionRole = Literal[
    "title",
    "body",
    "list",
    "table",
    "figure",
    "figure_caption",
    "formula",
    "header",
    "footer",
    "page_number",
    "qr_related",
    "figure_embedded_text",
    "noise",
    "other",
]
BODY_OCR_REGION_ROLES = frozenset({"title", "body", "list", "table", "formula"})


class OCRRegion(StrictModel):
    region_id: str = Field(min_length=1, max_length=160)
    bbox: BBox
    source_bbox_pdf_points: BBox
    role: OCRRegionRole
    gold_text: str | None = Field(default=None, min_length=1, max_length=20_000)
    include_in_body_text: bool
    body_order_index: int | None = Field(default=None, ge=0)
    source_page_region_id: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_role_contract(self) -> OCRRegion:
        if self.include_in_body_text != (self.role in BODY_OCR_REGION_ROLES):
            raise ValueError("OCR Region body inclusion must follow the frozen role policy")
        if self.include_in_body_text and self.gold_text is None:
            raise ValueError("body OCR Regions require Gold text")
        if self.include_in_body_text != (self.body_order_index is not None):
            raise ValueError("body OCR Regions require exactly one body order index")
        if self.role == "figure" and self.gold_text is not None:
            raise ValueError("figure Regions preserve geometry rather than embedded text")
        return self


class OCRGold(ReviewableRecord):
    record_type: Literal["ocr"] = "ocr"
    source_span: SourceSpan
    ocr_input_document_id: str = Field(min_length=1, max_length=160)
    ocr_input_document_version: str = Field(min_length=1, max_length=120)
    ocr_input_document_sha256: Sha256
    ocr_input_page_number: int = Field(ge=1)
    image_sha256: Sha256
    image_width: int = Field(ge=1)
    image_height: int = Field(ge=1)
    dpi: int = Field(ge=72, le=600)
    bbox_coordinate_space: Literal["image_pixels_top_left"] = "image_pixels_top_left"
    source_page_width_points: float = Field(gt=0)
    source_page_height_points: float = Field(gt=0)
    annotation_policy: Literal["p05_body_projection_v2"] = "p05_body_projection_v2"
    raw_text: str = Field(min_length=1)
    raw_text_sha256: Sha256
    gold_text: str = Field(min_length=1)
    gold_text_sha256: Sha256
    remove_spaces_between_chinese: bool = True
    normalize_full_width: bool = True
    ignore_line_break_difference: bool = True
    regions: list[OCRRegion] = Field(default_factory=list)
    reading_order: list[str] = Field(min_length=1)
    inherited_page_gold_record_id: str | None = Field(default=None, min_length=1, max_length=160)
    inherited_page_gold_record_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_ocr_coordinates_and_text(self) -> OCRGold:
        if hashlib.sha256(self.raw_text.encode("utf-8")).hexdigest() != self.raw_text_sha256:
            raise ValueError("OCR raw text Hash does not match exact text")
        if hashlib.sha256(self.gold_text.encode("utf-8")).hexdigest() != self.gold_text_sha256:
            raise ValueError("OCR Gold text Hash does not match exact text")
        if (self.inherited_page_gold_record_id is None) != (
            self.inherited_page_gold_record_sha256 is None
        ):
            raise ValueError("inherited PageGold ID and Hash must be supplied together")
        region_ids = [region.region_id for region in self.regions]
        if len(region_ids) != len(set(region_ids)):
            raise ValueError("OCR Region IDs must be unique")
        if len(self.reading_order) != len(set(self.reading_order)):
            raise ValueError("OCR body reading order cannot contain duplicates")
        body_regions = {
            region.region_id: region for region in self.regions if region.include_in_body_text
        }
        if set(self.reading_order) != set(body_regions):
            raise ValueError("OCR body reading order must contain every body Region exactly once")
        ordered_regions = [body_regions[region_id] for region_id in self.reading_order]
        if [region.body_order_index for region in ordered_regions] != list(
            range(len(ordered_regions))
        ):
            raise ValueError("OCR body Region indexes must match reading_order")
        expected_body = "\n".join(region.gold_text or "" for region in ordered_regions).strip()
        if self.gold_text != expected_body:
            raise ValueError("OCR Gold text must equal the ordered body Region projection")
        for region in self.regions:
            x0, y0, x1, y1 = region.bbox
            if x0 < 0 or y0 < 0 or x1 > self.image_width or y1 > self.image_height:
                raise ValueError("OCR Gold image-pixel BBox is outside the rendered page")
            sx0, sy0, sx1, sy1 = region.source_bbox_pdf_points
            if (
                sx0 < 0
                or sy0 < 0
                or sx1 > self.source_page_width_points
                or sy1 > self.source_page_height_points
            ):
                raise ValueError("OCR Gold source BBox is outside the native source page")
        return self


class P05OCRCandidateManifest(DatasetEnvelope):
    schema_version: Literal["courserag.p05-ocr-candidate-manifest.v2"] = (
        "courserag.p05-ocr-candidate-manifest.v2"
    )
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=15, max_length=15)
    previous_candidate_file_sha256: Sha256
    p04_work_package_sha256: Sha256
    p04_approved_ds1_sha256: Sha256
    inherited_page_gold_record_sha256: dict[str, Sha256] = Field(min_length=11, max_length=11)
    newly_annotated_record_ids: list[str] = Field(min_length=4, max_length=4)
    review_decisions_sha256: Sha256
    source_artifacts: list[HashedArtifact] = Field(min_length=4)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    dpi: Literal[200] = 200
    record_count: Literal[15] = 15
    gold_source: Literal["native_pdf_text_geometry"] = "native_pdf_text_geometry"


class P05OCRBatchApproval(DatasetEnvelope):
    schema_version: Literal["courserag.p05-ocr-batch-approval.v1"] = (
        "courserag.p05-ocr-batch-approval.v1"
    )
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=15, max_length=15)
    approved_relative_path: str = Field(min_length=1, max_length=1024)
    approved_file_sha256: Sha256
    approved_record_sha256: dict[str, Sha256] = Field(min_length=15, max_length=15)
    notes: str = Field(min_length=1, max_length=4000)


ParsingGoldRecord = Annotated[
    PageGold | SectionGold | TableGold | DocxPaginationGold | OCRGold,
    Field(discriminator="record_type"),
]


class DS1ParsingDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds1.v1"] = "courserag.ds1.v1"
    records: list[ParsingGoldRecord] = Field(default_factory=list)


class DS1CandidateManifest(DatasetEnvelope):
    schema_version: Literal["courserag.ds1-candidate-manifest.v1"] = (
        "courserag.ds1-candidate-manifest.v1"
    )
    candidate_revision: int = Field(ge=1)
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=1)
    source_artifacts: list[HashedArtifact] = Field(min_length=1)
    semantic_source_count: Literal[2] = 2
    record_counts: dict[str, int]
    renderer_profile: DocxRenderProfile
    canonical_rendered_pdf_sha256: dict[str, Sha256] = Field(min_length=2, max_length=2)
    raw_rendered_pdf_run_sha256: dict[str, list[Sha256]] = Field(min_length=2, max_length=2)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    second_review_record_ids: list[str] = Field(min_length=1)
    predecessor_candidate_file_sha256: Sha256 | None = None
    review_decisions_artifact: HashedArtifact | None = None
    review_decisions_source_filename: str | None = Field(default=None, min_length=1, max_length=512)
    review_decisions_source_sha256: Sha256 | None = None
    required_rereview_record_ids: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_review_lineage(self) -> DS1CandidateManifest:
        if (self.predecessor_candidate_file_sha256 is None) != (
            self.review_decisions_artifact is None
        ):
            raise ValueError("Candidate predecessor and review artifact must be supplied together")
        review_source_fields = (
            self.review_decisions_source_filename,
            self.review_decisions_source_sha256,
        )
        if self.review_decisions_artifact is None and any(
            value is not None for value in review_source_fields
        ):
            raise ValueError("review source metadata requires a review artifact")
        if self.review_decisions_artifact is not None and any(
            value is None for value in review_source_fields
        ):
            raise ValueError("review artifact requires source filename and source Hash")
        if len(self.required_rereview_record_ids) != len(set(self.required_rereview_record_ids)):
            raise ValueError("required re-review record IDs must be unique")
        if not set(self.required_rereview_record_ids).issubset(self.candidate_record_sha256):
            raise ValueError("required re-review IDs must reference Candidate records")
        return self


class DS1ReviewDecisions(StrictModel):
    schema_version: Literal["courserag.ds1-review-decisions.v1"] = (
        "courserag.ds1-review-decisions.v1"
    )
    candidate_file_sha256: Sha256
    reviewed_record_ids: list[str] = Field(min_length=1)
    returned_record_ids: list[str] = Field(default_factory=list)
    record_count: int = Field(ge=1)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_reviewed_ids(self) -> DS1ReviewDecisions:
        if len(self.reviewed_record_ids) != len(set(self.reviewed_record_ids)):
            raise ValueError("reviewed record IDs must be unique")
        if len(self.returned_record_ids) != len(set(self.returned_record_ids)):
            raise ValueError("returned record IDs must be unique")
        if set(self.reviewed_record_ids) & set(self.returned_record_ids):
            raise ValueError("reviewed and returned record IDs must be disjoint")
        if len(self.reviewed_record_ids) + len(self.returned_record_ids) > self.record_count:
            raise ValueError("review decision count cannot exceed Candidate record_count")
        return self


class DS1BatchApproval(DatasetEnvelope):
    schema_version: Literal["courserag.ds1-batch-approval.v1"] = "courserag.ds1-batch-approval.v1"
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=1)
    approved_relative_path: str = Field(min_length=1, max_length=1024)
    approved_file_sha256: Sha256
    approved_record_sha256: dict[str, Sha256] = Field(min_length=1)
    notes: str = Field(default="", max_length=4000)


class EvidenceBBox(StrictModel):
    page_number: int = Field(ge=1)
    bbox: BBox
    page_width: float | None = Field(default=None, gt=0)
    page_height: float | None = Field(default=None, gt=0)
    coordinate_space: (
        Literal[
            "pdf_points_top_left",
            "rendered_pdf_points_top_left",
        ]
        | None
    ) = None
    rendered_pdf_sha256: Sha256 | None = None
    source_region_id: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_coordinates(self) -> EvidenceBBox:
        x0, y0, x1, y1 = self.bbox
        if x1 <= x0 or y1 <= y0:
            raise ValueError("Evidence BBox must have positive width and height")
        dimensions = (self.page_width, self.page_height)
        if (dimensions[0] is None) != (dimensions[1] is None):
            raise ValueError("Evidence BBox page dimensions must be supplied together")
        if self.page_width is not None and self.page_height is not None:
            if self.coordinate_space is None:
                raise ValueError("bounded Evidence BBoxes require a coordinate space")
            if x0 < 0 or y0 < 0 or x1 > self.page_width or y1 > self.page_height:
                raise ValueError("Evidence BBox is outside the source page")
        if self.coordinate_space == "rendered_pdf_points_top_left":
            if self.rendered_pdf_sha256 is None:
                raise ValueError("rendered-PDF Evidence BBoxes require the rendered PDF Hash")
        elif self.rendered_pdf_sha256 is not None:
            raise ValueError("native-PDF Evidence BBoxes cannot bind a rendered PDF Hash")
        return self


class EvidenceSourceUnit(StrictModel):
    source_unit_id: str = Field(min_length=1, max_length=240)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)
    text_sha256: Sha256

    @model_validator(mode="after")
    def validate_char_range(self) -> EvidenceSourceUnit:
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("Evidence source-unit character bounds must be supplied together")
        if self.char_start is not None and self.char_end is not None:
            if self.char_end <= self.char_start:
                raise ValueError("Evidence source-unit char_end must be greater than char_start")
        return self


class UpstreamApprovedRecordRef(StrictModel):
    dataset_component: Literal["ds1_p04_native_docx", "ds1_p05_ocr"]
    record_type: Literal["page", "section", "table", "ocr"]
    record_id: str = Field(min_length=1, max_length=160)
    record_sha256: Sha256


class EvidenceNeighbor(StrictModel):
    relation: Literal["parent_heading", "previous", "next"]
    source_span: SourceSpan
    text: str = Field(min_length=1, max_length=20_000)
    text_sha256: Sha256

    @model_validator(mode="after")
    def validate_text_hash(self) -> EvidenceNeighbor:
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("Evidence neighbor Hash does not match exact text")
        return self


class EvidenceOCRProvenance(StrictModel):
    approved_ocr_record_id: str = Field(min_length=1, max_length=160)
    approved_ocr_record_sha256: Sha256
    ocr_input_document_id: str = Field(min_length=1, max_length=160)
    ocr_input_document_version: str = Field(min_length=1, max_length=120)
    ocr_input_document_sha256: Sha256
    ocr_input_page_number: int = Field(ge=1)
    source_page_number: int = Field(ge=1)
    source_region_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_region_ids(self) -> EvidenceOCRProvenance:
        if len(self.source_region_ids) != len(set(self.source_region_ids)):
            raise ValueError("OCR provenance Region IDs must be unique")
        return self


class EvidenceRecord(ReviewableRecord):
    evidence_id: str = Field(min_length=1, max_length=160)
    annotation_profile: Literal["legacy_v1", "formal_ds2_v1"] = "legacy_v1"
    course_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_span: SourceSpan
    source_type: Literal[
        "native_text",
        "ocr",
        "ocr_derived",
        "verified_content",
        "synthetic",
    ]
    gold_text: str = Field(min_length=1, max_length=20_000)
    content_sha256: Sha256
    normalized_content_sha256: Sha256 | None = None
    source_units: list[EvidenceSourceUnit] = Field(default_factory=list)
    text_assembly: (
        Literal[
            "single_source_unit",
            "ordered_source_units_newline",
            "table_tsv",
            "ocr_regions_newline",
            "rendered_formula_linearization",
        ]
        | None
    ) = None
    upstream_record_refs: list[UpstreamApprovedRecordRef] = Field(default_factory=list)
    semantic_unit_type: Literal[
        "definition",
        "principle",
        "procedure",
        "list",
        "table",
        "example",
        "comparison",
        "formula",
        "application",
        "other",
    ]
    requires_parent: bool = False
    necessary_neighbor_text: list[str] = Field(default_factory=list)
    necessary_neighbors: list[EvidenceNeighbor] = Field(default_factory=list)
    bboxes: list[EvidenceBBox] = Field(default_factory=list)
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    ocr_provenance: EvidenceOCRProvenance | None = None
    other_type_review_reason: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_evidence_identity_and_provenance(self) -> EvidenceRecord:
        normalized_text = " ".join(unicodedata.normalize("NFKC", self.gold_text).split())
        normalized_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        if self.normalized_content_sha256 is not None:
            if self.normalized_content_sha256 != normalized_hash:
                raise ValueError("Evidence normalized content Hash does not match Gold text")
        if self.source_type == "ocr_derived":
            if self.annotation_profile == "formal_ds2_v1" and self.ocr_provenance is None:
                raise ValueError("OCR-derived Evidence requires approved OCR provenance")
        elif self.ocr_provenance is not None:
            raise ValueError("only OCR-derived Evidence may carry OCR provenance")
        if self.semantic_unit_type == "other" and self.annotation_profile == "formal_ds2_v1":
            if self.other_type_review_reason is None:
                raise ValueError("formal 'other' Evidence requires a review reason")
        elif self.semantic_unit_type != "other" and self.other_type_review_reason is not None:
            raise ValueError("only 'other' Evidence may carry an other-type review reason")
        if self.annotation_profile == "formal_ds2_v1":
            exact_hash = hashlib.sha256(self.gold_text.encode("utf-8")).hexdigest()
            if exact_hash != self.content_sha256:
                raise ValueError("Evidence content Hash does not match exact Gold text")
            if self.record_id != self.evidence_id:
                raise ValueError("formal Evidence record_id must equal its stable evidence_id")
            if self.course_id is None:
                raise ValueError("formal Evidence requires course_id")
            if self.normalized_content_sha256 is None:
                raise ValueError("formal Evidence requires the normalized content Hash")
            if not self.source_units or self.text_assembly is None or not self.bboxes:
                raise ValueError("formal Evidence requires source units, assembly and BBoxes")
            if self.ocr_confidence is not None:
                raise ValueError("formal Gold must not contain Provider OCR confidence")
            unit_ids = [unit.source_unit_id for unit in self.source_units]
            if len(unit_ids) != len(set(unit_ids)):
                raise ValueError("formal Evidence source-unit IDs must be unique")
        return self


class DS2EvidenceDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds2.v1"] = "courserag.ds2.v1"
    evidence: list[EvidenceRecord] = Field(default_factory=list)


class DS2ReviewGroup(StrictModel):
    group_id: Literal["group-01", "group-02", "group-03", "group-04"]
    title: str = Field(min_length=1, max_length=240)
    record_ids: list[str] = Field(min_length=30, max_length=30)

    @model_validator(mode="after")
    def validate_record_ids(self) -> DS2ReviewGroup:
        if len(self.record_ids) != len(set(self.record_ids)):
            raise ValueError("DS2 review-group record IDs must be unique")
        return self


class DS2CandidateManifest(DatasetEnvelope):
    schema_version: Literal["courserag.ds2-candidate-manifest.v1"] = (
        "courserag.ds2-candidate-manifest.v1"
    )
    candidate_revision: int = Field(ge=1)
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=120, max_length=120)
    source_artifacts: list[HashedArtifact] = Field(min_length=6)
    upstream_approved_file_sha256: dict[str, Sha256] = Field(min_length=2, max_length=2)
    semantic_source_count: Literal[2] = 2
    record_counts: dict[str, int]
    section_record_counts: dict[str, int] = Field(min_length=24, max_length=24)
    semantic_type_counts: dict[str, int]
    review_groups: list[DS2ReviewGroup] = Field(min_length=4, max_length=4)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    review_asset_sha256: dict[str, Sha256] = Field(min_length=120)
    renderer_profile: DocxRenderProfile
    canonical_rendered_pdf_sha256: Sha256
    stable_id_profile_sha256: Sha256
    normalization_profile_sha256: Sha256
    predecessor_candidate_file_sha256: Sha256 | None = None
    review_decisions_artifact: HashedArtifact | None = None
    retained_reviewed_record_ids: list[str] = Field(default_factory=list)
    required_rereview_record_ids: list[str] = Field(default_factory=list)
    duplicate_review_record_ids: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_candidate_manifest(self) -> DS2CandidateManifest:
        group_ids = [group.group_id for group in self.review_groups]
        if group_ids != ["group-01", "group-02", "group-03", "group-04"]:
            raise ValueError("DS2 review groups must use the frozen four-group order")
        grouped = [record_id for group in self.review_groups for record_id in group.record_ids]
        if len(grouped) != 120 or len(grouped) != len(set(grouped)):
            raise ValueError("DS2 review groups must cover 120 unique records")
        if set(grouped) != set(self.candidate_record_sha256):
            raise ValueError("DS2 review groups must cover every Candidate record")
        if set(self.review_asset_sha256) != set(self.candidate_record_sha256):
            raise ValueError("DS2 review assets must cover every Candidate record")
        if not set(self.required_rereview_record_ids).issubset(self.candidate_record_sha256):
            raise ValueError("DS2 re-review IDs must reference Candidate records")
        if not set(self.retained_reviewed_record_ids).issubset(self.candidate_record_sha256):
            raise ValueError("retained DS2 review IDs must reference Candidate records")
        if set(self.retained_reviewed_record_ids) & set(self.required_rereview_record_ids):
            raise ValueError("retained and required DS2 review IDs must be disjoint")
        if len(self.retained_reviewed_record_ids) != len(set(self.retained_reviewed_record_ids)):
            raise ValueError("retained DS2 review IDs must be unique")
        if not set(self.duplicate_review_record_ids).issubset(self.candidate_record_sha256):
            raise ValueError("DS2 duplicate-review IDs must reference Candidate records")
        if (
            self.review_decisions_artifact is not None
            and self.predecessor_candidate_file_sha256 is None
        ):
            raise ValueError("DS2 review artifacts require a predecessor Candidate")
        return self


class DS2ReviewDecisions(StrictModel):
    schema_version: Literal["courserag.ds2-review-decisions.v1"] = (
        "courserag.ds2-review-decisions.v1"
    )
    candidate_file_sha256: Sha256
    reviewed_record_ids: list[str] = Field(default_factory=list)
    returned_record_ids: list[str] = Field(default_factory=list)
    completed_group_ids: list[Literal["group-01", "group-02", "group-03", "group-04"]] = Field(
        default_factory=list
    )
    record_count: Literal[120] = 120
    record_notes: dict[str, str] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_reviewed_ids(self) -> DS2ReviewDecisions:
        reviewed = self.reviewed_record_ids
        returned = self.returned_record_ids
        if len(reviewed) != len(set(reviewed)) or len(returned) != len(set(returned)):
            raise ValueError("DS2 review decision record IDs must be unique")
        if set(reviewed) & set(returned):
            raise ValueError("reviewed and returned DS2 record IDs must be disjoint")
        if len(reviewed) + len(returned) > self.record_count:
            raise ValueError("DS2 review decisions exceed the Candidate record count")
        if len(self.completed_group_ids) != len(set(self.completed_group_ids)):
            raise ValueError("completed DS2 review groups must be unique")
        if not set(self.record_notes).issubset(set(reviewed) | set(returned)):
            raise ValueError("DS2 review notes must reference a decided record")
        return self


class DS2BatchApproval(DatasetEnvelope):
    schema_version: Literal["courserag.ds2-batch-approval.v1"] = "courserag.ds2-batch-approval.v1"
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=120, max_length=120)
    review_decisions_artifact: HashedArtifact
    approved_relative_path: str = Field(min_length=1, max_length=1024)
    approved_file_sha256: Sha256
    approved_record_sha256: dict[str, Sha256] = Field(min_length=120, max_length=120)
    notes: str = Field(min_length=1, max_length=4000)


class KnowledgePointEvidenceLink(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    role: Literal[
        "definition",
        "principle",
        "method",
        "process",
        "formula",
        "example",
        "application",
        "constraint",
        "comparison",
        "support",
    ]
    is_primary: bool = False
    evidence_record_sha256: Sha256


class KnowledgePointAliasAnnotation(StrictModel):
    alias: str = Field(min_length=1, max_length=240)
    basis: Literal["source_text", "deterministic_normalization"]
    evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_alias_basis(self) -> KnowledgePointAliasAnnotation:
        if self.basis == "source_text" and not self.evidence_ids:
            raise ValueError("source-text aliases require at least one Evidence reference")
        if self.basis == "deterministic_normalization" and self.evidence_ids:
            raise ValueError("mechanical aliases cannot claim source Evidence")
        return self


class DS3SectionScope(StrictModel):
    scope_id: str = Field(min_length=1, max_length=160)
    course_id: str = Field(min_length=1, max_length=160)
    section_path: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=500)
    source_span: SourceSpan
    source_text: str = Field(min_length=1, max_length=500_000)
    source_text_sha256: Sha256
    upstream_section_record_id: str | None = Field(default=None, max_length=160)
    upstream_section_record_sha256: Sha256 | None = None
    excluded_child_section_paths: list[str] = Field(default_factory=list)
    requires_boundary_review: bool = False

    @model_validator(mode="after")
    def validate_source_text_hash(self) -> DS3SectionScope:
        digest = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
        if digest != self.source_text_sha256:
            raise ValueError("DS3 Section source text hash does not match source_text")
        return self


class DS3SectionScopeDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds3-section-scopes.v1"] = "courserag.ds3-section-scopes.v1"
    scopes: list[DS3SectionScope] = Field(min_length=24, max_length=24)

    @model_validator(mode="after")
    def validate_scope_identity(self) -> DS3SectionScopeDataset:
        ids = [item.scope_id for item in self.scopes]
        keys = [(item.course_id, item.section_path) for item in self.scopes]
        if len(ids) != len(set(ids)) or len(keys) != len(set(keys)):
            raise ValueError("DS3 Section scopes must be unique")
        return self


class KnowledgePointRecord(ReviewableRecord):
    gold_kp_id: str
    course_id: str
    canonical_name: str = Field(min_length=1, max_length=240)
    aliases: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=4000)
    parent_gold_kp_id: str | None = None
    section_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    importance: Literal["core", "supporting", "optional"]
    granularity: Literal["atomic", "composite", "too_broad", "too_narrow"]
    annotation_profile: Literal["formal_ds3_v1"] | None = None
    normalized_name: str | None = Field(default=None, max_length=240)
    concept_family_id: str | None = Field(default=None, max_length=160)
    evidence_links: list[KnowledgePointEvidenceLink] = Field(default_factory=list)
    alias_annotations: list[KnowledgePointAliasAnnotation] = Field(default_factory=list)
    source_scope_ids: list[str] = Field(default_factory=list)
    merge_conflict_ids: list[str] = Field(default_factory=list)
    annotation_rationale: str | None = Field(default=None, max_length=2000)
    cross_section_rationale: str | None = Field(default=None, max_length=2000)
    composite_rationale: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_formal_annotation(self) -> KnowledgePointRecord:
        if self.parent_gold_kp_id == self.gold_kp_id:
            raise ValueError("a knowledge point cannot be its own parent")
        if self.annotation_profile is None:
            return self
        if self.record_id != self.gold_kp_id:
            raise ValueError("formal DS3 record_id must equal gold_kp_id")
        required = (self.normalized_name, self.concept_family_id, self.annotation_rationale)
        if any(value is None for value in required):
            raise ValueError("formal DS3 records require normalized name, family, and rationale")
        if not self.evidence_links or not any(link.is_primary for link in self.evidence_links):
            raise ValueError("formal DS3 records require a primary Evidence link")
        if self.evidence_ids != [link.evidence_id for link in self.evidence_links]:
            raise ValueError("evidence_ids must preserve evidence_links order")
        if self.aliases != [item.alias for item in self.alias_annotations]:
            raise ValueError("aliases must preserve alias annotation order")
        if not self.section_ids or not self.source_scope_ids:
            raise ValueError("formal DS3 records require Section and source scope references")
        if self.granularity not in {"atomic", "composite"}:
            raise ValueError(
                "formal DS3 Candidate only accepts atomic or justified composite items"
            )
        if self.granularity == "composite" and not self.composite_rationale:
            raise ValueError("composite knowledge points require a rationale")
        return self


class DS3KnowledgePointDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds3.v1"] = "courserag.ds3.v1"
    knowledge_points: list[KnowledgePointRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_formal_graph(self) -> DS3KnowledgePointDataset:
        records = {item.gold_kp_id: item for item in self.knowledge_points}
        if len(records) != len(self.knowledge_points):
            raise ValueError("DS3 knowledge point IDs must be unique")
        for item in self.knowledge_points:
            if item.parent_gold_kp_id is None:
                continue
            parent = records.get(item.parent_gold_kp_id)
            if parent is None or parent.course_id != item.course_id:
                raise ValueError("DS3 parents must resolve inside the same course")
            seen = {item.gold_kp_id}
            cursor: KnowledgePointRecord | None = parent
            while cursor is not None:
                if cursor.gold_kp_id in seen:
                    raise ValueError("DS3 parent graph must be acyclic")
                seen.add(cursor.gold_kp_id)
                cursor = records.get(cursor.parent_gold_kp_id) if cursor.parent_gold_kp_id else None
        return self


class DS3ReviewGroup(StrictModel):
    group_id: Literal["group-01", "group-02", "group-03", "group-04"]
    section_scope_ids: list[str] = Field(min_length=6, max_length=6)
    knowledge_point_ids: list[str] = Field(min_length=1)


class DS3SplitManifest(DatasetEnvelope):
    schema_version: Literal["courserag.ds3-split.v1"] = "courserag.ds3-split.v1"
    calibration_ids: list[str] = Field(min_length=1)
    holdout_ids: list[str] = Field(min_length=1)
    family_assignments: dict[str, Literal["calibration", "holdout"]] = Field(min_length=1)
    target_calibration_ratio: float = Field(default=0.7, ge=0.7, le=0.7)
    actual_calibration_ratio: float = Field(ge=0.6, le=0.8)
    algorithm_profile_sha256: Sha256

    @model_validator(mode="after")
    def validate_split(self) -> DS3SplitManifest:
        if set(self.calibration_ids) & set(self.holdout_ids):
            raise ValueError("DS3 calibration and holdout IDs must be disjoint")
        if len(self.calibration_ids) != len(set(self.calibration_ids)) or len(
            self.holdout_ids
        ) != len(set(self.holdout_ids)):
            raise ValueError("DS3 split IDs must be unique")
        return self


class P07GoldBundleManifest(DatasetEnvelope):
    schema_version: Literal["courserag.p07-gold-bundle-manifest.v1"] = (
        "courserag.p07-gold-bundle-manifest.v1"
    )
    bundle_sha256: Sha256
    knowledge_point_candidate: HashedArtifact
    support_candidate: HashedArtifact
    section_scopes: HashedArtifact
    split_manifest: HashedArtifact
    generation_policy: HashedArtifact
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=80, max_length=120)
    support_record_sha256: dict[str, Sha256] = Field(default_factory=dict)
    source_artifacts: list[HashedArtifact] = Field(min_length=2)
    upstream_approved_file_sha256: dict[str, Sha256] = Field(min_length=3)
    preserved_p06_artifact_sha256: dict[str, Sha256] = Field(min_length=3)
    review_groups: list[DS3ReviewGroup] = Field(min_length=4, max_length=4)
    first_review_ids: list[str] = Field(min_length=80, max_length=120)
    second_review_ids: list[str] = Field(min_length=1)
    second_review_reasons: dict[str, list[str]] = Field(default_factory=dict)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    second_review_index_sha256: Sha256
    review_asset_sha256: dict[str, Sha256] = Field(min_length=80, max_length=120)
    semantic_source_count: Literal[2] = 2
    constraints: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bundle_coverage(self) -> P07GoldBundleManifest:
        ids = set(self.candidate_record_sha256)
        if set(self.first_review_ids) != ids or len(self.first_review_ids) != len(ids):
            raise ValueError("first DS3 review must cover every Candidate record")
        if not set(self.second_review_ids).issubset(ids):
            raise ValueError("second DS3 review IDs must reference Candidate records")
        grouped = [item for group in self.review_groups for item in group.knowledge_point_ids]
        if set(grouped) != ids or len(grouped) != len(ids):
            raise ValueError("four DS3 review groups must cover every Candidate once")
        if set(self.review_asset_sha256) != ids:
            raise ValueError("DS3 review assets must cover every Candidate record")
        return self


class DS3ReviewDecisions(StrictModel):
    schema_version: Literal["courserag.ds3-review-decisions.v1"] = (
        "courserag.ds3-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    reviewer_id: str | None = Field(default=None, min_length=1, max_length=160)
    reviewed_at: datetime | None = None
    attestation_source: (
        Literal["offline_review_package", "course_owner_conversation_attestation"] | None
    ) = None
    expected_record_ids: list[str] = Field(min_length=1)
    reviewed_record_ids: list[str] = Field(default_factory=list)
    returned_record_ids: list[str] = Field(default_factory=list)
    record_notes: dict[str, str] = Field(default_factory=dict)
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_decisions(self) -> DS3ReviewDecisions:
        expected = set(self.expected_record_ids)
        accepted = set(self.reviewed_record_ids)
        returned = set(self.returned_record_ids)
        if len(expected) != len(self.expected_record_ids):
            raise ValueError("expected review IDs must be unique")
        if accepted & returned or not (accepted | returned).issubset(expected):
            raise ValueError("review decisions must be disjoint and expected")
        if not set(self.record_notes).issubset(accepted | returned):
            raise ValueError("review notes must reference decided records")
        return self


class P07GoldBundleApproval(DatasetEnvelope):
    schema_version: Literal["courserag.p07-gold-bundle-approval.v1"] = (
        "courserag.p07-gold-bundle-approval.v1"
    )
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    bundle_sha256: Sha256
    knowledge_point_candidate: HashedArtifact
    support_candidate: HashedArtifact
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=80, max_length=120)
    support_record_sha256: dict[str, Sha256] = Field(default_factory=dict)
    first_review_decisions: HashedArtifact
    second_review_decisions: HashedArtifact
    approved_knowledge_points: HashedArtifact
    approved_support: HashedArtifact
    approved_record_sha256: dict[str, Sha256] = Field(min_length=80, max_length=120)
    approved_support_record_sha256: dict[str, Sha256] = Field(default_factory=dict)
    notes: str = Field(min_length=1, max_length=4000)


class QueryProcessingExpected(StrictModel):
    normalized_query: str
    linked_knowledge_points: list[str] = Field(default_factory=list)
    filters: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)
    route: str
    allowed_expansions: list[str] = Field(default_factory=list)
    forbidden_expansions: list[str] = Field(default_factory=list)
    must_preserve_terms: list[str] = Field(default_factory=list)
    must_preserve_filters: bool = True


class QueryProcessingCase(ReviewableRecord):
    raw_query: str = Field(min_length=1, max_length=4000)
    expected: QueryProcessingExpected
    course_id: str | None = Field(default=None, min_length=1, max_length=160)
    capability: (
        Literal[
            "query_normalization",
            "knowledge_point_linking",
            "filter_parsing",
            "query_router",
            "expansion_rewrite_constraints",
        ]
        | None
    ) = None
    query_family_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_package_id: str | None = Field(default=None, min_length=1, max_length=160)
    mirrored_ds5_case_id: str | None = Field(default=None, min_length=1, max_length=160)
    upstream_approved_sha256: dict[str, Sha256] = Field(default_factory=dict)
    query_sha256: Sha256 | None = None
    generation_strategy_sha256: Sha256 | None = None
    approval_scope: Literal["ds4_query_processing_and_ds5_retrieval_only"] | None = None

    @model_validator(mode="after")
    def validate_formal_p08_case(self) -> QueryProcessingCase:
        formal_values = (
            self.course_id,
            self.capability,
            self.query_family_id,
            self.source_package_id,
            self.query_sha256,
            self.generation_strategy_sha256,
            self.approval_scope,
        )
        if any(value is not None for value in formal_values):
            if any(value is None for value in formal_values):
                raise ValueError("formal P08 DS4 cases require all provenance fields")
            actual = hashlib.sha256(self.raw_query.encode("utf-8")).hexdigest()
            if self.query_sha256 != actual:
                raise ValueError("DS4 query_sha256 must bind raw_query exactly")
            if not self.upstream_approved_sha256:
                raise ValueError("formal P08 DS4 cases require upstream Approved hashes")
        return self


class DS4QueryProcessingDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds4.v1"] = "courserag.ds4.v1"
    cases: list[QueryProcessingCase] = Field(default_factory=list)


class ClaimEvidenceSupport(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    evidence_record_sha256: Sha256
    support_role: Literal["primary", "supporting"]
    support_source: Literal["evidence_text", "necessary_neighbor"] = "evidence_text"
    necessary_neighbor_id: str | None = Field(default=None, min_length=1, max_length=160)
    exact_support_excerpt: str = Field(min_length=1, max_length=20_000)
    exact_support_excerpt_sha256: Sha256

    @model_validator(mode="after")
    def validate_excerpt_hash(self) -> ClaimEvidenceSupport:
        actual = hashlib.sha256(self.exact_support_excerpt.encode("utf-8")).hexdigest()
        if self.exact_support_excerpt_sha256 != actual:
            raise ValueError("Claim support excerpt Hash must bind exact source text")
        if self.support_source == "evidence_text" and self.necessary_neighbor_id is not None:
            raise ValueError("Evidence-text Claim support cannot name a necessary neighbor")
        if self.support_source == "necessary_neighbor" and self.necessary_neighbor_id is None:
            raise ValueError("Neighbor Claim support must name the necessary neighbor")
        return self


class GoldClaim(StrictModel):
    claim_id: str
    claim_text: str = Field(min_length=1, max_length=8000)
    importance: Literal["required", "optional"] = "required"
    required_evidence_ids: list[str] = Field(min_length=1)
    claim_text_sha256: Sha256 | None = None
    normalized_claim_sha256: Sha256 | None = None
    evidence_supports: list[ClaimEvidenceSupport] = Field(default_factory=list)
    annotation_rationale: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_formal_p09_claim(self) -> GoldClaim:
        formal_values = (
            self.claim_text_sha256,
            self.normalized_claim_sha256,
            self.annotation_rationale,
        )
        if self.evidence_supports or any(value is not None for value in formal_values):
            if not self.evidence_supports or any(value is None for value in formal_values):
                raise ValueError("formal P09 Claims require hashes, supports and rationale")
            exact = hashlib.sha256(self.claim_text.encode("utf-8")).hexdigest()
            normalized = " ".join(unicodedata.normalize("NFKC", self.claim_text).split())
            normalized_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            if self.claim_text_sha256 != exact or self.normalized_claim_sha256 != normalized_hash:
                raise ValueError("formal P09 Claim hashes must bind Claim text")
            support_ids = [item.evidence_id for item in self.evidence_supports]
            if len(support_ids) != len(set(support_ids)):
                raise ValueError("formal P09 Claim Evidence supports must be unique")
            if set(support_ids) != set(self.required_evidence_ids):
                raise ValueError("formal P09 Claim support IDs must match required Evidence IDs")
        return self


class EvidenceGroup(StrictModel):
    group_id: str
    sufficiency: Literal["complete", "partial"]
    required_evidence_ids: list[str] = Field(min_length=1)


class RetrievalEvidenceJudgment(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    relevance: Literal[0, 1, 2]
    role: Literal["required", "helpful", "hard_negative"]
    evidence_record_sha256: Sha256
    rationale: str = Field(min_length=1, max_length=2000)


class UnanswerableRetrievalAudit(StrictModel):
    audit_scope: Literal["entire_course_approved_ds2"] = "entire_course_approved_ds2"
    search_terms: list[str] = Field(min_length=1, max_length=20)
    search_rules: list[str] = Field(min_length=1, max_length=20)
    exact_match_count: int = Field(ge=0)
    nearest_false_positive_evidence_ids: list[str] = Field(min_length=1, max_length=5)
    human_confirmation_items: list[str] = Field(min_length=1, max_length=20)


class RetrievalQACase(ReviewableRecord):
    query: str = Field(min_length=1, max_length=4000)
    query_type: Literal[
        "exact_fact",
        "definition",
        "paraphrase",
        "comparison",
        "procedure",
        "application",
        "cross_section",
        "unanswerable",
    ]
    answerable: bool
    difficulty: Literal["easy", "medium", "hard"]
    gold_answer_type: Literal[
        "factoid",
        "list",
        "explanatory",
        "comparison",
        "procedure",
        "unanswerable",
        "pending_p09",
    ]
    gold_short_answers: list[str] = Field(default_factory=list)
    gold_claims: list[GoldClaim] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_knowledge_points: list[str] = Field(default_factory=list)
    filters: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)
    gold_evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    graded_relevance: dict[str, Literal[0, 1, 2]] = Field(default_factory=dict)
    allowed_answer_variants: list[str] = Field(default_factory=list)
    expected_behavior: (
        Literal[
            "answer",
            "no_relevant_evidence",
            "abstained_insufficient_evidence",
        ]
        | None
    ) = None
    properties: dict[str, bool] = Field(default_factory=dict)
    course_id: str | None = Field(default=None, min_length=1, max_length=160)
    query_family_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_package_id: str | None = Field(default=None, min_length=1, max_length=160)
    split: Literal["dev", "test"] | None = None
    retrieval_gold_status: Literal["candidate", "approved"] | None = None
    qa_gold_status: Literal["pending_p09"] | None = None
    evaluation_stratum: Literal["retrieval_main", "upstream_gap_diagnostic"] | None = None
    p06_runtime_resolvable: bool | None = None
    diagnostic_evidence_id: str | None = Field(default=None, min_length=1, max_length=160)
    evidence_judgments: list[RetrievalEvidenceJudgment] = Field(default_factory=list)
    hard_negative_evidence_ids: list[str] = Field(default_factory=list)
    unanswerable_audit: UnanswerableRetrievalAudit | None = None
    upstream_approved_sha256: dict[str, Sha256] = Field(default_factory=dict)
    query_sha256: Sha256 | None = None
    generation_strategy_sha256: Sha256 | None = None
    approval_scope: Literal["ds4_query_processing_and_ds5_retrieval_only"] | None = None

    @model_validator(mode="after")
    def validate_answerability(self) -> RetrievalQACase:
        qa_pending = self.qa_gold_status == "pending_p09"
        if self.answerable:
            if self.gold_answer_type == "unanswerable":
                raise ValueError("answerable cases cannot use unanswerable gold_answer_type")
            if not self.gold_evidence_groups:
                raise ValueError("answerable cases require at least one evidence group")
            if self.expected_behavior not in (None, "answer"):
                raise ValueError("answerable cases cannot require abstention")
        else:
            if self.gold_answer_type not in ({"pending_p09"} if qa_pending else {"unanswerable"}):
                raise ValueError("unanswerable cases require unanswerable gold_answer_type")
            if self.gold_claims or self.gold_evidence_groups or self.gold_short_answers:
                raise ValueError("unanswerable cases cannot contain answer Gold")
            if self.allowed_answer_variants:
                raise ValueError("unanswerable cases cannot contain answer variants")
            if self.expected_behavior == "answer":
                raise ValueError("unanswerable cases cannot require an answer")
        formal_values = (
            self.course_id,
            self.query_family_id,
            self.source_package_id,
            self.split,
            self.retrieval_gold_status,
            self.qa_gold_status,
            self.evaluation_stratum,
            self.p06_runtime_resolvable,
            self.query_sha256,
            self.generation_strategy_sha256,
            self.approval_scope,
        )
        if any(value is not None for value in formal_values):
            if any(value is None for value in formal_values):
                raise ValueError("formal P08 DS5 cases require all provenance and status fields")
            if not qa_pending or self.gold_answer_type != "pending_p09":
                raise ValueError("P08 formal DS5 QA Gold must remain pending_p09")
            if self.gold_short_answers or self.gold_claims or self.forbidden_claims:
                raise ValueError("P08 formal DS5 cannot contain P09 QA Gold")
            if self.allowed_answer_variants:
                raise ValueError("P08 formal DS5 cannot contain answer variants")
            actual = hashlib.sha256(self.query.encode("utf-8")).hexdigest()
            if self.query_sha256 != actual:
                raise ValueError("DS5 query_sha256 must bind query exactly")
            if not self.upstream_approved_sha256:
                raise ValueError("formal P08 DS5 requires upstream Approved hashes")
            judged = {item.evidence_id: item for item in self.evidence_judgments}
            if len(judged) != len(self.evidence_judgments):
                raise ValueError("DS5 Evidence judgments must have unique Evidence IDs")
            if set(judged) != set(self.graded_relevance):
                raise ValueError("DS5 Evidence judgments and graded_relevance must agree")
            if any(
                judged[item].relevance != score for item, score in self.graded_relevance.items()
            ):
                raise ValueError("DS5 Evidence judgment scores must match graded_relevance")
            if not 3 <= len(self.hard_negative_evidence_ids) <= 5:
                raise ValueError("formal DS5 requires three to five explicit hard negatives")
            if any(
                item not in judged or judged[item].relevance != 0
                for item in self.hard_negative_evidence_ids
            ):
                raise ValueError("hard negatives must be explicit zero-relevance judgments")
            if self.answerable and self.unanswerable_audit is not None:
                raise ValueError("answerable cases cannot carry an unanswerable audit")
            if not self.answerable and self.unanswerable_audit is None:
                raise ValueError("unanswerable formal cases require a full-course audit")
            diagnostic = self.evaluation_stratum == "upstream_gap_diagnostic"
            if diagnostic != (self.diagnostic_evidence_id is not None):
                raise ValueError("diagnostic stratum requires exactly one diagnostic Evidence ID")
            if diagnostic == bool(self.p06_runtime_resolvable):
                raise ValueError("only retrieval_main cases may be P06 runtime-resolvable")
        return self


class FixturePageMap(StrictModel):
    output_page_number: int = Field(ge=1)
    source_page_number: int = Field(ge=1)
    representation: Literal["native", "raster_lossless", "raster_jpeg"]


class FixtureSourceUnitMap(StrictModel):
    source_kind: Literal["paragraph", "table_cell"]
    source_index: str = Field(min_length=1, max_length=160)
    target_index: str = Field(min_length=1, max_length=160)
    text_sha256: Sha256


class CorpusFixtureArtifact(StrictModel):
    course_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_role: Literal["primary", "derived_fixture"]
    parent_document_id: str | None = Field(default=None, min_length=1, max_length=160)
    repository_relative_path: str = Field(min_length=1, max_length=1024)
    sha256: Sha256
    size_bytes: int = Field(ge=1)
    mime_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    page_count: int | None = Field(default=None, ge=1)
    page_count_basis: Literal[
        "verified_pdf_page_tree",
        "derived_manifest",
        "pending_fixed_renderer",
    ]
    transform_type: Literal[
        "identity",
        "raster_subset_lossless",
        "raster_subset_compressed",
        "mixed_native_raster",
        "docx_structure_stress",
    ]
    transform_parameters: dict[str, str | int | float | bool | list[int] | list[str]] = Field(
        default_factory=dict
    )
    page_map: list[FixturePageMap] = Field(default_factory=list)
    source_unit_map: list[FixtureSourceUnitMap] = Field(default_factory=list)
    mutually_exclusive_variant_group: str = Field(min_length=1, max_length=160)
    retrieval_eligible: bool

    @model_validator(mode="after")
    def validate_fixture_role(self) -> CorpusFixtureArtifact:
        if self.document_role == "primary":
            if self.parent_document_id is not None:
                raise ValueError("primary fixture artifacts cannot declare a parent")
            if not self.retrieval_eligible:
                raise ValueError("primary fixture artifacts must remain retrieval eligible")
        else:
            if self.parent_document_id is None:
                raise ValueError("derived fixture artifacts require a parent")
            if self.retrieval_eligible:
                raise ValueError("derived fixture artifacts cannot be retrieval eligible")
        return self


class CorpusFixtureManifest(StrictModel):
    schema_version: Literal["courserag.corpus-fixtures.v1"] = "courserag.corpus-fixtures.v1"
    generator: str = Field(min_length=1, max_length=160)
    generator_version: str = Field(min_length=1, max_length=80)
    semantic_source_count: Literal[2] = 2
    evaluation_document_count: Literal[6] = 6
    artifacts: list[CorpusFixtureArtifact] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_lineages(self) -> CorpusFixtureManifest:
        artifact_by_id = {artifact.document_id: artifact for artifact in self.artifacts}
        if len(artifact_by_id) != len(self.artifacts):
            raise ValueError("fixture artifact document IDs must be unique")
        primary_ids = {
            artifact.document_id
            for artifact in self.artifacts
            if artifact.document_role == "primary"
        }
        if len(primary_ids) != self.semantic_source_count:
            raise ValueError("semantic source count must equal the number of primary artifacts")
        for artifact in self.artifacts:
            if artifact.document_role == "primary":
                continue
            parent = artifact_by_id.get(artifact.parent_document_id or "")
            if parent is None or parent.document_id not in primary_ids:
                raise ValueError("derived fixture parent must be a primary artifact")
            if parent.course_id != artifact.course_id:
                raise ValueError("derived fixture must remain in its parent's course")
            if parent.mutually_exclusive_variant_group != artifact.mutually_exclusive_variant_group:
                raise ValueError("parent and derived fixture must share a variant group")
        return self


class DS1SampleSelection(StrictModel):
    selection_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    sample_kind: Literal["native_pdf_page", "docx_structure_anchor", "ocr_page"]
    source_page_numbers: list[int] = Field(default_factory=list)
    document_page_numbers: list[int] = Field(default_factory=list)
    section_anchors: list[str] = Field(default_factory=list)
    status: Literal["candidate"] = "candidate"
    notes: list[str] = Field(default_factory=list)


class DS1SamplingPlan(StrictModel):
    schema_version: Literal["courserag.ds1-sampling-plan.v1"] = "courserag.ds1-sampling-plan.v1"
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    review_status: Literal["candidate"] = "candidate"
    selections: list[DS1SampleSelection] = Field(min_length=1)
    blockers: list[str] = Field(default_factory=list)


class P03EvalIdentityBinding(StrictModel):
    course_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_role: Literal["primary", "derived_fixture"]
    parent_document_id: str | None = Field(default=None, min_length=1, max_length=160)
    mutually_exclusive_variant_group: str = Field(min_length=1, max_length=160)
    retrieval_eligible: bool
    ds0_document_version: str = Field(min_length=1, max_length=120)
    document_sha256: Sha256
    knowledge_base_id: str = Field(min_length=36, max_length=36)
    source_document_id: str = Field(min_length=36, max_length=36)
    document_version_id: str = Field(min_length=36, max_length=36)
    build_job_id: str = Field(min_length=36, max_length=36)
    build_scope: Literal["p03_inventory"] = "p03_inventory"
    build_request_sha256: Sha256
    build_status: Literal["succeeded"] = "succeeded"
    stage_name: Literal["legacy_document_inventory"] = "legacy_document_inventory"
    stage_status: Literal["succeeded", "cached"]
    stage_fingerprint_sha256: Sha256
    artifact_uri: str = Field(pattern=r"^artifact://sha256/[0-9a-f]{64}$")
    artifact_sha256: Sha256

    @model_validator(mode="after")
    def validate_role(self) -> P03EvalIdentityBinding:
        if self.document_role == "primary":
            if self.parent_document_id is not None or not self.retrieval_eligible:
                raise ValueError("primary P03 bindings must be retrieval eligible and parentless")
        elif self.parent_document_id is None or self.retrieval_eligible:
            raise ValueError("derived P03 bindings require a parent and cannot be retrievable")
        return self


class P03EvalIdentitySnapshot(StrictModel):
    schema_version: Literal["courserag.p03-eval-identity-snapshot.v1"] = (
        "courserag.p03-eval-identity-snapshot.v1"
    )
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    identity_scheme: Literal["uuid5-url-courserag-eval-v1"] = "uuid5-url-courserag-eval-v1"
    database_scope: Literal["isolated_coursepilot_eval"] = "isolated_coursepilot_eval"
    semantic_source_count: Literal[2] = 2
    bindings: list[P03EvalIdentityBinding] = Field(min_length=6, max_length=6)

    @model_validator(mode="after")
    def validate_bindings(self) -> P03EvalIdentitySnapshot:
        document_ids = {binding.document_id for binding in self.bindings}
        if len(document_ids) != 6:
            raise ValueError("P03 evaluation bindings require six unique documents")
        knowledge_base_ids = {binding.knowledge_base_id for binding in self.bindings}
        if len(knowledge_base_ids) != self.semantic_source_count:
            raise ValueError("P03 evaluation bindings require exactly two knowledge bases")
        if sum(binding.document_role == "primary" for binding in self.bindings) != 2:
            raise ValueError("P03 evaluation bindings require exactly two primary documents")
        return self


class NativePDFPageCandidate(StrictModel):
    selection_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=36, max_length=36)
    page_number: int = Field(ge=1)
    page_text_sha256: Sha256
    pilot: bool = False
    coverage_tags: list[str] = Field(default_factory=list)


class DocxPaginationAnchorCandidate(StrictModel):
    selection_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=36, max_length=36)
    source_document_id: str = Field(min_length=1, max_length=160)
    source_paragraph_index: int = Field(ge=0)
    section_anchor: str = Field(min_length=1, max_length=40)
    source_text: str = Field(min_length=1, max_length=1000)
    source_text_sha256: Sha256
    mapped_source_unit: str = Field(min_length=1, max_length=160)
    physical_page_index: None = None
    display_page_label: None = None
    section_page_index: None = None
    renderer_provider: None = None
    renderer_version: None = None
    render_profile_sha256: None = None
    font_manifest_sha256: None = None
    rendered_pdf_sha256: None = None
    alignment_confidence: None = None

    @model_validator(mode="after")
    def validate_source_text_hash(self) -> DocxPaginationAnchorCandidate:
        actual = hashlib.sha256(self.source_text.encode("utf-8")).hexdigest()
        if self.source_text_sha256 != actual:
            raise ValueError("DOCX anchor hash must bind the exact source text")
        return self


class SectionCandidateSelection(StrictModel):
    selection_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=36, max_length=36)
    section_anchor: str = Field(min_length=1, max_length=40)
    source_title: str = Field(min_length=1, max_length=1000)
    source_title_sha256: Sha256
    source_paragraph_index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_source_title_hash(self) -> SectionCandidateSelection:
        actual = hashlib.sha256(self.source_title.encode("utf-8")).hexdigest()
        if self.source_title_sha256 != actual:
            raise ValueError("Section title hash must bind the exact source title")
        return self


class TableCandidateSelection(StrictModel):
    selection_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=36, max_length=36)
    source_table_index: int | None = Field(default=None, ge=0)
    source_page_number: int | None = Field(default=None, ge=1)
    source_anchor_text: str = Field(min_length=1, max_length=1000)
    source_content_sha256: Sha256
    observed_row_count: int | None = Field(default=None, ge=1)
    observed_column_count: int | None = Field(default=None, ge=1)


class OCRRouteOnlyCandidate(StrictModel):
    selection_id: str = Field(min_length=1, max_length=160)
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=36, max_length=36)
    document_page_number: int = Field(ge=1)
    parent_document_id: str = Field(min_length=1, max_length=160)
    source_page_number: int = Field(ge=1)
    representation: Literal["raster_lossless", "raster_jpeg", "raster"]
    expected_p04_action: Literal["route_to_ocr_pending"] = "route_to_ocr_pending"
    transcription: None = None
    regions: list[None] = Field(default_factory=list, max_length=0)


class P04InputWorkPackage(ReviewableRecord):
    schema_version: Literal["courserag.p04-input-work-package.v1"] = (
        "courserag.p04-input-work-package.v1"
    )
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)
    approval_scope: Literal["p04_input_selection_only"] = "p04_input_selection_only"
    gold_status: Literal["no_ds1_gold"] = "no_ds1_gold"
    p03_identity_snapshot_sha256: Sha256
    identities: list[P03EvalIdentityBinding] = Field(min_length=6, max_length=6)
    native_pdf_pages: list[NativePDFPageCandidate] = Field(min_length=15, max_length=15)
    docx_pagination_anchors: list[DocxPaginationAnchorCandidate] = Field(
        min_length=10, max_length=10
    )
    sections: list[SectionCandidateSelection] = Field(min_length=20, max_length=20)
    tables: list[TableCandidateSelection] = Field(min_length=10, max_length=10)
    ocr_route_only_pages: list[OCRRouteOnlyCandidate] = Field(min_length=15, max_length=15)
    pending_p04_fields: list[
        Literal[
            "reading_order",
            "regions_and_noise",
            "section_boundaries",
            "table_cells",
            "docx_physical_page_index",
            "docx_display_page_label",
            "docx_section_page_index",
            "renderer_manifest",
            "rendered_pdf_sha256",
            "alignment_confidence",
        ]
    ] = Field(min_length=10, max_length=10)
    constraints: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fixed_scope(self) -> P04InputWorkPackage:
        if len({binding.document_id for binding in self.identities}) != 6:
            raise ValueError("P04 input work package requires six unique P03 bindings")
        if len({page.page_number for page in self.native_pdf_pages}) != 15:
            raise ValueError("native PDF page candidates must be unique")
        pilot_pages = {page.page_number for page in self.native_pdf_pages if page.pilot}
        if pilot_pages != {5, 10, 12, 20, 32}:
            raise ValueError("P04 Pilot native PDF pages must remain frozen")
        anchor_documents = {anchor.document_id for anchor in self.docx_pagination_anchors}
        if len(anchor_documents) != 2 or any(
            sum(anchor.document_id == document_id for anchor in self.docx_pagination_anchors) != 5
            for document_id in anchor_documents
        ):
            raise ValueError("DOCX pagination requires five primary and five stress anchors")
        if len({selection.selection_id for selection in self.sections}) != 20:
            raise ValueError("Section candidate IDs must be unique")
        if len({selection.selection_id for selection in self.tables}) != 10:
            raise ValueError("Table candidate IDs must be unique")
        if len({selection.selection_id for selection in self.ocr_route_only_pages}) != 15:
            raise ValueError("OCR route-only candidate IDs must be unique")
        return self


class DS5RetrievalQADataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds5.v1"] = "courserag.ds5.v1"
    cases: list[RetrievalQACase] = Field(default_factory=list)


class P08SourcePackage(StrictModel):
    package_id: str = Field(min_length=1, max_length=160)
    course_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=300)
    section_anchors: list[str] = Field(min_length=1)
    primary_document_id: str = Field(min_length=1, max_length=160)
    primary_document_version: str = Field(min_length=1, max_length=120)
    primary_document_sha256: Sha256
    evidence_ids: list[str] = Field(min_length=1)
    evidence_record_sha256: dict[str, Sha256] = Field(min_length=1)
    necessary_neighbor_record_sha256: dict[str, Sha256] = Field(default_factory=dict)
    knowledge_point_ids: list[str] = Field(min_length=1)
    knowledge_point_record_sha256: dict[str, Sha256] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_package_references(self) -> P08SourcePackage:
        if set(self.evidence_ids) != set(self.evidence_record_sha256):
            raise ValueError("source package Evidence IDs and hashes must agree")
        if set(self.knowledge_point_ids) != set(self.knowledge_point_record_sha256):
            raise ValueError("source package KP IDs and hashes must agree")
        if not set(self.necessary_neighbor_record_sha256).issubset(self.evidence_ids):
            raise ValueError("neighbor hashes may only describe package Evidence")
        return self


class P08SourcePackageDataset(DatasetEnvelope):
    schema_version: Literal["courserag.p08-source-packages.v1"] = "courserag.p08-source-packages.v1"
    semantic_source_count: Literal[2] = 2
    packages: list[P08SourcePackage] = Field(min_length=10, max_length=10)
    upstream_approved_sha256: dict[str, Sha256] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_package_set(self) -> P08SourcePackageDataset:
        if len({item.package_id for item in self.packages}) != 10:
            raise ValueError("P08 requires ten unique Source Packages")
        if len({item.course_id for item in self.packages}) != 2:
            raise ValueError("P08 Source Packages require exactly two courses")
        return self


class P08SplitAssignment(StrictModel):
    case_id: str = Field(min_length=1, max_length=160)
    query_family_id: str = Field(min_length=1, max_length=160)
    split: Literal["dev", "test"]
    course_id: str = Field(min_length=1, max_length=160)
    query_type: Literal[
        "exact_fact",
        "definition",
        "paraphrase",
        "comparison",
        "procedure",
        "application",
        "cross_section",
        "unanswerable",
    ]
    evaluation_stratum: Literal["retrieval_main", "upstream_gap_diagnostic"]


class P08DS5SplitManifest(DatasetEnvelope):
    schema_version: Literal["courserag.p08-ds5-split.v1"] = "courserag.p08-ds5-split.v1"
    assignments: list[P08SplitAssignment] = Field(min_length=100, max_length=100)
    test_locked: Literal[False] = False
    p08_tuning_allowed_ids: list[str] = Field(min_length=54, max_length=54)

    @model_validator(mode="after")
    def validate_split(self) -> P08DS5SplitManifest:
        ids = [item.case_id for item in self.assignments]
        if len(ids) != len(set(ids)):
            raise ValueError("P08 DS5 split IDs must be unique")
        family_sides: dict[str, set[str]] = {}
        for item in self.assignments:
            family_sides.setdefault(item.query_family_id, set()).add(item.split)
        if any(len(sides) != 1 for sides in family_sides.values()):
            raise ValueError("Query Families cannot cross Dev/Test")
        allowed = {
            item.case_id
            for item in self.assignments
            if item.split == "dev" and item.evaluation_stratum == "retrieval_main"
        }
        if set(self.p08_tuning_allowed_ids) != allowed:
            raise ValueError("P08 tuning IDs must be exactly retrieval_main Dev")
        return self


class P08ReviewDecisions(StrictModel):
    schema_version: Literal["courserag.p08-review-decisions.v1"] = (
        "courserag.p08-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    expected_record_ids: list[str] = Field(min_length=1)
    reviewed_record_ids: list[str] = Field(default_factory=list)
    returned_record_ids: list[str] = Field(default_factory=list)
    record_notes: dict[str, str] = Field(default_factory=dict)
    reviewer_id: str | None = Field(default=None, min_length=1, max_length=160)
    reviewed_at: datetime | None = None
    attestation_source: (
        Literal["offline_review_package", "course_owner_conversation_attestation"] | None
    ) = None
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_decisions(self) -> P08ReviewDecisions:
        expected = set(self.expected_record_ids)
        if len(expected) != len(self.expected_record_ids):
            raise ValueError("expected P08 review IDs must be unique")
        if len(set(self.reviewed_record_ids)) != len(self.reviewed_record_ids):
            raise ValueError("reviewed P08 IDs must be unique")
        if len(set(self.returned_record_ids)) != len(self.returned_record_ids):
            raise ValueError("returned P08 IDs must be unique")
        if not set(self.reviewed_record_ids).issubset(expected):
            raise ValueError("reviewed P08 IDs must belong to the expected review pass")
        if not set(self.returned_record_ids).issubset(self.reviewed_record_ids):
            raise ValueError("returned P08 IDs must already be reviewed")
        if not set(self.record_notes).issubset(self.reviewed_record_ids):
            raise ValueError("P08 review notes must belong to reviewed records")
        return self


class P08GoldBundleManifest(DatasetEnvelope):
    schema_version: Literal["courserag.p08-gold-bundle-manifest.v1"] = (
        "courserag.p08-gold-bundle-manifest.v1"
    )
    revision: int = Field(ge=1)
    approval_scope: Literal["ds4_query_processing_and_ds5_retrieval_only"] = (
        "ds4_query_processing_and_ds5_retrieval_only"
    )
    ds4_candidate: HashedArtifact
    ds5_candidate: HashedArtifact
    source_packages: HashedArtifact
    split_manifest: HashedArtifact
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=160, max_length=160)
    upstream_approved_sha256: dict[str, Sha256] = Field(min_length=2)
    preserved_upstream_sha256: dict[str, Sha256] = Field(min_length=1)
    p06_unmapped_evidence_ids: list[str] = Field(min_length=19, max_length=19)
    diagnostic_evidence_ids: list[str] = Field(min_length=10, max_length=10)
    first_review_groups: list[list[str]] = Field(min_length=8, max_length=8)
    second_review_ids: list[str] = Field(min_length=132, max_length=132)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    second_review_index_sha256: Sha256
    review_asset_sha256: dict[str, Sha256] = Field(min_length=1)
    bundle_sha256: Sha256
    qa_gold_status: Literal["pending_p09"] = "pending_p09"
    test_locked: Literal[False] = False

    @model_validator(mode="after")
    def validate_review_sets(self) -> P08GoldBundleManifest:
        first = [item for group in self.first_review_groups for item in group]
        if len(first) != 160 or len(set(first)) != 160:
            raise ValueError("P08 first review must contain 160 unique records")
        if len(self.second_review_ids) != len(set(self.second_review_ids)):
            raise ValueError("P08 second review IDs must be unique")
        if not set(self.second_review_ids).issubset(first):
            raise ValueError("P08 second review must be a subset of first review")
        if len(set(self.diagnostic_evidence_ids)) != 10:
            raise ValueError("P08 diagnostic Evidence IDs must be unique")
        if not set(self.diagnostic_evidence_ids).issubset(self.p06_unmapped_evidence_ids):
            raise ValueError("P08 diagnostics must come from frozen P06 gaps")
        return self


class P08GoldBundleApproval(DatasetEnvelope):
    schema_version: Literal["courserag.p08-gold-bundle-approval.v1"] = (
        "courserag.p08-gold-bundle-approval.v1"
    )
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    bundle_sha256: Sha256
    ds4_candidate: HashedArtifact
    ds5_candidate: HashedArtifact
    first_review_decisions: HashedArtifact
    second_review_decisions: HashedArtifact
    approved_ds4: HashedArtifact
    approved_ds5: HashedArtifact
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=160, max_length=160)
    approved_record_sha256: dict[str, Sha256] = Field(min_length=160, max_length=160)
    notes: str = Field(min_length=1, max_length=4000)


class P09AnswerVariant(StrictModel):
    text: str = Field(min_length=1, max_length=8000)
    basis: Literal["source_attested", "mechanical_normalization"]
    source_text_sha256: Sha256
    rationale: str = Field(min_length=1, max_length=1000)


class P09ForbiddenClaim(StrictModel):
    forbidden_claim_id: str = Field(min_length=1, max_length=160)
    claim_text: str = Field(min_length=1, max_length=8000)
    claim_text_sha256: Sha256
    risk_type: Literal["conflation", "contradiction", "unsupported_specificity"]
    basis_evidence_ids: list[str] = Field(min_length=1)
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_claim_hash(self) -> P09ForbiddenClaim:
        actual = hashlib.sha256(self.claim_text.encode("utf-8")).hexdigest()
        if self.claim_text_sha256 != actual:
            raise ValueError("Forbidden Claim Hash must bind exact Claim text")
        if len(self.basis_evidence_ids) != len(set(self.basis_evidence_ids)):
            raise ValueError("Forbidden Claim Evidence IDs must be unique")
        return self


class P09QAGoldCase(ReviewableRecord):
    retrieval_case_id: str = Field(min_length=1, max_length=160)
    retrieval_case_sha256: Sha256
    query: str = Field(min_length=1, max_length=4000)
    query_sha256: Sha256
    query_type: Literal[
        "exact_fact",
        "definition",
        "paraphrase",
        "comparison",
        "procedure",
        "application",
        "cross_section",
        "unanswerable",
    ]
    course_id: str = Field(min_length=1, max_length=160)
    split: Literal["dev", "test"]
    evaluation_stratum: Literal["retrieval_main", "upstream_gap_diagnostic"]
    answerable: bool
    gold_answer_type: Literal[
        "factoid",
        "list",
        "explanatory",
        "comparison",
        "procedure",
        "unanswerable",
    ]
    gold_short_answers: list[str] = Field(default_factory=list)
    gold_list_items: list[str] = Field(default_factory=list)
    allowed_answer_variants: list[str] = Field(default_factory=list)
    answer_variant_details: list[P09AnswerVariant] = Field(default_factory=list)
    gold_claims: list[GoldClaim] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list, max_length=3)
    forbidden_claim_details: list[P09ForbiddenClaim] = Field(default_factory=list, max_length=3)
    annotation_flags: list[
        Literal[
            "source_evidence_appears_truncated",
            "retrieval_question_support_needs_owner_adjudication",
        ]
    ] = Field(default_factory=list)
    manual_review_reason: str | None = Field(default=None, min_length=1, max_length=2000)
    expected_behavior: Literal["answer", "abstained_insufficient_evidence"]
    unanswerable_audit_sha256: Sha256 | None = None
    upstream_approved_sha256: dict[str, Sha256] = Field(min_length=5)
    generation_strategy_sha256: Sha256
    qa_gold_status: Literal["candidate", "approved"]
    approval_scope: Literal["ds5_qa_and_context_only"] = "ds5_qa_and_context_only"

    @model_validator(mode="after")
    def validate_p09_qa_gold(self) -> P09QAGoldCase:
        if hashlib.sha256(self.query.encode("utf-8")).hexdigest() != self.query_sha256:
            raise ValueError("P09 QA query Hash must bind exact P08 Query")
        claim_ids = [item.claim_id for item in self.gold_claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("P09 QA Claim IDs must be unique")
        if self.answerable:
            if self.gold_answer_type == "unanswerable":
                raise ValueError("answerable P09 QA cases cannot be unanswerable")
            if self.expected_behavior != "answer" or not self.gold_claims:
                raise ValueError("answerable P09 QA cases require answer behavior and Claims")
            if not any(item.importance == "required" for item in self.gold_claims):
                raise ValueError("answerable P09 QA cases require a Required Claim")
            if self.unanswerable_audit_sha256 is not None:
                raise ValueError("answerable P09 QA cases cannot bind an unanswerable audit")
        else:
            if self.gold_answer_type != "unanswerable":
                raise ValueError("unanswerable P09 QA cases require unanswerable answer type")
            if self.expected_behavior != "abstained_insufficient_evidence":
                raise ValueError(
                    "unanswerable P09 QA cases require insufficient-Evidence abstention"
                )
            if any(
                (
                    self.gold_short_answers,
                    self.gold_list_items,
                    self.allowed_answer_variants,
                    self.answer_variant_details,
                    self.gold_claims,
                )
            ):
                raise ValueError("unanswerable P09 QA cases cannot contain answer Gold")
            if self.unanswerable_audit_sha256 is None:
                raise ValueError("unanswerable P09 QA cases must bind the P08 audit")
        if self.gold_answer_type in {"factoid", "list"}:
            if not self.gold_short_answers:
                raise ValueError("factoid/list P09 QA cases require short answers")
        elif self.gold_short_answers or self.gold_list_items or self.allowed_answer_variants:
            raise ValueError("only factoid/list P09 QA cases may contain short-answer Gold")
        if self.gold_answer_type == "list" and not self.gold_list_items:
            raise ValueError("list P09 QA cases require structured list items")
        if set(self.allowed_answer_variants) != {item.text for item in self.answer_variant_details}:
            raise ValueError("P09 answer variant strings and details must agree")
        if self.forbidden_claims != [item.claim_text for item in self.forbidden_claim_details]:
            raise ValueError("P09 Forbidden Claim strings and details must agree")
        if bool(self.annotation_flags) != bool(self.manual_review_reason):
            raise ValueError("P09 annotation flags and manual-review reason must appear together")
        if self.qa_gold_status == "approved" and self.review_status != "approved":
            raise ValueError("Approved QA Gold requires an approved review status")
        if self.qa_gold_status == "candidate" and self.review_status == "approved":
            raise ValueError("Candidate QA Gold cannot have an approved review status")
        return self


class P09QAGoldDataset(DatasetEnvelope):
    schema_version: Literal["courserag.p09-qa-gold.v1"] = "courserag.p09-qa-gold.v1"
    cases: list[P09QAGoldCase] = Field(min_length=100, max_length=100)


class P09NecessaryContextNeighbor(StrictModel):
    neighbor_id: str = Field(min_length=1, max_length=160)
    evidence_id: str = Field(min_length=1, max_length=160)
    relation: Literal["parent_heading", "previous", "next"]
    text: str = Field(min_length=1, max_length=20_000)
    text_sha256: Sha256
    source_span: SourceSpan
    necessity_reason: Literal[
        "resolve_reference",
        "restore_list_scope",
        "restore_definition_scope",
        "restore_semantic_dependency",
        "complete_procedure",
    ]

    @model_validator(mode="after")
    def validate_neighbor_hash(self) -> P09NecessaryContextNeighbor:
        if hashlib.sha256(self.text.encode("utf-8")).hexdigest() != self.text_sha256:
            raise ValueError("P09 necessary-neighbor Hash must bind exact text")
        return self


class P09ContextGoldCase(ReviewableRecord):
    retrieval_case_id: str = Field(min_length=1, max_length=160)
    retrieval_case_sha256: Sha256
    qa_case_id: str = Field(min_length=1, max_length=160)
    query_sha256: Sha256
    course_id: str = Field(min_length=1, max_length=160)
    split: Literal["dev", "test"]
    evaluation_stratum: Literal["retrieval_main", "upstream_gap_diagnostic"]
    answerable: bool
    purpose: Literal["question_answering"] = "question_answering"
    complete_evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    relevant_evidence_ids: list[str] = Field(default_factory=list)
    hard_negative_evidence_ids: list[str] = Field(min_length=3, max_length=5)
    necessary_neighbors: list[P09NecessaryContextNeighbor] = Field(default_factory=list)
    max_items: Literal[8] = 8
    max_tokens: Literal[4000] = 4000
    preserve_evidence_boundaries: Literal[True] = True
    deduplicate: Literal[True] = True
    parent_expansion: Literal["forbidden", "only_if_necessary_neighbor"]
    neighbor_expansion: Literal["forbidden", "only_listed_neighbors"]
    context_order_policy: Literal["not_fixed_equivalent_orders_allowed"] = (
        "not_fixed_equivalent_orders_allowed"
    )
    p06_runtime_resolvable: bool
    upstream_approved_sha256: dict[str, Sha256] = Field(min_length=5)
    generation_strategy_sha256: Sha256
    context_gold_status: Literal["candidate", "approved"]
    approval_scope: Literal["ds5_qa_and_context_only"] = "ds5_qa_and_context_only"

    @model_validator(mode="after")
    def validate_p09_context_gold(self) -> P09ContextGoldCase:
        if len(self.relevant_evidence_ids) != len(set(self.relevant_evidence_ids)):
            raise ValueError("P09 relevant Evidence IDs must be unique")
        if set(self.relevant_evidence_ids).intersection(self.hard_negative_evidence_ids):
            raise ValueError("P09 relevant and hard-negative Evidence must be disjoint")
        required = {
            evidence_id
            for group in self.complete_evidence_groups
            for evidence_id in group.required_evidence_ids
        }
        if not required.issubset(self.relevant_evidence_ids):
            raise ValueError("complete Evidence Groups must be included in relevant Evidence")
        if self.answerable:
            if not self.complete_evidence_groups or not self.relevant_evidence_ids:
                raise ValueError("answerable P09 Context Gold requires relevant Evidence Groups")
        elif (
            self.complete_evidence_groups or self.relevant_evidence_ids or self.necessary_neighbors
        ):
            raise ValueError("unanswerable P09 Context Gold cannot contain relevant Context")
        neighbor_ids = [item.neighbor_id for item in self.necessary_neighbors]
        if len(neighbor_ids) != len(set(neighbor_ids)):
            raise ValueError("P09 Context necessary-neighbor IDs must be unique")
        if any(
            item.evidence_id not in self.relevant_evidence_ids for item in self.necessary_neighbors
        ):
            raise ValueError("P09 necessary neighbors must belong to relevant Evidence")
        expected_parent = (
            "only_if_necessary_neighbor"
            if any(item.relation == "parent_heading" for item in self.necessary_neighbors)
            else "forbidden"
        )
        expected_neighbor = (
            "only_listed_neighbors"
            if any(item.relation in {"previous", "next"} for item in self.necessary_neighbors)
            else "forbidden"
        )
        if self.parent_expansion != expected_parent or self.neighbor_expansion != expected_neighbor:
            raise ValueError("P09 expansion policy must be derived from listed necessary neighbors")
        if self.context_gold_status == "approved" and self.review_status != "approved":
            raise ValueError("Approved Context Gold requires an approved review status")
        if self.context_gold_status == "candidate" and self.review_status == "approved":
            raise ValueError("Candidate Context Gold cannot have an approved review status")
        return self


class P09ContextGoldDataset(DatasetEnvelope):
    schema_version: Literal["courserag.p09-context-gold.v1"] = "courserag.p09-context-gold.v1"
    cases: list[P09ContextGoldCase] = Field(min_length=100, max_length=100)


class P09ReviewDecision(StrictModel):
    record_id: str = Field(min_length=1, max_length=160)
    decision: Literal["pass", "return"]
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_return_reason(self) -> P09ReviewDecision:
        if self.decision == "return" and not self.notes.strip():
            raise ValueError("returned P09 records require reviewer notes")
        return self


class P09ReviewDecisions(DatasetEnvelope):
    schema_version: Literal["courserag.p09-review-decisions.v1"] = (
        "courserag.p09-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    expected_record_ids: list[str] = Field(min_length=1)
    decisions: list[P09ReviewDecision] = Field(default_factory=list)
    reviewer_id: str | None = Field(default=None, min_length=1, max_length=160)
    reviewed_at: datetime | None = None
    attestation_source: Literal["html_export", "course_owner_conversation_attestation"] = (
        "html_export"
    )
    notes: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def validate_review_coverage(self) -> P09ReviewDecisions:
        expected = self.expected_record_ids
        actual = [item.record_id for item in self.decisions]
        if len(expected) != len(set(expected)) or len(actual) != len(set(actual)):
            raise ValueError("P09 review IDs must be unique")
        if not set(actual).issubset(expected):
            raise ValueError("P09 decisions may only reference expected records")
        return self


class P09AnswerObligation(StrictModel):
    obligation_id: str = Field(min_length=1, max_length=160)
    obligation_text: str = Field(min_length=1, max_length=2000)
    claim_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    support_mode: Literal["single_claim", "joint_claim_set"]
    rationale: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_unique_links(self) -> P09AnswerObligation:
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("P09 obligation Claim IDs must be unique")
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("P09 obligation Evidence IDs must be unique")
        return self


class P09CaseCoverageAudit(StrictModel):
    qa_case_id: str = Field(min_length=1, max_length=160)
    query_sha256: Sha256
    answerable: bool
    audit_status: Literal["complete", "not_applicable_unanswerable"]
    obligations: list[P09AnswerObligation] = Field(default_factory=list)
    required_claim_ids: list[str] = Field(default_factory=list)
    uncovered_obligation_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_coverage(self) -> P09CaseCoverageAudit:
        obligation_ids = [item.obligation_id for item in self.obligations]
        if len(obligation_ids) != len(set(obligation_ids)):
            raise ValueError("P09 obligation IDs must be unique within a case")
        if self.answerable:
            if self.audit_status != "complete" or not self.obligations:
                raise ValueError("answerable P09 cases require complete obligation coverage")
            if self.uncovered_obligation_ids:
                raise ValueError(
                    "complete P09 coverage audits cannot contain uncovered obligations"
                )
            linked_claims = {claim for item in self.obligations for claim in item.claim_ids}
            if set(self.required_claim_ids) != linked_claims:
                raise ValueError("every Required Claim must be assigned to an answer obligation")
        elif (
            self.audit_status != "not_applicable_unanswerable"
            or self.obligations
            or self.required_claim_ids
            or self.uncovered_obligation_ids
        ):
            raise ValueError("unanswerable P09 cases cannot contain answer obligations")
        return self


class P09CoverageAuditDataset(DatasetEnvelope):
    schema_version: Literal["courserag.p09-coverage-audit.v1"] = "courserag.p09-coverage-audit.v1"
    cases: list[P09CaseCoverageAudit] = Field(min_length=100, max_length=100)


class P09GoldBundleManifest(DatasetEnvelope):
    schema_version: Literal["courserag.p09-gold-bundle-manifest.v1"] = (
        "courserag.p09-gold-bundle-manifest.v1"
    )
    revision: Literal[1, 2] = 1
    approval_scope: Literal["ds5_qa_and_context_only"] = "ds5_qa_and_context_only"
    qa_candidate: HashedArtifact
    context_candidate: HashedArtifact
    approved_p08_retrieval: HashedArtifact
    qa_candidate_record_sha256: dict[str, Sha256] = Field(min_length=100, max_length=100)
    context_candidate_record_sha256: dict[str, Sha256] = Field(min_length=100, max_length=100)
    p08_retrieval_record_sha256: dict[str, Sha256] = Field(min_length=100, max_length=100)
    upstream_approved_sha256: dict[str, Sha256] = Field(min_length=5)
    preserved_p08_sha256: dict[str, Sha256] = Field(min_length=3)
    first_review_groups: list[list[str]] = Field(min_length=1, max_length=5)
    second_review_ids: list[str] = Field(min_length=1)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    second_review_index_sha256: Sha256
    bundle_sha256: Sha256
    test_locked: Literal[False] = False
    coverage_audit: HashedArtifact | None = None
    parent_bundle_sha256: Sha256 | None = None
    inherited_first_review: HashedArtifact | None = None
    inherited_second_review: HashedArtifact | None = None
    semantic_changed_record_ids: list[str] = Field(default_factory=list)
    context_changed_record_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_review_sets(self) -> P09GoldBundleManifest:
        first = [item for group in self.first_review_groups for item in group]
        if len(first) != len(set(first)):
            raise ValueError("P09 first-review IDs must be unique")
        if len(self.second_review_ids) != len(set(self.second_review_ids)):
            raise ValueError("P09 second-review IDs must be unique")
        if not set(self.second_review_ids).issubset(first):
            raise ValueError("P09 second review must be a subset of first review")
        if self.revision == 1:
            if len(first) != 100 or any(len(group) != 20 for group in self.first_review_groups):
                raise ValueError("P09 r1 first review must use five groups of 20")
            if (
                any(
                    value is not None
                    for value in (
                        self.coverage_audit,
                        self.parent_bundle_sha256,
                        self.inherited_first_review,
                        self.inherited_second_review,
                    )
                )
                or self.semantic_changed_record_ids
                or self.context_changed_record_ids
            ):
                raise ValueError("P09 r1 cannot contain revision-inheritance fields")
        else:
            required = (
                self.coverage_audit,
                self.parent_bundle_sha256,
                self.inherited_first_review,
                self.inherited_second_review,
            )
            if any(value is None for value in required):
                raise ValueError("P09 r2 requires coverage and inherited-review artifacts")
            if not self.semantic_changed_record_ids:
                raise ValueError("P09 r2 requires semantic changes")
            if set(first) != set(self.semantic_changed_record_ids):
                raise ValueError("P09 r2 first review must equal the semantic-change set")
            if set(self.second_review_ids) != set(self.semantic_changed_record_ids):
                raise ValueError("P09 r2 must blind-review every semantic change twice")
            if not set(self.context_changed_record_ids).issubset(self.semantic_changed_record_ids):
                raise ValueError("P09 r2 Context changes must belong to semantic QA changes")
        return self


class P09GoldBundleApproval(DatasetEnvelope):
    schema_version: Literal["courserag.p09-gold-bundle-approval.v1"] = (
        "courserag.p09-gold-bundle-approval.v1"
    )
    review_id: str = Field(min_length=1, max_length=160)
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    bundle_sha256: Sha256
    qa_candidate: HashedArtifact
    context_candidate: HashedArtifact
    first_review_decisions: HashedArtifact
    second_review_decisions: HashedArtifact
    approved_qa: HashedArtifact
    approved_context: HashedArtifact
    candidate_record_sha256: dict[str, Sha256] = Field(min_length=200, max_length=200)
    approved_record_sha256: dict[str, Sha256] = Field(min_length=200, max_length=200)
    notes: str = Field(min_length=1, max_length=4000)


class QACitationHumanAssessment(StrictModel):
    citation_id: str = Field(min_length=1, max_length=160)
    supports_claim: bool
    supported_gold_claim_ids: list[str] = Field(default_factory=list)


class QAClaimHumanAssessment(StrictModel):
    system_claim_id: str = Field(min_length=1, max_length=160)
    label: Literal[
        "correct_supported",
        "correct_but_uncited",
        "unsupported",
        "contradictory",
        "irrelevant",
    ]
    matched_gold_claim_ids: list[str] = Field(default_factory=list)
    citations: list[QACitationHumanAssessment] = Field(default_factory=list)


class QAHumanReviewRecord(StrictModel):
    metadata: HumanReviewMetadata
    case_id: str = Field(min_length=1, max_length=160)
    system_answer_id: str = Field(min_length=1, max_length=160)
    claims: list[QAClaimHumanAssessment]
    missed_gold_claim_ids: list[str]
    conciseness_pass: bool
    answer_should_be_refused: bool
    system_refused: bool


class QAHumanScoreDataset(DatasetEnvelope):
    schema_version: Literal["courserag.qa-human-scores.v1"] = "courserag.qa-human-scores.v1"
    records: list[QAHumanReviewRecord] = Field(default_factory=list)


class P09ClaimCitationReviewEvidence(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1)
    text_sha256: Sha256
    document_id: str = Field(min_length=1, max_length=160)
    document_version_id: str = Field(min_length=1, max_length=160)
    section_id: str | None = Field(default=None, max_length=160)
    section_path: list[str] = Field(default_factory=list)
    page_labels: list[str] = Field(default_factory=list)
    source_mode: Literal["native", "ocr", "hybrid"]
    warning_codes: list[str] = Field(default_factory=list)


class P09ClaimCitationReviewLink(StrictModel):
    citation_id: str = Field(min_length=1, max_length=160)
    cited_evidence_id: str = Field(min_length=1, max_length=160)
    evidence: P09ClaimCitationReviewEvidence


class P09ClaimCitationReviewClaim(StrictModel):
    system_claim_id: str = Field(min_length=1, max_length=160)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    text_sha256: Sha256
    citations: list[P09ClaimCitationReviewLink] = Field(min_length=1)


class P09ClaimCitationReviewCase(StrictModel):
    case_id: str = Field(min_length=1, max_length=160)
    blinded_sample_id: str = Field(min_length=1, max_length=160)
    system_answer_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=4000)
    answer_status: Literal["answered", "abstained_insufficient_evidence", "failed"]
    answer: str | None = None
    answer_type: str | None = Field(default=None, max_length=80)
    context_evidence: list[P09ClaimCitationReviewEvidence] = Field(default_factory=list)
    claims: list[P09ClaimCitationReviewClaim] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_claim_boundary(self) -> P09ClaimCitationReviewCase:
        if self.answer_status == "answered" and not self.claims:
            raise ValueError("answered review Cases require system Claims")
        if self.answer_status != "answered" and self.claims:
            raise ValueError("non-answered review Cases cannot carry system Claims")
        return self


class P09ClaimCitationPhase1Package(DatasetEnvelope):
    schema_version: Literal["courserag.p09-claim-citation-phase1-package.v1"] = (
        "courserag.p09-claim-citation-phase1-package.v1"
    )
    phase: Literal["claim_citation_support_blinded"] = "claim_citation_support_blinded"
    scope: Literal["fixed_p09_answer_grounding_main_dev"] = "fixed_p09_answer_grounding_main_dev"
    test_access: Literal[False] = False
    source_report_sha256: Sha256
    source_checkpoint_sha256: Sha256
    approved_gold_bundle_sha256: Sha256
    approved_qa_sha256: Sha256
    case_count: int = Field(ge=1)
    answered_case_count: int = Field(ge=0)
    abstained_case_count: int = Field(ge=0)
    failed_case_count: int = Field(ge=0)
    system_claim_count: int = Field(ge=0)
    citation_link_count: int = Field(ge=0)
    cases: list[P09ClaimCitationReviewCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> P09ClaimCitationPhase1Package:
        if self.case_count != len(self.cases):
            raise ValueError("phase-1 Case count does not match payload")
        statuses = [item.answer_status for item in self.cases]
        if self.answered_case_count != statuses.count("answered"):
            raise ValueError("phase-1 answered count does not match payload")
        if self.abstained_case_count != statuses.count("abstained_insufficient_evidence"):
            raise ValueError("phase-1 abstained count does not match payload")
        if self.failed_case_count != statuses.count("failed"):
            raise ValueError("phase-1 failed count does not match payload")
        claims = [claim for item in self.cases for claim in item.claims]
        if self.system_claim_count != len(claims):
            raise ValueError("phase-1 Claim count does not match payload")
        if self.citation_link_count != sum(len(claim.citations) for claim in claims):
            raise ValueError("phase-1 Citation count does not match payload")
        return self


class P09ClaimCitationSupportLinkDecision(StrictModel):
    citation_id: str = Field(min_length=1, max_length=160)
    supports_claim: bool | None = None


class P09ClaimCitationSupportClaimDecision(StrictModel):
    system_claim_id: str = Field(min_length=1, max_length=160)
    label: (
        Literal[
            "correct_supported",
            "correct_but_uncited",
            "unsupported",
            "contradictory",
            "irrelevant",
        ]
        | None
    ) = None
    citations: list[P09ClaimCitationSupportLinkDecision] = Field(min_length=1)
    notes: str = Field(default="", max_length=4000)


class P09ClaimCitationSupportCaseDecision(StrictModel):
    case_id: str = Field(min_length=1, max_length=160)
    system_answer_id: str = Field(min_length=1, max_length=160)
    reviewed: bool = False
    conciseness_pass: bool | None = None
    claims: list[P09ClaimCitationSupportClaimDecision] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)


class P09ClaimCitationPhase1Decisions(DatasetEnvelope):
    schema_version: Literal["courserag.p09-claim-citation-phase1-decisions.v1"] = (
        "courserag.p09-claim-citation-phase1-decisions.v1"
    )
    source_package_sha256: Sha256
    review_status: Literal["draft", "submitted"] = "draft"
    reviewer_id: str | None = Field(default=None, min_length=1, max_length=160)
    cases: list[P09ClaimCitationSupportCaseDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_submission(self) -> P09ClaimCitationPhase1Decisions:
        if self.review_status == "draft":
            return self
        if self.reviewer_id is None:
            raise ValueError("submitted phase-1 decisions require reviewer_id")
        for case in self.cases:
            if not case.reviewed:
                raise ValueError("submitted phase-1 decisions require every Case review")
            for claim in case.claims:
                if claim.label is None or any(
                    citation.supports_claim is None for citation in claim.citations
                ):
                    raise ValueError(
                        "submitted phase-1 decisions require every Claim and Citation label"
                    )
                supported = any(bool(item.supports_claim) for item in claim.citations)
                if claim.label == "correct_supported" and not supported:
                    raise ValueError("correct_supported Claims require a supporting Citation")
                if claim.label != "correct_supported" and supported:
                    raise ValueError("only correct_supported Claims may have a supporting Citation")
        return self


class P09ClaimCitationPhase1Approval(DatasetEnvelope):
    schema_version: Literal["courserag.p09-claim-citation-phase1-approval.v1"] = (
        "courserag.p09-claim-citation-phase1-approval.v1"
    )
    status: Literal["approved"] = "approved"
    reviewer_id: str = Field(min_length=1, max_length=160)
    approval_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_package_sha256: Sha256
    decisions_sha256: Sha256
    approval_statement: str = Field(min_length=1, max_length=1000)
    approval_statement_sha256: Sha256

    @model_validator(mode="after")
    def validate_statement_hash(self) -> P09ClaimCitationPhase1Approval:
        actual = hashlib.sha256(self.approval_statement.encode("utf-8")).hexdigest()
        if actual != self.approval_statement_sha256:
            raise ValueError("phase-1 approval statement Hash must bind exact text")
        return self


class P09ClaimCitationPhase2Citation(StrictModel):
    citation_id: str = Field(min_length=1, max_length=160)
    supports_claim: bool
    cited_evidence_id: str = Field(min_length=1, max_length=160)
    evidence: P09ClaimCitationReviewEvidence


class P09ClaimCitationPhase2SystemClaim(StrictModel):
    system_claim_id: str = Field(min_length=1, max_length=160)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    text_sha256: Sha256
    phase1_label: Literal[
        "correct_supported",
        "correct_but_uncited",
        "unsupported",
        "contradictory",
        "irrelevant",
    ]
    citations: list[P09ClaimCitationPhase2Citation] = Field(min_length=1)


class P09ClaimCitationPhase2GoldSupport(StrictModel):
    evidence_id: str = Field(min_length=1, max_length=160)
    support_role: Literal["primary", "supporting"]
    exact_support_excerpt: str = Field(min_length=1, max_length=20_000)
    exact_support_excerpt_sha256: Sha256


class P09ClaimCitationPhase2GoldClaim(StrictModel):
    gold_claim_id: str = Field(min_length=1, max_length=160)
    text: str = Field(min_length=1, max_length=8000)
    text_sha256: Sha256
    required_evidence_ids: list[str] = Field(min_length=1)
    supports: list[P09ClaimCitationPhase2GoldSupport] = Field(min_length=1)


class P09ClaimCitationPhase2Case(StrictModel):
    case_id: str = Field(min_length=1, max_length=160)
    system_answer_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=4000)
    answerable: bool
    answer_status: Literal["answered", "abstained_insufficient_evidence", "failed"]
    answer: str | None = None
    phase1_conciseness_pass: bool | None = None
    system_claims: list[P09ClaimCitationPhase2SystemClaim] = Field(default_factory=list)
    required_gold_claims: list[P09ClaimCitationPhase2GoldClaim] = Field(default_factory=list)


class P09ClaimCitationPhase2Package(DatasetEnvelope):
    schema_version: Literal["courserag.p09-claim-citation-phase2-package.v1"] = (
        "courserag.p09-claim-citation-phase2-package.v1"
    )
    phase: Literal["gold_claim_mapping"] = "gold_claim_mapping"
    scope: Literal["fixed_p09_answer_grounding_main_dev"] = "fixed_p09_answer_grounding_main_dev"
    test_access: Literal[False] = False
    phase1_package_sha256: Sha256
    phase1_decisions_sha256: Sha256
    phase1_approval_sha256: Sha256
    approved_gold_bundle_sha256: Sha256
    approved_qa_sha256: Sha256
    case_count: int = Field(ge=1)
    system_claim_count: int = Field(ge=0)
    required_gold_claim_count: int = Field(ge=0)
    cases: list[P09ClaimCitationPhase2Case] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> P09ClaimCitationPhase2Package:
        if self.case_count != len(self.cases):
            raise ValueError("phase-2 Case count does not match payload")
        if self.system_claim_count != sum(len(item.system_claims) for item in self.cases):
            raise ValueError("phase-2 system Claim count does not match payload")
        if self.required_gold_claim_count != sum(
            len(item.required_gold_claims) for item in self.cases
        ):
            raise ValueError("phase-2 Gold Claim count does not match payload")
        return self


class P09ClaimCitationPhase2ClaimMapping(StrictModel):
    system_claim_id: str = Field(min_length=1, max_length=160)
    matched_gold_claim_ids: list[str] = Field(default_factory=list)


class P09ClaimCitationPhase2CaseDecision(StrictModel):
    case_id: str = Field(min_length=1, max_length=160)
    system_answer_id: str = Field(min_length=1, max_length=160)
    reviewed: bool = False
    mappings: list[P09ClaimCitationPhase2ClaimMapping] = Field(default_factory=list)
    missed_gold_claim_ids: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=4000)


class P09ClaimCitationPhase2Decisions(DatasetEnvelope):
    schema_version: Literal["courserag.p09-claim-citation-phase2-decisions.v1"] = (
        "courserag.p09-claim-citation-phase2-decisions.v1"
    )
    source_package_sha256: Sha256
    review_status: Literal["draft", "submitted"] = "draft"
    reviewer_id: str | None = Field(default=None, min_length=1, max_length=160)
    cases: list[P09ClaimCitationPhase2CaseDecision] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_submission(self) -> P09ClaimCitationPhase2Decisions:
        if self.review_status == "submitted":
            if self.reviewer_id is None:
                raise ValueError("submitted phase-2 decisions require reviewer_id")
            if any(not case.reviewed for case in self.cases):
                raise ValueError("submitted phase-2 decisions require every Case review")
        return self


class P09ClaimCitationPhase2Approval(DatasetEnvelope):
    schema_version: Literal["courserag.p09-claim-citation-phase2-approval.v1"] = (
        "courserag.p09-claim-citation-phase2-approval.v1"
    )
    status: Literal["approved"] = "approved"
    reviewer_id: str = Field(min_length=1, max_length=160)
    approval_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_package_sha256: Sha256
    decisions_sha256: Sha256
    approval_statement: str = Field(min_length=1, max_length=1000)
    approval_statement_sha256: Sha256

    @model_validator(mode="after")
    def validate_statement_hash(self) -> P09ClaimCitationPhase2Approval:
        actual = hashlib.sha256(self.approval_statement.encode("utf-8")).hexdigest()
        if actual != self.approval_statement_sha256:
            raise ValueError("phase-2 approval statement Hash must bind exact text")
        return self


class CitationMigrationCase(ReviewableRecord):
    before_document_sha256: Sha256
    after_document_sha256: Sha256
    old_evidence_id: str
    expected_status: Literal["valid", "migrated", "needs_review", "invalid"]
    expected_new_evidence_id: str | None = None
    change_description: str = Field(min_length=1, max_length=2000)


class DS6CitationMigrationDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds6.v1"] = "courserag.ds6.v1"
    cases: list[CitationMigrationCase] = Field(default_factory=list)


class IncrementalWritebackCase(ReviewableRecord):
    operation: Literal[
        "rename_document",
        "modify_section",
        "add_section",
        "delete_section",
        "replace_ocr_page",
        "change_chunker",
        "change_kp_prompt",
        "change_embedding",
        "change_reranker",
        "writeback",
        "trigger_enrichment",
    ]
    affected_section_ids: list[str] = Field(default_factory=list)
    reusable_artifact_ids: list[str] = Field(default_factory=list)
    should_trigger_kp_extraction: bool
    should_create_index_version: bool
    preserve_review_status: bool


class DS7IncrementalWritebackDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds7.v1"] = "courserag.ds7.v1"
    cases: list[IncrementalWritebackCase] = Field(default_factory=list)


class PerformanceWorkloadCase(ReviewableRecord):
    workload_type: Literal[
        "full_build",
        "single_document_build",
        "single_section_update",
        "ocr_batch",
        "enrichment_batch",
        "search",
        "search_rerank",
        "context",
        "qa",
        "qa_abstention",
    ]
    referenced_case_ids: list[str] = Field(default_factory=list)
    cold_start: bool
    repetitions: int = Field(default=1, ge=1, le=1000)


class DS8PerformanceDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds8.v1"] = "courserag.ds8.v1"
    cases: list[PerformanceWorkloadCase] = Field(default_factory=list)
