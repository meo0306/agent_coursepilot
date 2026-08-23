from __future__ import annotations

from coursepilot.domain.exam import ExamGlobalReport, ExamQuestion
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
