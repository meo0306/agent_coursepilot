from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RetrievalFilter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    course_id: str
    index_version_id: str
    document_ids: tuple[str, ...] = ()
    document_version_ids: tuple[str, ...] = ()
    section_ids: tuple[str, ...] = ()
    knowledge_point_ids: tuple[str, ...] = ()
    source_tiers: tuple[str, ...] = ()


class RetrievalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str | None = None
    document_version_id: str
    section_id: str | None = None
    source_tier: str = "primary_source"
    text: str = ""
    evidence_ids: tuple[str, ...] = ()
    knowledge_point_ids: tuple[str, ...] = ()
    dense_score: float | None = None
    sparse_score: float | None = None
    fusion_score: float | None = None
    rerank_score: float | None = None
    dense_rank: int | None = Field(default=None, ge=1)
    sparse_rank: int | None = Field(default=None, ge=1)
    fusion_rank: int | None = Field(default=None, ge=1)
    rerank_rank: int | None = Field(default=None, ge=1)

    def clone(self) -> RetrievalCandidate:
        return self.model_copy(deep=True)
