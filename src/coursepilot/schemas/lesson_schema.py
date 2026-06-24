from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coursepilot.schemas.kb_schema import KBSearchResult


class LessonGenerationParams(BaseModel):
    chapter_range: str = Field(min_length=1)
    total_sessions: int = Field(default=2, ge=1, le=12)
    session_duration: int = Field(default=45, ge=15, le=240)
    student_level: str | None = None
    student_background: str | None = None
    teaching_template: str = "standard"
    teaching_focus: str | None = None
    include_interaction: bool = True
    include_homework: bool = True
    additional_requirements: str | None = None


class Reference(BaseModel):
    chunk_id: str
    source_type: str | None = None
    chapter: str | None = None
    page: int | None = None


class TimeAllocation(BaseModel):
    activity: str = Field(min_length=1)
    minutes: int = Field(ge=1)


class TeachingProcessItem(BaseModel):
    stage: str = Field(min_length=1)
    minutes: int = Field(ge=1)
    content: str = Field(min_length=1)


class SessionPlan(BaseModel):
    session_index: int = Field(ge=1)
    session_title: str = Field(min_length=1)
    duration: int = Field(ge=1)
    knowledge_points: list[str] = Field(min_length=1)
    teaching_focus: str = Field(min_length=1)
    difficulty_points: list[str] = Field(default_factory=list)
    time_allocation: list[TimeAllocation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_sum(self):
        total_minutes = sum(item.minutes for item in self.time_allocation)
        if total_minutes != self.duration:
            raise ValueError("time_allocation minutes must equal duration")
        return self


class LessonSession(BaseModel):
    session_index: int = Field(ge=1)
    session_title: str = Field(min_length=1)
    teaching_objectives: list[str] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    difficult_points: list[str] = Field(default_factory=list)
    teaching_process: list[TeachingProcessItem] = Field(min_length=1)
    interaction_design: list[str] = Field(default_factory=list)
    blackboard_or_slide_suggestions: list[str] = Field(default_factory=list)
    homework_suggestion: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(min_length=1)


class LessonDesignContent(BaseModel):
    course_name: str
    chapter: str
    total_sessions: int
    session_duration: int
    retrieved_contexts: list[KBSearchResult] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    session_plan: list[SessionPlan]
    sessions: list[LessonSession]


class LessonValidationReport(BaseModel):
    schema_valid: bool = True
    session_count_valid: bool
    time_allocation_valid: bool
    required_fields_valid: bool
    knowledge_coverage_valid: bool
    citation_valid: bool
    errors: list[str] = Field(default_factory=list)
    repair_attempts: int = 0

    @property
    def passed(self) -> bool:
        return all(
            [
                self.schema_valid,
                self.session_count_valid,
                self.time_allocation_valid,
                self.required_fields_valid,
                self.knowledge_coverage_valid,
                self.citation_valid,
            ]
        )


class LessonDesignRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    task_id: str
    chapter: str
    status: str
    total_sessions: int
    content_json: dict
    validation_report_json: dict
    created_at: datetime
    updated_at: datetime


class LessonGenerationResponse(BaseModel):
    lesson_id: str
    task_id: str
    status: str
    lesson_design: LessonDesignContent
    validation_report: LessonValidationReport


class LessonRevisionRequest(BaseModel):
    target_scope: str = Field(min_length=1)
    feedback_text: str = Field(min_length=1)
    keep_unchanged_parts: bool = True


class LessonRevisionResponse(BaseModel):
    lesson_id: str
    modification_summary: str
    lesson_design: LessonDesignContent
    validation_report: LessonValidationReport


class ExportFileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    task_id: str | None
    file_type: str
    file_name: str
    file_path: str
    file_role: str
    created_at: datetime

