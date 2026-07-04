"""
CoursePilot SQLAlchemy  ORM 表 models.
Alembic 和 SQLAlchemy 需要 import models 后，表模型才会注册进 Base.metadata
"""

from coursepilot.models.chunk import KnowledgeChunk
from coursepilot.models.course import Course
from coursepilot.models.document import Document
from coursepilot.models.exam import ExamBlueprint
from coursepilot.models.export_file import ExportFile
from coursepilot.models.lesson import LessonDesign
from coursepilot.models.question import Question
from coursepilot.models.review_record import ReviewRecord
from coursepilot.models.slide_outline import SlideOutline
from coursepilot.models.task import GenerationTask

# 统一导出模型，避免迁移或测试漏掉某张表
__all__ = [
    "Course",
    "Document",
    "ExamBlueprint",
    "ExportFile",
    "GenerationTask",
    "KnowledgeChunk",
    "LessonDesign",
    "Question",
    "ReviewRecord",
    "SlideOutline",
]
