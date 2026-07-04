"""CoursePilot Pydantic schemas.
FastAPI 不应该直接把数据库对象暴露给外部，故用Schema来定义：
请求体应该长什么样。
响应体应该返回哪些字段。
必填字段和基础校验规则是什么。

"""

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
from coursepilot.schemas.exam_schema import (
    ExamBlueprintContent,
    ExamBlueprintRead,
    ExamBlueprintResponse,
    ExamExportResponse,
    ExamGenerationParams,
    ExamValidationReport,
    QuestionGenerationResponse,
    QuestionGroupPlan,
)
from coursepilot.schemas.question_schema import QuestionItem, QuestionRead, QuestionSet
from coursepilot.schemas.ppt_schema import (
    PPTExportResponse,
    PPTGenerationParams,
    PPTGenerationResponse,
    SlideItem,
    SlideOutlineContent,
    SlideOutlineRead,
    SlideValidationReport,
)
from coursepilot.schemas.review_schema import ReviewCreate, ReviewRead, ReviewWriteBackResponse

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
    "ExamBlueprintContent",
    "ExamBlueprintRead",
    "ExamBlueprintResponse",
    "ExamExportResponse",
    "ExamGenerationParams",
    "ExamValidationReport",
    "QuestionGenerationResponse",
    "QuestionGroupPlan",
    "QuestionItem",
    "QuestionRead",
    "QuestionSet",
    "PPTExportResponse",
    "PPTGenerationParams",
    "PPTGenerationResponse",
    "SlideItem",
    "SlideOutlineContent",
    "SlideOutlineRead",
    "SlideValidationReport",
    "ReviewCreate",
    "ReviewRead",
    "ReviewWriteBackResponse",
]
