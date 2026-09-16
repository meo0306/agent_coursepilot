from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import Field, JsonValue, model_validator

from coursepilot.evals.formal_schemas import (
    RecoveryExpectation,
    ValidationIssue,
)
from evaluation.contracts import MetricResult, StrictModel

_ISSUE_WEIGHTS = {
    "info": 0,
    "warning": 1,
    "error": 3,
    "critical": 5,
}


class RepairObservation(StrictModel):
    artifact_before: JsonValue
    artifact_after: JsonValue
    allowed_paths: list[str] = Field(min_length=1)
    original_correct_paths: list[str] = Field(default_factory=list)
    expected_resolved_issue_codes: list[str] = Field(default_factory=list)
    issues_before: list[ValidationIssue] = Field(default_factory=list)
    issues_by_round: list[list[ValidationIssue]] = Field(min_length=1)
    max_repair_rounds: int = Field(ge=1)


class RecoveryObservation(StrictModel):
    interrupt_reached: bool
    resume_succeeds: bool
    completed_nodes_reused: int = Field(ge=0)
    edited_fields_preserved: int = Field(ge=0)
    duplicate_side_effects: int = Field(ge=0)
    replayed_side_effect_attempts: int = Field(ge=0)
    approval_scope_correct: bool
    stale_version_detected: bool | None = None

    @model_validator(mode="after")
    def validate_duplicate_denominator(self) -> RecoveryObservation:
        if self.duplicate_side_effects > self.replayed_side_effect_attempts:
            raise ValueError("duplicate_side_effects cannot exceed replayed_side_effect_attempts")
        return self


def validation_issue_metrics(
    gold: list[ValidationIssue],
    predicted: list[ValidationIssue],
) -> dict[str, MetricResult]:
    exact_pairs = _greedy_pairs(gold, predicted, require_code=True, require_scope=True)
    code_pairs = _greedy_pairs(gold, predicted, require_code=True, require_scope=False)
    scope_pairs = _greedy_pairs(gold, predicted, require_code=False, require_scope=True)

    severity_matches = sum(
        gold[gold_index].severity == predicted[predicted_index].severity
        for gold_index, predicted_index in exact_pairs
    )
    repairable_matches = sum(
        gold[gold_index].auto_repairable == predicted[predicted_index].auto_repairable
        for gold_index, predicted_index in exact_pairs
    )
    severe_false_positive = int(
        not gold and any(issue.severity in {"error", "critical"} for issue in predicted)
    )

    return {
        "issue_detection_precision": MetricResult.ratio(
            "issue_detection_precision",
            len(exact_pairs),
            len(predicted),
        ),
        "issue_detection_recall": MetricResult.ratio(
            "issue_detection_recall",
            len(exact_pairs),
            len(gold),
        ),
        "issue_code_accuracy": MetricResult.ratio(
            "issue_code_accuracy",
            len(exact_pairs),
            len(scope_pairs),
        ),
        "scope_localization_accuracy": MetricResult.ratio(
            "scope_localization_accuracy",
            len(exact_pairs),
            len(code_pairs),
        ),
        "severity_accuracy": MetricResult.ratio(
            "severity_accuracy",
            severity_matches,
            len(exact_pairs),
        ),
        "auto_repairable_accuracy": MetricResult.ratio(
            "auto_repairable_accuracy",
            repairable_matches,
            len(exact_pairs),
        ),
        "clean_artifact_false_positive_rate": MetricResult.ratio(
            "clean_artifact_false_positive_rate",
            severe_false_positive,
            int(not gold),
        ),
    }


def repair_metrics(observation: RepairObservation) -> dict[str, MetricResult]:
    changed_paths = json_leaf_changes(
        observation.artifact_before,
        observation.artifact_after,
    )
    targeted_paths = {
        path for path in changed_paths if _path_in_allowed_scope(path, observation.allowed_paths)
    }
    expected_codes = set(observation.expected_resolved_issue_codes)
    first_round_codes = {issue.code for issue in observation.issues_by_round[0]}
    final_issues = observation.issues_by_round[
        min(len(observation.issues_by_round), observation.max_repair_rounds) - 1
    ]
    final_codes = {issue.code for issue in final_issues}
    first_success = bool(expected_codes) and expected_codes.isdisjoint(first_round_codes)
    final_success = bool(expected_codes) and expected_codes.isdisjoint(final_codes)

    before_severe = {
        (issue.code, issue.scope.item_id, issue.scope.json_path)
        for issue in observation.issues_before
        if issue.severity in {"error", "critical"}
    }
    new_severe = {
        (issue.code, issue.scope.item_id, issue.scope.json_path)
        for issue in final_issues
        if issue.severity in {"error", "critical"}
    } - before_severe

    before_values = _flatten_json(observation.artifact_before)
    after_values = _flatten_json(observation.artifact_after)
    preserved = sum(
        path in before_values and path in after_values and before_values[path] == after_values[path]
        for path in observation.original_correct_paths
    )
    issue_reduction = _issue_score(observation.issues_before) - _issue_score(final_issues)

    return {
        "repair_attempt_success_rate": MetricResult.ratio(
            "repair_attempt_success_rate",
            int(first_success),
            int(bool(expected_codes)),
        ),
        "final_repair_success_rate": MetricResult.ratio(
            "final_repair_success_rate",
            int(final_success),
            int(bool(expected_codes)),
        ),
        "targeted_modification_rate": MetricResult.ratio(
            "targeted_modification_rate",
            len(targeted_paths),
            len(changed_paths),
        ),
        "unauthorized_modification_rate": MetricResult.ratio(
            "unauthorized_modification_rate",
            len(changed_paths - targeted_paths),
            len(changed_paths),
        ),
        "regression_rate": MetricResult.ratio(
            "regression_rate",
            int(bool(new_severe)),
            1,
        ),
        "preservation_rate": MetricResult.ratio(
            "preservation_rate",
            preserved,
            len(observation.original_correct_paths),
        ),
        "issue_reduction": MetricResult(
            name="issue_reduction",
            value=float(issue_reduction),
            numerator=float(issue_reduction),
            denominator=1,
            applicable=True,
        ),
    }


def recovery_metrics(
    expectations: Sequence[RecoveryExpectation],
    observations: Sequence[RecoveryObservation],
) -> dict[str, MetricResult]:
    if len(expectations) != len(observations):
        raise ValueError("expectations and observations must have equal length")

    interrupt_denominator = sum(item.interrupt_reached for item in expectations)
    interrupt_numerator = sum(
        expected.interrupt_reached and observed.interrupt_reached
        for expected, observed in zip(expectations, observations, strict=True)
    )
    resume_denominator = sum(item.resume_succeeds for item in expectations)
    resume_numerator = sum(
        expected.resume_succeeds and observed.resume_succeeds
        for expected, observed in zip(expectations, observations, strict=True)
    )
    completed_nodes = sum(expected.completed_nodes_before_resume for expected in expectations)
    reused_nodes = sum(
        min(observed.completed_nodes_reused, expected.completed_nodes_before_resume)
        for expected, observed in zip(expectations, observations, strict=True)
    )
    edited_fields = sum(item.edited_fields_total for item in expectations)
    preserved_fields = sum(
        min(observed.edited_fields_preserved, expected.edited_fields_total)
        for expected, observed in zip(expectations, observations, strict=True)
    )
    stale_denominator = sum(expected.stale_version_detected is True for expected in expectations)
    stale_numerator = sum(
        expected.stale_version_detected is True and observed.stale_version_detected is True
        for expected, observed in zip(expectations, observations, strict=True)
    )
    replayed_side_effect_attempts = sum(item.replayed_side_effect_attempts for item in observations)

    return {
        "interrupt_reach_rate": MetricResult.ratio(
            "interrupt_reach_rate",
            interrupt_numerator,
            interrupt_denominator,
        ),
        "resume_success_rate": MetricResult.ratio(
            "resume_success_rate",
            resume_numerator,
            resume_denominator,
        ),
        "completed_node_reuse_rate": MetricResult.ratio(
            "completed_node_reuse_rate",
            reused_nodes,
            completed_nodes,
        ),
        "human_edit_preservation_rate": MetricResult.ratio(
            "human_edit_preservation_rate",
            preserved_fields,
            edited_fields,
        ),
        "duplicate_side_effect_rate": MetricResult.ratio(
            "duplicate_side_effect_rate",
            sum(item.duplicate_side_effects for item in observations),
            replayed_side_effect_attempts,
        ),
        "approval_scope_accuracy": MetricResult.ratio(
            "approval_scope_accuracy",
            sum(item.approval_scope_correct for item in observations),
            len(observations),
        ),
        "stale_version_detection_rate": MetricResult.ratio(
            "stale_version_detection_rate",
            stale_numerator,
            stale_denominator,
        ),
    }


def json_leaf_changes(before: JsonValue, after: JsonValue) -> set[str]:
    before_values = _flatten_json(before)
    after_values = _flatten_json(after)
    return {
        path
        for path in before_values.keys() | after_values.keys()
        if before_values.get(path) != after_values.get(path)
    }


def _greedy_pairs(
    gold: list[ValidationIssue],
    predicted: list[ValidationIssue],
    *,
    require_code: bool,
    require_scope: bool,
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    used_predictions: set[int] = set()
    for gold_index, gold_issue in enumerate(gold):
        for predicted_index, predicted_issue in enumerate(predicted):
            if predicted_index in used_predictions:
                continue
            if require_code and predicted_issue.code != gold_issue.code:
                continue
            if require_scope and not _scope_matches(predicted_issue, gold_issue):
                continue
            pairs.append((gold_index, predicted_index))
            used_predictions.add(predicted_index)
            break
    return pairs


def _scope_matches(predicted: ValidationIssue, gold: ValidationIssue) -> bool:
    if predicted.scope.artifact_type != gold.scope.artifact_type:
        return False
    if predicted.scope.item_id != gold.scope.item_id:
        return False
    return (
        predicted.scope.json_path == gold.scope.json_path
        or predicted.scope.json_path in gold.allowed_parent_paths
    )


def _path_in_allowed_scope(path: str, allowed_paths: list[str]) -> bool:
    return any(
        path == allowed or path.startswith(f"{allowed}.") or path.startswith(f"{allowed}[")
        for allowed in allowed_paths
    )


def _flatten_json(value: JsonValue, path: str = "$") -> dict[str, JsonValue]:
    if isinstance(value, Mapping):
        flattened: dict[str, JsonValue] = {}
        for key, child in value.items():
            flattened.update(_flatten_json(child, f"{path}.{key}"))
        return flattened or {path: {}}
    if isinstance(value, list):
        flattened = {}
        for index, child in enumerate(value):
            flattened.update(_flatten_json(child, f"{path}[{index}]"))
        return flattened or {path: []}
    return {path: value}


def _issue_score(issues: list[ValidationIssue]) -> int:
    return sum(_ISSUE_WEIGHTS[issue.severity] for issue in issues)
