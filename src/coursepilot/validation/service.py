from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, ValidationError

from coursepilot.validation.codes import definition_for
from coursepilot.validation.models import IssueScope, Severity, ValidationIssue, ValidationReport


@dataclass
class ValidationContext:
    artifact_id: str = "artifact"
    artifact_version: int | str = 1
    course_id: str | None = None
    expected_sessions: int | None = None
    expected_duration: int | None = None
    expected_question_counts: dict[str, int] = field(default_factory=dict)
    expected_total_score: int | None = None
    expected_slide_count: int | None = None
    valid_session_indices: set[int] = field(default_factory=set)
    required_knowledge_points: set[str] = field(default_factory=set)
    required_evidence_ids: set[str] = field(default_factory=set)
    grounding_resolver: Callable[[str], dict[str, Any] | None] | None = None


def _path_from_loc(loc: tuple[object, ...]) -> str:
    path = "$"
    for part in loc:
        path += f"[{part}]" if isinstance(part, int) else f".{part}"
    return path


def _issue_id(code: str, scope: IssueScope) -> str:
    return f"{code}:{scope.artifact_type}:{scope.item_id or '-'}:{scope.json_path}"


def _question_similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, left, right).ratio()


class ValidatorService:
    """Deterministic layered validator; model providers are never called here."""

    def __init__(self, profile: str = "coursepilot_validator_v1") -> None:
        self.profile = profile

    def validate_raw(
        self,
        artifact_type: str,
        payload: dict[str, Any],
        schema: type[BaseModel],
        context: ValidationContext | None = None,
    ) -> ValidationReport:
        ctx = context or ValidationContext()
        report = ValidationReport(
            artifact_id=ctx.artifact_id,
            artifact_version=ctx.artifact_version,
            artifact_type=artifact_type,  # type: ignore[arg-type]
            validator_profile=self.profile,
        )
        try:
            typed = schema.model_validate(payload)
        except ValidationError as exc:
            for error in exc.errors():
                scope = IssueScope(
                    artifact_type=artifact_type, json_path=_path_from_loc(tuple(error["loc"]))
                )  # type: ignore[arg-type]
                schema_code = {
                    "lesson": "LESSON_SCHEMA_REQUIRED_FIELD_MISSING",
                    "exam": "EXAM_SCHEMA_FIELD_MISSING",
                    "ppt": "PPT_SCHEMA_FIELD_MISSING",
                }[artifact_type]
                report.issues.append(
                    self._issue(
                        schema_code,
                        scope,
                        actual=error.get("input"),
                        message=error["msg"],
                    )
                )
            return report.finalize()
        self._validate_typed(artifact_type, typed.model_dump(mode="python"), report, ctx)
        return report.finalize()

    def validate_typed(
        self, artifact_type: str, payload: dict[str, Any], context: ValidationContext | None = None
    ) -> ValidationReport:
        ctx = context or ValidationContext()
        report = ValidationReport(
            artifact_id=ctx.artifact_id,
            artifact_version=ctx.artifact_version,
            artifact_type=artifact_type,  # type: ignore[arg-type]
            validator_profile=self.profile,
        )
        self._validate_typed(artifact_type, payload, report, ctx)
        return report.finalize()

    def _validate_typed(
        self,
        artifact_type: str,
        payload: dict[str, Any],
        report: ValidationReport,
        ctx: ValidationContext,
    ) -> None:
        if artifact_type == "lesson":
            self._lesson(payload, report, ctx)
        elif artifact_type == "exam":
            self._exam(payload, report, ctx)
        elif artifact_type == "ppt":
            self._ppt(payload, report, ctx)
        else:
            raise ValueError(f"unsupported artifact_type: {artifact_type}")

    def _issue(
        self,
        code: str,
        scope: IssueScope,
        *,
        actual: Any = None,
        expected: Any = None,
        message: str = "",
        evidence_ids: list[str] | None = None,
        severity_override: Severity | None = None,
    ) -> ValidationIssue:
        definition = definition_for(code)
        return ValidationIssue(
            issue_id=_issue_id(code, scope),
            code=code,
            severity=severity_override or definition.severity,
            layer=definition.layer,
            scope=scope,
            auto_repairable=definition.auto_repairable,
            repair_strategy=definition.strategy,
            actual=actual,
            expected=expected,
            message=message,
            evidence_ids=evidence_ids or [],
        )

    def _lesson(
        self, payload: dict[str, Any], report: ValidationReport, ctx: ValidationContext
    ) -> None:
        plan = payload.get("session_plan") or []
        sessions = payload.get("sessions") or []
        if ctx.expected_sessions is not None and len(plan) != ctx.expected_sessions:
            report.issues.append(
                self._issue(
                    "LESSON_SESSION_COUNT_MISMATCH",
                    IssueScope(artifact_type="lesson", json_path="$.total_sessions"),
                    actual=len(plan),
                    expected=ctx.expected_sessions,
                )
            )
        if ctx.expected_duration is not None:
            for index, item in enumerate(plan):
                if not item.get("teaching_focus"):
                    report.issues.append(
                        self._issue(
                            "LESSON_SCHEMA_REQUIRED_FIELD_MISSING",
                            IssueScope(
                                artifact_type="lesson",
                                item_id=str(item.get("session_index", index + 1)),
                                json_path=f"$.session_plan[{index}].teaching_focus",
                            ),
                        )
                    )
                minutes = sum(int(x.get("minutes", 0)) for x in item.get("time_allocation", []))
                if minutes != int(item.get("duration", 0)):
                    report.issues.append(
                        self._issue(
                            "LESSON_TIME_ALLOCATION_MISMATCH",
                            IssueScope(
                                artifact_type="lesson",
                                item_id=str(item.get("session_index", index + 1)),
                                json_path=f"$.session_plan[{index}].time_allocation[0].minutes",
                            ),
                            actual=minutes,
                            expected=item.get("duration"),
                        )
                    )
        for index, session in enumerate(sessions):
            for objective_index, objective in enumerate(session.get("teaching_objectives", [])):
                if len(str(objective).strip()) <= 6:
                    report.issues.append(
                        self._issue(
                            "LESSON_OBJECTIVE_NOT_MEASURABLE",
                            IssueScope(
                                artifact_type="lesson",
                                item_id=str(session.get("session_index", index + 1)),
                                json_path=f"$.sessions[{index}].teaching_objectives[{objective_index}]",
                            ),
                        )
                    )
            self._grounding(
                session.get("references", []),
                "lesson",
                f"$.sessions[{index}].references",
                report,
                ctx,
            )
        if ctx.required_knowledge_points:
            covered = {str(point) for item in plan for point in item.get("knowledge_points", [])}
            missing = sorted(ctx.required_knowledge_points - covered)
            if missing:
                report.issues.append(
                    self._issue(
                        "LESSON_KP_NOT_COVERED",
                        IssueScope(
                            artifact_type="lesson",
                            item_id="1",
                            json_path="$.sessions[0].key_points",
                        ),
                        actual=missing,
                        expected=sorted(ctx.required_knowledge_points),
                    )
                )
            for index, session in enumerate(sessions):
                if not session.get("key_points"):
                    report.issues.append(
                        self._issue(
                            "LESSON_KP_NOT_COVERED",
                            IssueScope(
                                artifact_type="lesson",
                                item_id=str(index + 1),
                                json_path=f"$.sessions[{index}].key_points",
                            ),
                            actual=session.get("key_points", []),
                            expected=sorted(ctx.required_knowledge_points),
                        )
                    )
                    break

    def _exam(
        self, payload: dict[str, Any], report: ValidationReport, ctx: ValidationContext
    ) -> None:
        groups = payload.get("question_groups") or []
        if "total_score" not in payload:
            report.issues.append(
                self._issue(
                    "EXAM_SCHEMA_FIELD_MISSING",
                    IssueScope(artifact_type="exam", json_path="$.blueprint.total_score"),
                    expected="total_score",
                )
            )
        actual_counts = {
            str(group.get("question_type")): int(group.get("count", 0)) for group in groups
        }
        if ctx.expected_question_counts and actual_counts != ctx.expected_question_counts:
            report.issues.append(
                self._issue(
                    "EXAM_QUESTION_COUNT_MISMATCH",
                    IssueScope(
                        artifact_type="exam", json_path="$.blueprint.question_counts.single_choice"
                    ),
                    actual=actual_counts,
                    expected=ctx.expected_question_counts,
                )
            )
        total = sum(
            int(
                group.get(
                    "total_score", int(group.get("count", 0)) * int(group.get("score_each", 0))
                )
            )
            for group in groups
        )
        if (
            ctx.expected_total_score is not None
            and "total_score" in payload
            and total != ctx.expected_total_score
        ):
            report.issues.append(
                self._issue(
                    "EXAM_SCORE_MISMATCH",
                    IssueScope(artifact_type="exam", json_path="$.blueprint.total_score"),
                    actual=total,
                    expected=ctx.expected_total_score,
                )
            )
        questions = payload.get("questions") or []
        seen: dict[str, int] = {}
        for index, question in enumerate(questions):
            text = str(question.get("question_text", question.get("stem", ""))).strip().lower()
            similar_previous = next(
                (previous for previous in seen if _question_similarity(text, previous) >= 0.7),
                None,
            )
            if text and (text in seen or similar_previous is not None):
                report.issues.append(
                    self._issue(
                        "EXAM_DUPLICATE_QUESTION",
                        IssueScope(
                            artifact_type="exam",
                            item_id=str(index),
                            json_path=f"$.questions[{index}].stem",
                        ),
                        actual=seen.get(text, seen.get(similar_previous or text)),
                        expected="unique",
                    )
                )
            seen[text] = index
            options = question.get("options") or []
            answer = question.get("correct_answer")
            if (
                question.get("question_type") in {"single_choice", "multiple_choice"}
                and not options
            ):
                report.issues.append(
                    self._issue(
                        "EXAM_ANSWER_NOT_IN_OPTIONS",
                        IssueScope(
                            artifact_type="exam",
                            item_id=str(question.get("question_id", index)),
                            json_path=f"$.questions[{index}].options",
                        ),
                        actual=options,
                        expected="non-empty options",
                    )
                )
            if isinstance(answer, str) and options and answer not in options:
                report.issues.append(
                    self._issue(
                        "EXAM_ANSWER_NOT_IN_OPTIONS",
                        IssueScope(
                            artifact_type="exam",
                            item_id=str(question.get("question_id", index)),
                            json_path=f"$.questions[{index}].correct_answer",
                        ),
                        actual=answer,
                        expected=options,
                    )
                )
            if ctx.required_knowledge_points:
                points = set(question.get("knowledge_point_ids", [])) | set(
                    question.get("knowledge_points", [])
                )
                if not points & ctx.required_knowledge_points:
                    report.issues.append(
                        self._issue(
                            "EXAM_KP_COVERAGE_MISSING",
                            IssueScope(
                                artifact_type="exam",
                                item_id=str(question.get("question_id", index)),
                                json_path=f"$.questions[{index}].knowledge_point_ids",
                            ),
                            actual=sorted(points),
                            expected=sorted(ctx.required_knowledge_points),
                        )
                    )
            if not question.get("explanation"):
                report.issues.append(
                    self._issue(
                        "EXAM_EXPLANATION_ANSWER_CONFLICT",
                        IssueScope(
                            artifact_type="exam",
                            item_id=str(question.get("question_id", index)),
                            json_path=f"$.questions[{index}].explanation",
                        ),
                        actual=None,
                        expected="non-empty explanation",
                    )
                )
            elif "其他选项" in str(question.get("explanation")):
                report.issues.append(
                    self._issue(
                        "EXAM_EXPLANATION_ANSWER_CONFLICT",
                        IssueScope(
                            artifact_type="exam",
                            item_id=str(question.get("question_id", index)),
                            json_path=f"$.questions[{index}].explanation",
                        ),
                        actual=question.get("explanation"),
                        expected="explanation supports correct answer",
                    )
                )
            references = question.get("references", []) or [
                {"evidence_id": item} for item in question.get("evidence_ids", [])
            ]
            self._grounding(
                references,
                "exam",
                f"$.questions[{index}].evidence_ids"
                if question.get("evidence_ids")
                else f"$.questions[{index}].references",
                report,
                ctx,
                scalar_list=bool(question.get("evidence_ids")),
            )

    def _ppt(
        self, payload: dict[str, Any], report: ValidationReport, ctx: ValidationContext
    ) -> None:
        slides = payload.get("slides") or []
        if "style_template" not in payload:
            report.issues.append(
                self._issue(
                    "PPT_SCHEMA_FIELD_MISSING",
                    IssueScope(artifact_type="ppt", json_path="$.style_template"),
                    expected="style_template",
                )
            )
        if ctx.expected_slide_count is not None and len(slides) != ctx.expected_slide_count:
            report.issues.append(
                self._issue(
                    "PPT_SLIDE_COUNT_MISMATCH",
                    IssueScope(artifact_type="ppt", json_path="$.slide_count"),
                    actual=len(slides),
                    expected=ctx.expected_slide_count,
                )
            )
        allowed_types = {"title", "objectives", "content", "activity", "summary", "references"}
        for index, slide in enumerate(slides):
            scope = IssueScope(
                artifact_type="ppt",
                item_id=str(slide.get("slide_index", index + 1)),
                json_path=f"$.slides[{index}]",
            )
            if slide.get("slide_type") not in allowed_types:
                report.issues.append(
                    self._issue(
                        "PPT_INVALID_SLIDE_TYPE",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].slide_type",
                        ),
                        actual=slide.get("slide_type"),
                        expected=sorted(allowed_types),
                    )
                )
            if not slide.get("bullet_points") and not slide.get("speaker_notes"):
                report.issues.append(
                    self._issue(
                        "PPT_CONTENT_OVERFLOW_RISK", scope, actual="empty", expected="non-empty"
                    )
                )
            if len(slide.get("bullet_points") or []) > 10:
                report.issues.append(
                    self._issue(
                        "PPT_CONTENT_OVERFLOW_RISK",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].bullet_points",
                        ),
                        actual=len(slide.get("bullet_points") or []),
                        expected="<=10",
                    )
                )
            if slide.get("slide_type") == "references" and not slide.get("references"):
                report.issues.append(
                    self._issue(
                        "PPT_REFERENCES_SLIDE_MISSING",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].references",
                        ),
                        actual="no references",
                        expected="at least one reference",
                    )
                )
            if slide.get("layout") is None:
                report.issues.append(
                    self._issue(
                        "PPT_LAYOUT_MISSING",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].layout",
                        ),
                        expected="layout",
                    )
                )
            if (
                slide.get("slide_type") in {"objectives", "content", "activity"}
                and slide.get("source_session_index") is None
            ):
                report.issues.append(
                    self._issue(
                        "PPT_SESSION_SOURCE_INVALID",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].source_session_index",
                        ),
                        expected="source_session_index",
                    )
                )
            elif (
                ctx.valid_session_indices
                and slide.get("source_session_index") not in ctx.valid_session_indices
            ):
                report.issues.append(
                    self._issue(
                        "PPT_SESSION_SOURCE_INVALID",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].source_session_index",
                        ),
                        actual=slide.get("source_session_index"),
                        expected=sorted(ctx.valid_session_indices),
                    )
                )
            self._grounding(
                slide.get("references", []), "ppt", f"$.slides[{index}].references", report, ctx
            )
            if slide.get("slide_type") not in {"title", "references"} and not slide.get(
                "references"
            ):
                report.issues.append(
                    self._issue(
                        "PPT_CITATION_MISSING",
                        IssueScope(
                            artifact_type="ppt",
                            item_id=scope.item_id,
                            json_path=f"$.slides[{index}].references",
                        ),
                        expected="at least one reference",
                    )
                )

    def _grounding(
        self,
        references: list[dict[str, Any]],
        artifact_type: str,
        path: str,
        report: ValidationReport,
        ctx: ValidationContext,
        scalar_list: bool = False,
    ) -> None:
        for index, reference in enumerate(references):
            evidence_id = reference.get("evidence_id") or reference.get("chunk_id")
            if not evidence_id:
                report.issues.append(
                    self._issue(
                        "GROUNDING_EVIDENCE_NOT_FOUND",
                        IssueScope(
                            artifact_type=artifact_type,
                            json_path=path if scalar_list else f"{path}[{index}].evidence_id",
                        ),
                        actual=None,
                        expected="evidence_id",
                        severity_override=Severity.CRITICAL if artifact_type == "exam" else None,
                    )
                )
                continue
            if ctx.required_evidence_ids and evidence_id not in ctx.required_evidence_ids:
                if any(item.code == "GROUNDING_EVIDENCE_NOT_FOUND" for item in report.issues):
                    continue
                report.issues.append(
                    self._issue(
                        "GROUNDING_EVIDENCE_NOT_FOUND",
                        IssueScope(
                            artifact_type=artifact_type,
                            json_path=path if scalar_list else f"{path}[{index}].evidence_id",
                        ),
                        actual=evidence_id,
                        expected=sorted(ctx.required_evidence_ids),
                        evidence_ids=[str(evidence_id)],
                        severity_override=Severity.CRITICAL if artifact_type == "exam" else None,
                    )
                )
            if ctx.course_id is not None and reference.get("course_id") not in (
                None,
                ctx.course_id,
            ):
                if any(item.code == "GROUNDING_SOURCE_TIER_INVALID" for item in report.issues):
                    continue
                report.issues.append(
                    self._issue(
                        "GROUNDING_SOURCE_TIER_INVALID",
                        IssueScope(
                            artifact_type=artifact_type,
                            json_path=f"{path}[{index}].course_id",
                        ),
                        actual=reference.get("course_id"),
                        expected=ctx.course_id,
                        evidence_ids=[str(evidence_id)],
                    )
                )
            if ctx.grounding_resolver is not None:
                resolved = ctx.grounding_resolver(str(evidence_id))
                if resolved is None:
                    report.issues.append(
                        self._issue(
                            "GROUNDING_EVIDENCE_NOT_FOUND",
                            IssueScope(
                                artifact_type=artifact_type,
                                json_path=f"{path}[{index}].evidence_id",
                            ),
                            actual=evidence_id,
                            expected="resolvable evidence",
                            evidence_ids=[str(evidence_id)],
                        )
                    )
                elif ctx.course_id is not None and resolved.get("course_id") not in (
                    None,
                    ctx.course_id,
                ):
                    report.issues.append(
                        self._issue(
                            "GROUNDING_SOURCE_TIER_INVALID",
                            IssueScope(artifact_type=artifact_type, json_path=f"{path}[{index}]"),
                            actual=resolved.get("course_id"),
                            expected=ctx.course_id,
                            evidence_ids=[str(evidence_id)],
                        )
                    )
