"""CoursePilot SQLAlchemy models registered with ``Base.metadata``."""

from coursepilot.models.chunk import KnowledgeChunk
from coursepilot.models.course import Course
from coursepilot.models.document import Document
from coursepilot.models.exam import ExamBlueprint
from coursepilot.models.export_file import ExportFile
from coursepilot.models.idempotency_record import IdempotencyRecord
from coursepilot.models.lesson import LessonDesign
from coursepilot.models.question import Question
from coursepilot.models.review_record import ReviewRecord
from coursepilot.models.runtime import (
    ApprovalRecord,
    ArtifactRecord,
    ArtifactVersionRecord,
    InterruptRecord,
    ModelInvocationRecord,
    NodeRunRecord,
    ResumeCommandRecord,
    SideEffectRunRecord,
    TemplateSnapshotRecord,
    WorkflowRunRecord,
)
from coursepilot.models.slide_outline import SlideOutline
from coursepilot.models.task import GenerationTask

__all__ = [
    "ApprovalRecord",
    "ArtifactRecord",
    "ArtifactVersionRecord",
    "Course",
    "Document",
    "ExamBlueprint",
    "ExportFile",
    "GenerationTask",
    "IdempotencyRecord",
    "KnowledgeChunk",
    "LessonDesign",
    "ModelInvocationRecord",
    "NodeRunRecord",
    "Question",
    "ReviewRecord",
    "SlideOutline",
    "TemplateSnapshotRecord",
    "WorkflowRunRecord",
    "InterruptRecord",
    "ResumeCommandRecord",
    "SideEffectRunRecord",
]
