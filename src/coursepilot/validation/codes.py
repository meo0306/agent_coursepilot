from __future__ import annotations

from dataclasses import dataclass

from coursepilot.validation.models import IssueLayer, Severity


@dataclass(frozen=True)
class IssueCodeDefinition:
    code: str
    layer: IssueLayer
    severity: Severity
    auto_repairable: bool
    strategy: str


def _d(code: str, layer: str, severity: str, auto: bool, strategy: str) -> IssueCodeDefinition:
    return IssueCodeDefinition(code, IssueLayer(layer), Severity(severity), auto, strategy)


ISSUE_CODES: dict[str, IssueCodeDefinition] = {
    definition.code: definition
    for definition in (
        _d("LESSON_SCHEMA_REQUIRED_FIELD_MISSING", "L0", "critical", True, "deterministic_patch"),
        _d("LESSON_SESSION_COUNT_MISMATCH", "L1", "error", True, "deterministic_patch"),
        _d("LESSON_TIME_ALLOCATION_MISMATCH", "L1", "error", True, "deterministic_patch"),
        _d("LESSON_KP_NOT_COVERED", "L2", "error", False, "model_patch"),
        _d("LESSON_OBJECTIVE_NOT_MEASURABLE", "L4", "warning", False, "model_patch"),
        _d("LESSON_FACT_EVIDENCE_MISSING", "L3", "error", False, "model_patch"),
        _d("LESSON_EVIDENCE_COVERAGE_MISSING", "L3", "error", False, "model_patch"),
        _d("LESSON_REQUIRED_ACTIVITY_MISSING", "L2", "error", True, "deterministic_patch"),
        _d("LESSON_ACTIVITY_DUPLICATE", "L2", "warning", True, "deterministic_patch"),
        _d("LESSON_OBJECTIVE_PROGRESS_INVALID", "L4", "warning", False, "model_patch"),
        _d("LESSON_HOMEWORK_OBJECTIVE_MISMATCH", "L4", "warning", False, "model_patch"),
        _d("LESSON_FORBIDDEN_CLAIM", "L3", "error", False, "model_patch"),
        _d("EXAM_SCHEMA_FIELD_MISSING", "L0", "critical", True, "deterministic_patch"),
        _d("EXAM_QUESTION_COUNT_MISMATCH", "L1", "error", True, "deterministic_patch"),
        _d("EXAM_SCORE_MISMATCH", "L1", "error", True, "deterministic_patch"),
        _d("EXAM_ANSWER_NOT_IN_OPTIONS", "L1", "error", True, "deterministic_patch"),
        _d("EXAM_EXPLANATION_ANSWER_CONFLICT", "L2", "error", False, "model_patch"),
        _d("EXAM_MULTIPLE_CHOICE_CARDINALITY", "L1", "error", False, "model_patch"),
        _d("EXAM_OPTION_ASSESSMENT_MISMATCH", "L2", "error", False, "model_patch"),
        _d("EXAM_ANSWER_SET_INCONSISTENT", "L2", "error", False, "model_patch"),
        _d("EXAM_REQUIRED_STIMULUS_MISSING", "L1", "error", False, "model_patch"),
        _d("EXAM_OMITTED_STIMULUS_REFERENCE", "L1", "error", False, "model_patch"),
        _d("EXAM_SEMANTIC_DUPLICATE", "L2", "warning", False, "model_patch"),
        _d("EXAM_KP_COVERAGE_MISSING", "L2", "error", False, "model_patch"),
        _d("EXAM_DUPLICATE_QUESTION", "L2", "warning", False, "model_patch"),
        _d("PPT_SCHEMA_FIELD_MISSING", "L0", "critical", True, "deterministic_patch"),
        _d("PPT_SLIDE_COUNT_MISMATCH", "L1", "error", True, "deterministic_patch"),
        _d("PPT_INVALID_SLIDE_TYPE", "L1", "error", True, "deterministic_patch"),
        _d("PPT_CITATION_MISSING", "L1", "error", True, "deterministic_patch"),
        _d("PPT_SESSION_SOURCE_INVALID", "L2", "error", False, "model_patch"),
        _d("PPT_LAYOUT_MISSING", "L2", "error", False, "model_patch"),
        _d("PPT_REFERENCES_SLIDE_MISSING", "L1", "error", True, "deterministic_patch"),
        _d("PPT_CONTENT_OVERFLOW_RISK", "L4", "warning", False, "model_patch"),
        _d("GROUNDING_EVIDENCE_NOT_FOUND", "L3", "error", False, "model_patch"),
        _d("GROUNDING_SOURCE_TIER_INVALID", "L3", "critical", False, "model_patch"),
    )
}


def definition_for(code: str) -> IssueCodeDefinition:
    return ISSUE_CODES.get(
        code,
        IssueCodeDefinition(code, IssueLayer.L1, Severity.ERROR, False, "human_review"),
    )
