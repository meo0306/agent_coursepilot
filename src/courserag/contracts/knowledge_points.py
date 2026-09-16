from __future__ import annotations

from pydantic import Field

from courserag.contracts.common import ContractModel, RequestContext, ResponseMeta


class KnowledgePointSnapshotRequest(ContractModel):
    """Read-only CourseRAG contract consumed by generation workflows."""

    context: RequestContext = Field(default_factory=RequestContext)
    course_id: str = Field(min_length=1)
    section_ids: list[str] = Field(default_factory=list)
    include_unreviewed: bool = False
    limit: int = Field(default=500, ge=1, le=500)


class KnowledgePointEvidenceLink(ContractModel):
    evidence_id: str = Field(min_length=1)
    role: str = "support"
    strength: float = Field(default=1.0, ge=0.0, le=1.0)


class KnowledgePointSnapshotItem(ContractModel):
    knowledge_point_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    canonical_name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    summary: str | None = None
    review_status: str = "approved"
    version: int = Field(default=1, ge=1)
    section_ids: list[str] = Field(default_factory=list)
    evidence_links: list[KnowledgePointEvidenceLink] = Field(default_factory=list)


class KnowledgePointSnapshot(ContractModel):
    meta: ResponseMeta
    course_id: str = Field(min_length=1)
    items: list[KnowledgePointSnapshotItem] = Field(default_factory=list)
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
