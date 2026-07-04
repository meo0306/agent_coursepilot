from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coursepilot.schemas.lesson_schema import Reference

SlideType = Literal["title", "objectives", "content", "activity", "summary", "references"]


class PPTGenerationParams(BaseModel):
    slide_count: int | None = Field(default=None, ge=3, le=60)
    style_template: str = "standard"
    include_references: bool = True
    additional_requirements: str | None = None


class SlideItem(BaseModel):
    slide_index: int = Field(ge=1)
    slide_type: SlideType
    title: str = Field(min_length=1)
    bullet_points: list[str] = Field(min_length=1)
    speaker_notes: str | None = None
    references: list[Reference] = Field(default_factory=list)
    source_session_index: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_references_slide(self):
        if self.slide_type == "references" and not self.references:
            raise ValueError("references slide requires at least one reference")
        return self


class SlideOutlineContent(BaseModel):
    course_name: str
    chapter: str
    lesson_id: str
    style_template: str = "standard"
    slides: list[SlideItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_slide_indices(self):
        expected = list(range(1, len(self.slides) + 1))
        actual = [slide.slide_index for slide in self.slides]
        if actual != expected:
            raise ValueError("slide_index values must be continuous from 1")
        return self


class SlideValidationReport(BaseModel):
    schema_valid: bool = True
    slide_count_valid: bool
    slide_type_valid: bool
    content_not_empty: bool
    source_session_valid: bool
    citation_valid: bool
    errors: list[str] = Field(default_factory=list)
    repair_attempts: int = 0

    @property
    def passed(self) -> bool:
        return all(
            [
                self.schema_valid,
                self.slide_count_valid,
                self.slide_type_valid,
                self.content_not_empty,
                self.source_session_valid,
                self.citation_valid,
            ]
        )


class SlideOutlineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    task_id: str
    lesson_design_id: str
    status: str
    outline_json: dict
    validation_report_json: dict
    pptx_file_id: str | None
    created_at: datetime
    updated_at: datetime


class PPTGenerationResponse(BaseModel):
    outline_id: str
    task_id: str
    status: str
    outline: SlideOutlineContent
    validation_report: SlideValidationReport


class PPTExportResponse(BaseModel):
    outline_id: str
    file_id: str
    file_name: str
    file_path: str
    file_role: str = "pptx"
