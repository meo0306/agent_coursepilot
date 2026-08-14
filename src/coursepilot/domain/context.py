from __future__ import annotations

from pydantic import Field

from coursepilot.domain.common import DomainModel


class ContextPackageRef(DomainModel):
    context_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    index_version: str = Field(min_length=1)
    evidence_ids: list[str]
    token_count: int = Field(ge=0)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    trace_id: str = Field(min_length=1)
    warning_codes: list[str] = Field(default_factory=list)
