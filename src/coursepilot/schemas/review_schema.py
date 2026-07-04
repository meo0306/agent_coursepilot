from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal["approved", "rejected", "needs_revision"]
ReviewTargetType = Literal["ppt_outline", "lesson_design", "question"]


class ReviewCreate(BaseModel):
    target_type: ReviewTargetType
    target_id: str = Field(min_length=1)
    review_status: ReviewStatus
    comment: str | None = None


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    target_type: str
    target_id: str
    review_status: str
    comment: str | None
    write_back_status: str
    created_at: datetime


class ReviewWriteBackResponse(BaseModel):
    review_id: str
    target_type: str
    target_id: str
    write_back_status: str
    written_chunk_ids: list[str] = Field(default_factory=list)
