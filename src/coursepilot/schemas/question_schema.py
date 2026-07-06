from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coursepilot.schemas.lesson_schema import Reference

QuestionType = Literal["single_choice", "multiple_choice", "judgement", "short_answer"]
Difficulty = Literal["easy", "medium", "hard"]


class QuestionItem(BaseModel):
    question_type: QuestionType
    knowledge_point: str = Field(min_length=1)
    difficulty: Difficulty = "medium"
    score: int = Field(ge=1)
    question_text: str = Field(min_length=1)
    options: dict[str, str] | None = None
    correct_answer: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    references: list[Reference] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_objective_question(self):
        if self.question_type in {"single_choice", "multiple_choice"}:
            if not self.options or len(self.options) < 2:
                raise ValueError("choice questions require at least two options")
            if self.question_type == "single_choice" and self.correct_answer not in self.options:
                raise ValueError("single_choice answer must match an option key")
            if self.question_type == "multiple_choice":
                answers = {item.strip() for item in self.correct_answer.split(",") if item.strip()}
                if not answers or not answers.issubset(set(self.options)):
                    raise ValueError("multiple_choice answer must match option keys")
        if self.question_type == "judgement":
            answer = self.correct_answer.strip()
            lower_answer = answer.lower()
            if lower_answer in {"true", "false"}:
                self.correct_answer = lower_answer
            elif answer in {"\u6b63\u786e", "\u9519\u8bef"}:
                self.correct_answer = answer
            else:
                raise ValueError("judgement answer must be true/false or Chinese equivalents")
        return self


class QuestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    exam_blueprint_id: str
    question_type: str
    knowledge_point: str
    difficulty: str
    score: int
    question_text: str
    options_json: dict | None
    correct_answer: str
    explanation: str
    references_json: list[dict]
    status: str
    created_at: datetime
    updated_at: datetime


class QuestionSet(BaseModel):
    blueprint_id: str
    questions: list[QuestionItem]
