"""
CoursePilot application services.
新增的服务层，负责处理业务逻辑，形成
API route -> service -> ORM model/db
只负责创建任务、调用 graph、校验 graph 输出、持久化结果
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
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

_SERVICE_MODULES = {
    "CourseService": "coursepilot.services.course_service",
    "DocumentService": "coursepilot.services.document_service",
    "ExamService": "coursepilot.services.exam_service",
    "KnowledgeBaseService": "coursepilot.services.kb_service",
    "LessonService": "coursepilot.services.lesson_service",
    "PPTService": "coursepilot.services.ppt_service",
    "ReviewService": "coursepilot.services.review_service",
}


def __getattr__(name: str) -> object:
    """Preserve package exports without eagerly importing Agent Graphs."""

    module_name = _SERVICE_MODULES.get(name)
    if module_name is None:
        raise AttributeError(name)
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
