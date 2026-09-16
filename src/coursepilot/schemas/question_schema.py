import re
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
                raw_answer = self.correct_answer.strip()
                if raw_answer in self.options:
                    answers = {raw_answer}
                elif re.search(r"[,，、;/\s]", raw_answer):
                    answers = {item for item in re.split(r"[,，、;/\s]+", raw_answer) if item}
                else:
                    # Providers commonly serialize a set of single-character option
                    # keys as ``AB``. Accept that representation only when every
                    # character is an exact declared key; arbitrary text still fails.
                    answers = (
                        set(raw_answer) if all(key in self.options for key in raw_answer) else set()
                    )
                if not answers or not answers.issubset(set(self.options)):
                    raise ValueError("multiple_choice answer must match option keys")
                self.correct_answer = ",".join(key for key in self.options if key in answers)
        if self.question_type == "judgement":
            answer = self.correct_answer.strip()
            if self.options and answer in self.options:
                # Some providers express judgement answers through explicit
                # option keys (for example A=correct, B=incorrect). Resolve
                # only an exact declared key whose label is itself an accepted
                # judgement value; never guess from the key position.
                answer = self.options[answer].strip()
            lower_answer = answer.lower()
            if lower_answer in {"true", "false"}:
                self.correct_answer = lower_answer
            elif answer in {"\u6b63\u786e", "\u5bf9", "\u662f"}:
                self.correct_answer = "\u6b63\u786e"
            elif answer in {"\u9519\u8bef", "\u9519", "\u5426"}:
                self.correct_answer = "\u9519\u8bef"
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
