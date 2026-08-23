from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from coursepilot.domain.common import DomainModel, canonical_sha256

SlideType = Literal[
    "title",
    "agenda",
    "objectives",
    "concept",
    "process",
    "comparison",
    "example",
    "activity",
    "summary",
    "references",
]
AssetKind = Literal["none", "editable_table", "editable_shape", "replaceable_image"]


class SlideCitation(DomainModel):
    evidence_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    source_document_id: str = Field(min_length=1)
    source_document_version: str = Field(min_length=1)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SlideAssetPlaceholder(DomainModel):
    asset_id: str = Field(min_length=1)
    kind: AssetKind
    description: str = Field(min_length=1)
    alt_text: str = Field(min_length=1)
    editable: bool = True


class SlidePlan(DomainModel):
    slide_id: str = Field(min_length=1)
    slide_index: int = Field(ge=1)
    slide_type: SlideType
    layout_role: str = Field(min_length=1)
    title_intent: str = Field(min_length=1)
    source_session_index: int | None = Field(default=None, ge=1)
    knowledge_point_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    max_bullets: int = Field(default=4, ge=1, le=20)
    max_chars_per_bullet: int = Field(default=72, ge=10, le=500)
    notes_required: bool = True
    citation_required: bool = True
    asset_kind: AssetKind = "none"
    assets: list[SlideAssetPlaceholder] = Field(default_factory=list)
    predecessor_slide_ids: list[str] = Field(default_factory=list)


class SlideArchitecture(DomainModel):
    course_id: str = Field(min_length=1)
    lesson_artifact_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    template_snapshot_id: str = Field(min_length=1)
    slide_count: int = Field(ge=3, le=80)
    plans: list[SlidePlan] = Field(min_length=3)
    context_evidence_ids: list[str] = Field(default_factory=list)
    architecture_version: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_order(self) -> SlideArchitecture:
        if self.slide_count != len(self.plans):
            raise ValueError("slide_count must equal the number of plans")
        if [p.slide_index for p in self.plans] != list(range(1, self.slide_count + 1)):
            raise ValueError("slide indexes must be contiguous")
        if self.plans[0].slide_type != "title":
            raise ValueError("the first slide must be a title slide")
        if self.plans[-1].slide_type != "references":
            raise ValueError("the last slide must be a references slide")
        allowed = set(self.context_evidence_ids)
        for plan in self.plans:
            if not set(plan.evidence_ids) <= allowed:
                raise ValueError("slide Evidence IDs must be in the Context package")
        return self

    @property
    def content_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class SlideContent(DomainModel):
    slide_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    bullets: list[str] = Field(default_factory=list)
    body_text: str = ""
    speaker_notes: str = ""
    citations: list[SlideCitation] = Field(default_factory=list)
    assets: list[SlideAssetPlaceholder] = Field(default_factory=list)
    content_sha256: str | None = None

    @model_validator(mode="after")
    def validate_hash(self) -> SlideContent:
        expected = canonical_sha256(
            {
                "slide_id": self.slide_id,
                "title": self.title,
                "bullets": self.bullets,
                "body_text": self.body_text,
                "speaker_notes": self.speaker_notes,
                "citations": [c.model_dump(mode="json") for c in self.citations],
                "assets": [a.model_dump(mode="json") for a in self.assets],
            }
        )
        if self.content_sha256 is not None and self.content_sha256 != expected:
            raise ValueError("slide content hash mismatch")
        object.__setattr__(self, "content_sha256", expected)
        return self


class PPTRenderReport(DomainModel):
    renderer: str
    renderer_version: str
    source_pptx_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rendered_pdf_sha256: str | None = None
    slide_png_sha256s: list[str] = Field(default_factory=list)
    slide_count: int = Field(ge=0)
    opened: bool = False
    rendered: bool = False
    severe_overflow_count: int = Field(default=0, ge=0)
    out_of_bounds_count: int = Field(default=0, ge=0)
    empty_required_placeholder_count: int = Field(default=0, ge=0)
    editable_object_count: int = Field(default=0, ge=0)
    warnings: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.opened
            and self.rendered
            and self.severe_overflow_count == 0
            and self.out_of_bounds_count == 0
            and self.empty_required_placeholder_count == 0
        )


class PPTArtifact(DomainModel):
    course_id: str = Field(min_length=1)
    lesson_artifact_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    template_snapshot_id: str = Field(min_length=1)
    architecture: SlideArchitecture
    slides: list[SlideContent] = Field(min_length=3)
    render_report: PPTRenderReport | None = None

    @model_validator(mode="after")
    def validate_slides(self) -> PPTArtifact:
        expected = [p.slide_id for p in self.architecture.plans]
        actual = [s.slide_id for s in self.slides]
        if actual != expected:
            raise ValueError("PPT slides must follow Architecture order")
        return self
