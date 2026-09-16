from __future__ import annotations

from coursepilot.domain.exam import (
    ExamConflict,
    ExamConflictGraph,
    ExamGlobalReport,
    ExamQuestion,
)
from coursepilot.repair.models import RepairAction, RepairPlan


class ExamRepairPlanner:
    """Turn global Exam issues into bounded question-level repair actions."""

    def __init__(self, *, max_model_calls: int = 4) -> None:
        self.max_model_calls = max(0, max_model_calls)

    def plan(
        self,
        *,
        artifact_id: str,
        artifact_version: int | str,
        report: ExamGlobalReport,
        questions: list[ExamQuestion],
        excluded_question_ids: set[str] | None = None,
    ) -> RepairPlan:
        actions: list[RepairAction] = []
        excluded_question_ids = excluded_question_ids or set()
        question_index = {question.question_id: index for index, question in enumerate(questions)}
        issues_by_question: dict[str, list[str]] = {}

        for question_id, issue_codes in report.question_issue_codes.items():
            if question_id in question_index and question_id not in excluded_question_ids:
                issues_by_question.setdefault(question_id, []).extend(issue_codes)

        # Preserve the first Blueprint-ordered question and regenerate only the
        # later duplicate. Regenerating both sides wastes calls and can create a
        # new duplicate pair without retaining either accepted item.
        for left_id, right_id in report.duplicate_pairs:
            left_index = question_index.get(left_id)
            right_index = question_index.get(right_id)
            if left_index is None or right_index is None:
                continue
            preferred_id = right_id if right_index >= left_index else left_id
            alternate_id = left_id if preferred_id == right_id else right_id
            target_id = (
                alternate_id
                if preferred_id in excluded_question_ids
                and alternate_id not in excluded_question_ids
                else preferred_id
            )
            if target_id in excluded_question_ids:
                continue
            issues_by_question.setdefault(target_id, []).append(
                f"DUPLICATE_QUESTIONS:{left_id}:{right_id}"
            )

        # Use typed IDs instead of parsing colon-delimited error strings: P15
        # question IDs themselves contain colons.
        for question_id in report.answer_leakage_question_ids:
            if question_id in question_index:
                issues_by_question.setdefault(question_id, []).append(
                    f"ANSWER_LEAKAGE:{question_id}"
                )
        for question_id, source_id in report.cross_answer_leakage_pairs:
            if question_id in question_index:
                issues_by_question.setdefault(question_id, []).append(
                    f"CROSS_ANSWER_LEAKAGE:{question_id}:{source_id}"
                )

        for question_id in sorted(issues_by_question, key=lambda item: question_index[item]):
            index = question_index[question_id]
            actions.append(
                RepairAction(
                    issue_ids=sorted(set(issues_by_question[question_id])),
                    strategy="regenerate_component",
                    target_scope=f"$.questions[{index}]",
                    allowed_paths=[
                        f"$.questions[{index}].stimulus",
                        f"$.questions[{index}].stem",
                        f"$.questions[{index}].options",
                        f"$.questions[{index}].option_assessments",
                        f"$.questions[{index}].answer",
                        f"$.questions[{index}].explanation",
                    ],
                    validator_layers=["batch", "global"],
                    model_profile="generator_main",
                )
            )
        return RepairPlan(
            artifact_id=artifact_id,
            artifact_version=artifact_version,
            actions=actions[: self.max_model_calls],
            max_model_calls=min(self.max_model_calls, len(actions)),
            allowed_json_paths=sorted(
                {path for action in actions for path in action.allowed_paths}
            ),
            forbidden_json_paths=["$", "$.blueprint", "$.questions"],
            requires_full_regeneration=False,
        )


def build_exam_conflict_graph(
    report: ExamGlobalReport, questions: list[ExamQuestion]
) -> ExamConflictGraph:
    """Select the later/conflicting question once for whole-question regeneration."""

    order = {question.question_id: index for index, question in enumerate(questions)}
    conflicts: list[ExamConflict] = []
    seen: set[tuple[str, str, str | None]] = set()

    def add(
        kind: str,
        target_id: str,
        issue_codes: list[str],
        source_id: str | None = None,
    ) -> None:
        if target_id not in order:
            return
        key = (kind, target_id, source_id)
        if key in seen:
            return
        seen.add(key)
        conflicts.append(
            ExamConflict(
                kind=kind,  # type: ignore[arg-type]
                target_question_id=target_id,
                source_question_id=source_id,
                issue_codes=sorted(set(issue_codes)),
            )
        )

    for left_id, right_id in report.duplicate_pairs:
        if left_id not in order or right_id not in order:
            continue
        target_id, source_id = (
            (right_id, left_id) if order[right_id] >= order[left_id] else (left_id, right_id)
        )
        add(
            "semantic_duplicate",
            target_id,
            [f"DUPLICATE_QUESTIONS:{left_id}:{right_id}"],
            source_id,
        )
    for target_id in report.answer_leakage_question_ids:
        add("answer_leakage", target_id, [f"ANSWER_LEAKAGE:{target_id}"])
    for target_id, source_id in report.cross_answer_leakage_pairs:
        add(
            "answer_leakage",
            target_id,
            [f"CROSS_ANSWER_LEAKAGE:{target_id}:{source_id}"],
            source_id,
        )
    structural = {
        "EXAM_MULTIPLE_CHOICE_CARDINALITY": "choice_contract",
        "EXAM_ANSWER_NOT_IN_OPTIONS": "choice_contract",
        "EXAM_OPTION_ASSESSMENT_MISMATCH": "answer_set",
        "EXAM_ANSWER_SET_INCONSISTENT": "answer_set",
        "EXAM_REQUIRED_STIMULUS_MISSING": "stimulus_contract",
        "EXAM_OMITTED_STIMULUS_REFERENCE": "stimulus_contract",
    }
    for question_id, issue_codes in report.question_issue_codes.items():
        by_kind: dict[str, list[str]] = {}
        for issue_code in issue_codes:
            kind = structural.get(issue_code)
            if kind:
                by_kind.setdefault(kind, []).append(issue_code)
        for kind, codes in by_kind.items():
            add(kind, question_id, codes)

    return ExamConflictGraph(
        conflicts=sorted(
            conflicts,
            key=lambda item: (
                order[item.target_question_id],
                item.kind,
                item.source_question_id or "",
            ),
        )
    )
