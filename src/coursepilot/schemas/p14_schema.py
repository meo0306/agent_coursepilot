from __future__ import annotations

from pydantic import BaseModel, Field

from coursepilot.domain.lesson import LessonArtifact


class LessonExportRequest(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    artifact: LessonArtifact
    output_filename: str = "lesson.docx"


class LessonWritebackRequest(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    artifact: LessonArtifact
    json_path: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    approval_record_id: str = Field(min_length=1)
