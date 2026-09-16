"""Layered validation contracts for generated CoursePilot artifacts."""

from coursepilot.validation.models import (
    IssueLayer,
    IssueScope,
    Severity,
    ValidationIssue,
    ValidationReport,
)
from coursepilot.validation.service import ValidationContext, ValidatorService

__all__ = [
    "IssueLayer",
    "IssueScope",
    "Severity",
    "ValidationContext",
    "ValidationIssue",
    "ValidationReport",
    "ValidatorService",
]
from coursepilot.validation.exam import (
    detect_answer_leakage,
    detect_duplicate_pairs,
    normalize_question_text,
    text_similarity,
    validate_exam_global,
)

__all__ = [
    "detect_answer_leakage",
    "detect_duplicate_pairs",
    "normalize_question_text",
    "text_similarity",
    "validate_exam_global",
]
