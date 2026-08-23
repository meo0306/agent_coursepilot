from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import Field, model_validator

from coursepilot.domain.common import DomainModel, canonical_sha256

QuestionType = Literal["single_choice", "multiple_choice", "judgement", "short_answer"]
Difficulty = Literal["easy", "medium", "hard"]
ContentRole = Literal[
    "definition",
    "principle",
    "procedure",
    "comparison",
    "application",
    "formula",
    "table",
    "example",
]


class EvidenceRef(DomainModel):
    evidence_id: str = Field(min_length=1)
    knowledge_point_id: str | None = None


class OptionAssessment(DomainModel):
    """Evidence-bound correctness decision for one objective-question option."""

    is_correct: bool
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class QuestionSlotPlan(DomainModel):
    slot_id: str = Field(min_length=1)
    question_type: QuestionType
    score: int = Field(gt=0)
    difficulty: Difficulty = "medium"
    content_role: ContentRole = "definition"
    target_id: str = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class QuestionBatchPlan(DomainModel):
    batch_id: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    question_type: QuestionType
    slot_ids: list[str] = Field(min_length=1, max_length=5)


class ExamBlueprintV2(DomainModel):
    blueprint_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    chapter_range: str = Field(min_length=1)
    context_package_id: str = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)
    slots: list[QuestionSlotPlan] = Field(min_length=1)
    batches: list[QuestionBatchPlan] = Field(min_length=1)
    max_concurrency: int = Field(ge=1, le=8, default=3)
    duplicate_similarity_threshold: float = Field(ge=0.0, le=1.0, default=0.85)
    content_hash: str | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> ExamBlueprintV2:
        slot_ids = {slot.slot_id for slot in self.slots}
        if len(slot_ids) != len(self.slots):
            raise ValueError("slot_id must be unique")
        if any(
            not set(slot.knowledge_point_ids) <= set(self.knowledge_point_ids)
            for slot in self.slots
        ):
            raise ValueError("slot knowledge points must be in blueprint whitelist")
        if any(not set(slot.evidence_ids) <= set(self.evidence_ids) for slot in self.slots):
            raise ValueError("slot evidence must be in blueprint whitelist")
        planned = [slot for batch in self.batches for slot in batch.slot_ids]
        if sorted(planned) != sorted(slot_ids):
            raise ValueError("batches must cover every slot exactly once")
        if len(planned) != len(set(planned)):
            raise ValueError("a slot cannot occur in multiple batches")
        return self

    def stable_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_hash"})
        return canonical_sha256(payload)

    def with_hash(self) -> ExamBlueprintV2:
        return self.model_copy(update={"content_hash": self.stable_hash()})


class ExamQuestion(DomainModel):
    question_id: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)
    question_number: int = Field(ge=1)
    question_type: QuestionType
    score: int = Field(gt=0)
    difficulty: Difficulty
    content_role: ContentRole
    stimulus: str | None = None
    stem: str = Field(min_length=1)
    options: dict[str, str] = Field(default_factory=dict)
    option_assessments: dict[str, OptionAssessment] = Field(default_factory=dict)
    answer: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    knowledge_point_ids: list[str] = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)


class QuestionBatchResult(DomainModel):
    batch_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: Literal["succeeded", "failed", "needs_review"]
    questions: list[ExamQuestion] = Field(default_factory=list)
    issue_codes: list[str] = Field(default_factory=list)
    model_invocation_ids: list[str] = Field(default_factory=list)


class ExamArtifact(DomainModel):
    task_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    blueprint: ExamBlueprintV2
    questions: list[ExamQuestion] = Field(default_factory=list)
    blueprint_approved: bool = False
    global_review_approved: bool = False


class ExamGlobalReport(DomainModel):
    schema_valid: bool = True
    question_count_valid: bool = True
    score_valid: bool = True
    distribution_valid: bool = True
    coverage_valid: bool = True
    citation_resolvable: bool = True
    duplicate_valid: bool = True
    answer_leakage_valid: bool = True
    choice_contract_valid: bool = True
    answer_set_valid: bool = True
    stimulus_valid: bool = True
    duplicate_pairs: list[tuple[str, str]] = Field(default_factory=list)
    answer_leakage_question_ids: list[str] = Field(default_factory=list)
    cross_answer_leakage_pairs: list[tuple[str, str]] = Field(default_factory=list)
    choice_contract_question_ids: list[str] = Field(default_factory=list)
    answer_set_question_ids: list[str] = Field(default_factory=list)
    stimulus_question_ids: list[str] = Field(default_factory=list)
    question_issue_codes: dict[str, list[str]] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(
            (
                self.schema_valid,
                self.question_count_valid,
                self.score_valid,
                self.distribution_valid,
                self.coverage_valid,
                self.citation_resolvable,
                self.duplicate_valid,
                self.answer_leakage_valid,
                self.choice_contract_valid,
                self.answer_set_valid,
                self.stimulus_valid,
            )
        )


def question_id(blueprint_hash: str, slot_id: str) -> str:
    return hashlib.sha256(f"{blueprint_hash}:{slot_id}".encode()).hexdigest()[:32]


def batch_job_id(task_id: str, blueprint_hash: str, batch_id: str) -> str:
    return hashlib.sha256(f"{task_id}:{blueprint_hash}:{batch_id}".encode()).hexdigest()
