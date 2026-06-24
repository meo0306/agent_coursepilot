from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CourseCreate(BaseModel):
    course_name: str = Field(min_length=1, max_length=255)
    course_type: str | None = None
    student_level: str | None = None
    student_background: str | None = None
    description: str | None = None


class CourseUpdate(BaseModel):
    course_name: str | None = Field(default=None, min_length=1, max_length=255)
    course_type: str | None = None
    student_level: str | None = None
    student_background: str | None = None
    description: str | None = None


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_name: str
    course_type: str | None
    student_level: str | None
    student_background: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime

