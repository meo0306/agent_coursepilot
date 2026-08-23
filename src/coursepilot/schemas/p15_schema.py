from __future__ import annotations

from pydantic import BaseModel, Field

from coursepilot.domain.exam import ExamArtifact


class ExamExportV2Request(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    artifact: ExamArtifact


class ExamWritebackV2Request(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    artifact: ExamArtifact
    question_id: str = Field(min_length=1)
    component: str = Field(pattern="^(question|explanation)$")
    evidence_ids: list[str] = Field(min_length=1)
    approval_record_id: str = Field(min_length=1)
