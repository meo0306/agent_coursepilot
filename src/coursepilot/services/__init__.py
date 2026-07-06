"""
CoursePilot application services.
新增的服务层，负责处理业务逻辑，形成
API route -> service -> ORM model/db
只负责创建任务、调用 graph、校验 graph 输出、持久化结果
"""

from coursepilot.services.course_service import CourseService
from coursepilot.services.document_service import DocumentService
from coursepilot.services.exam_service import ExamService
from coursepilot.services.kb_service import KnowledgeBaseService
from coursepilot.services.lesson_service import LessonService
from coursepilot.services.ppt_service import PPTService
from coursepilot.services.review_service import ReviewService

__all__ = [
    "CourseService",
    "DocumentService",
    "ExamService",
    "KnowledgeBaseService",
    "LessonService",
    "PPTService",
    "ReviewService",
]
