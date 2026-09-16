from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ExpansionSource(StrEnum):
    RETRIEVAL = "retrieval"
    PARENT = "parent"
    PREVIOUS_NEIGHBOR = "previous_neighbor"
    NEXT_NEIGHBOR = "next_neighbor"


class ContextProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = "question_answering_v1"
    max_items: int = Field(default=8, ge=1)
    max_tokens: int = Field(default=4000, ge=1)
    deduplicate: bool = True
    include_neighbors_for: tuple[str, ...] = ("procedure", "comparison", "cross_section")
    preserve_evidence_boundaries: bool = True
