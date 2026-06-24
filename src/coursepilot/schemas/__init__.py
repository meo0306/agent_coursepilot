"""CoursePilot Pydantic schemas."""

from coursepilot.schemas.course_schema import CourseCreate, CourseRead, CourseUpdate
from coursepilot.schemas.document_schema import DocumentBuildResponse, DocumentRead
from coursepilot.schemas.kb_schema import KBSearchRequest, KBSearchResponse, KBSearchResult
from coursepilot.schemas.lesson_schema import (
    ExportFileRead,
    LessonDesignContent,
    LessonDesignRead,
    LessonGenerationParams,
    LessonGenerationResponse,
    LessonRevisionRequest,
    LessonRevisionResponse,
    LessonValidationReport,
)

__all__ = [
    "CourseCreate",
    "CourseRead",
    "CourseUpdate",
    "DocumentBuildResponse",
    "DocumentRead",
    "KBSearchRequest",
    "KBSearchResponse",
    "KBSearchResult",
    "ExportFileRead",
    "LessonDesignContent",
    "LessonDesignRead",
    "LessonGenerationParams",
    "LessonGenerationResponse",
    "LessonRevisionRequest",
    "LessonRevisionResponse",
    "LessonValidationReport",
]
