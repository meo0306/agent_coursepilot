from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.question_schema import QuestionItem, QuestionType


class ExamGenerationParams(BaseModel):
    chapter_range: str = Field(min_length=1)
    generation_type: Literal["homework", "exam"] = "exam"
    total_score: int | None = Field(default=None, ge=1)
    question_counts: dict[QuestionType, int] = Field(
        default_factory=lambda: {
            "single_choice": 5,
            "multiple_choice": 2,
            "judgement": 3,
            "short_answer": 2,
        }
    )
    score_per_question: dict[QuestionType, int] = Field(
        default_factory=lambda: {
            "single_choice": 2,
            "multiple_choice": 3,
            "judgement": 1,
            "short_answer": 10,
        }
    )
    difficulty_distribution: dict[str, float] = Field(
        default_factory=lambda: {"easy": 0.3, "medium": 0.5, "hard": 0.2}
    )
    include_answer: bool = True
    include_explanation: bool = True
    include_answer_sheet: bool = True
    additional_requirements: str | None = None

    @model_validator(mode="after")
    def validate_question_counts(self):
        if not self.question_counts or sum(self.question_counts.values()) <= 0:
            raise ValueError("question_counts must contain at least one question")
        for question_type, count in self.question_counts.items():
            if count < 0:
                raise ValueError(f"question count for {question_type} cannot be negative")
            if count > 0 and self.score_per_question.get(question_type, 0) <= 0:
                raise ValueError(f"score_per_question missing for {question_type}")
        return self


class QuestionGroupPlan(BaseModel):
    question_type: QuestionType
    count: int = Field(ge=0)
    score_each: int = Field(ge=1)
    total_score: int = Field(ge=0)
    knowledge_points: list[str] = Field(default_factory=list)
    difficulty: str = "medium"


class ExamBlueprintContent(BaseModel):
    course_name: str
    chapter_range: str
    generation_type: str
    total_score: int
    question_groups: list[QuestionGroupPlan]
    retrieved_contexts: list[KBSearchResult] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)


class ExamValidationReport(BaseModel):
    schema_valid: bool = True
    question_count_valid: bool
    score_valid: bool
    option_valid: bool
    answer_valid: bool
    explanation_valid: bool
    knowledge_coverage_valid: bool
    citation_valid: bool
    duplicate_valid: bool = True
    duplicate_rate: float = 0.0
    duplicate_questions: list[tuple[int, int]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    repair_attempts: int = 0

    @property
    def passed(self) -> bool:
        return all(
            [
                self.schema_valid,
                self.question_count_valid,
                self.score_valid,
                self.option_valid,
                self.answer_valid,
                self.explanation_valid,
                self.knowledge_coverage_valid,
                self.citation_valid,
            ]
        ) and self.duplicate_valid


class ExamBlueprintRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    task_id: str
    chapter_range: str
    status: str
    blueprint_json: dict
    created_at: datetime
    updated_at: datetime


class ExamBlueprintResponse(BaseModel):
    blueprint_id: str
    task_id: str
    status: str
    blueprint: ExamBlueprintContent


class QuestionGenerationResponse(BaseModel):
    blueprint_id: str
    status: str
    questions: list[QuestionItem]
    validation_report: ExamValidationReport


class ExamExportResponse(BaseModel):
    blueprint_id: str
    files: list[dict]
