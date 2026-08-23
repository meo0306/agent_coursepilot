from __future__ import annotations

from pydantic import BaseModel, Field

from coursepilot.domain.ppt import PPTArtifact


class PPTExportV2Request(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    artifact: PPTArtifact


class PPTWritebackV2Request(BaseModel):
    artifact_version_id: str = Field(min_length=1)
    artifact: PPTArtifact
    slide_id: str = Field(min_length=1)
    component: str = Field(pattern="^(slide|speaker_notes)$")
    evidence_ids: list[str] = Field(default_factory=list)
    approval_record_id: str = Field(min_length=1)
