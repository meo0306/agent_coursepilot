from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
RecordId = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9_.:-]+$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewStatus(StrEnum):
    CANDIDATE = "candidate"
    NEEDS_REVIEW = "needs_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class DatasetSplit(StrEnum):
    PILOT = "pilot"
    DEV = "dev"
    TEST = "test"


class RunIntent(StrEnum):
    SMOKE = "smoke"
    TUNING = "tuning"
    EVALUATION = "evaluation"
    REPLAY = "replay"


class FallbackPolicy(StrEnum):
    NOT_APPLICABLE = "not_applicable"
    FAIL_SAMPLE = "fail_sample"
    FAIL_RUN = "fail_run"
    ALLOW_RECORDED = "allow_recorded"


class ApprovalRecord(StrictModel):
    review_id: RecordId
    reviewer_id: RecordId
    reviewed_at: datetime
    candidate_sha256: Sha256
    approved_record_sha256: Sha256
    notes: str = Field(default="", max_length=4000)


class ReviewLogEntry(StrictModel):
    review_id: RecordId
    record_id: RecordId
    action: Literal["approve", "reject", "request_changes"]
    reviewer_id: RecordId
    reviewed_at: datetime
    candidate_sha256: Sha256
    resulting_record_sha256: Sha256 | None = None
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_result_hash(self) -> ReviewLogEntry:
        if self.action == "approve" and self.resulting_record_sha256 is None:
            raise ValueError("approval review entries require a resulting record hash")
        if self.action != "approve" and self.resulting_record_sha256 is not None:
            raise ValueError("only approval review entries may contain a resulting record hash")
        return self


class ReviewableRecord(StrictModel):
    record_id: RecordId
    review_status: ReviewStatus = ReviewStatus.CANDIDATE
    candidate_source: str = Field(default="human", min_length=1, max_length=80)
    approval: ApprovalRecord | None = None

    @model_validator(mode="after")
    def validate_approval_boundary(self) -> ReviewableRecord:
        if self.review_status is ReviewStatus.APPROVED and self.approval is None:
            raise ValueError("approved records require an explicit human approval record")
        if self.review_status is not ReviewStatus.APPROVED and self.approval is not None:
            raise ValueError("only approved records may contain approval metadata")
        return self


class SourceSpan(StrictModel):
    document_id: RecordId
    document_version: str = Field(min_length=1, max_length=120)
    document_sha256: Sha256
    section_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    block_start: str | None = Field(default=None, max_length=160)
    block_end: str | None = Field(default=None, max_length=160)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def validate_locator(self) -> SourceSpan:
        has_pages = self.page_start is not None or self.page_end is not None
        has_blocks = self.block_start is not None or self.block_end is not None
        has_chars = self.char_start is not None or self.char_end is not None
        if not (has_pages or has_blocks or has_chars):
            raise ValueError("source span requires page, block, or character coordinates")
        if has_pages and (self.page_start is None or self.page_end is None):
            raise ValueError("page_start and page_end must be supplied together")
        if has_pages and self.page_start is not None and self.page_end is not None:
            if self.page_end < self.page_start:
                raise ValueError("page_end must be greater than or equal to page_start")
        if has_blocks and (self.block_start is None or self.block_end is None):
            raise ValueError("block_start and block_end must be supplied together")
        if has_chars and (self.char_start is None or self.char_end is None):
            raise ValueError("char_start and char_end must be supplied together")
        if has_chars and self.char_start is not None and self.char_end is not None:
            if self.char_end <= self.char_start:
                raise ValueError("char_end must be greater than char_start")
        return self


class HashedArtifact(StrictModel):
    path: str = Field(min_length=1, max_length=1024)
    sha256: Sha256
    size_bytes: int = Field(ge=0)
    media_type: str | None = Field(default=None, max_length=160)


class CandidateRevisionArtifact(StrictModel):
    revision: int = Field(ge=1)
    candidate_relative_path: str = Field(min_length=1, max_length=1024)
    candidate_file_sha256: Sha256
    status: Literal[
        "superseded",
        "pending_course_owner_review",
        "approved",
        "rejected",
    ]
    reason: str = Field(min_length=1, max_length=4000)


class CandidateRevisionHistory(StrictModel):
    schema_version: Literal["course-eval.candidate-revision-history.v1"] = (
        "course-eval.candidate-revision-history.v1"
    )
    dataset_id: RecordId
    dataset_version: str = Field(min_length=1, max_length=80)
    revisions: list[CandidateRevisionArtifact] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_revision_history(self) -> CandidateRevisionHistory:
        revisions = [entry.revision for entry in self.revisions]
        paths = [entry.candidate_relative_path for entry in self.revisions]
        if revisions != sorted(revisions) or len(revisions) != len(set(revisions)):
            raise ValueError("Candidate revisions must be unique and sorted")
        if len(paths) != len(set(paths)):
            raise ValueError("Candidate revision paths must be unique")
        return self


class TestLock(StrictModel):
    schema_version: str = "course-eval.test-lock.v1"
    dataset_id: RecordId
    dataset_version: str = Field(min_length=1, max_length=80)
    locked: bool = False
    test_ids_sha256: Sha256 | None = None
    approved_manifest_sha256: Sha256 | None = None
    locked_at: datetime | None = None
    locked_by: RecordId | None = None

    @model_validator(mode="after")
    def validate_locked_state(self) -> TestLock:
        required = (
            self.test_ids_sha256,
            self.approved_manifest_sha256,
            self.locked_at,
            self.locked_by,
        )
        if self.locked and any(value is None for value in required):
            raise ValueError("locked test sets require hashes, locked_at, and locked_by")
        if not self.locked and any(value is not None for value in required):
            raise ValueError("unlocked test sets must not carry lock approval metadata")
        return self


class MetricResult(StrictModel):
    name: str = Field(min_length=1, max_length=160)
    value: float | None
    numerator: float
    denominator: float
    applicable: bool
    details: dict[str, float | int | str | bool | None] = Field(default_factory=dict)

    @classmethod
    def ratio(
        cls,
        name: str,
        numerator: float,
        denominator: float,
        *,
        details: dict[str, float | int | str | bool | None] | None = None,
    ) -> MetricResult:
        applicable = denominator > 0
        return cls(
            name=name,
            value=numerator / denominator if applicable else None,
            numerator=numerator,
            denominator=denominator,
            applicable=applicable,
            details=details or {},
        )


class HumanReviewMetadata(StrictModel):
    review_id: RecordId
    reviewer_id: RecordId
    rubric_version: str = Field(min_length=1, max_length=120)
    reviewed_at: datetime
    blinded_sample_id: RecordId
    review_status: ReviewStatus = ReviewStatus.CANDIDATE
    notes: str = Field(default="", max_length=8000)
