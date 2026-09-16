from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from coursepilot.validation.models import ValidationIssue, ValidationReport


@dataclass(frozen=True)
class P13Metrics:
    expected_issues: int
    detected_issues: int
    code_match: int
    scope_match: int
    severity_match: int
    false_positives: int
    unauthorized_modifications: int = 0
    regressions: int = 0

    def as_dict(self) -> dict[str, int | float]:
        denominator = max(self.expected_issues, 1)
        return {
            "expected_issues": self.expected_issues,
            "detected_issues": self.detected_issues,
            "detection_recall": self.detected_issues / denominator,
            "code_match": self.code_match,
            "scope_match": self.scope_match,
            "severity_match": self.severity_match,
            "false_positives": self.false_positives,
            "unauthorized_modifications": self.unauthorized_modifications,
            "regressions": self.regressions,
        }


def compare_issues(expected: list[ValidationIssue], actual: list[ValidationIssue]) -> P13Metrics:
    expected_keys = {(issue.code, issue.scope.json_path) for issue in expected}
    actual_keys = {(issue.code, issue.scope.json_path) for issue in actual}
    code_match = sum(issue.code in {item.code for item in expected} for issue in actual)
    scope_match = sum((issue.code, issue.scope.json_path) in expected_keys for issue in actual)
    severity_by_key = {(issue.code, issue.scope.json_path): issue.severity for issue in expected}
    severity_match = sum(
        severity_by_key.get((issue.code, issue.scope.json_path)) == issue.severity
        for issue in actual
    )
    return P13Metrics(
        expected_issues=len(expected),
        detected_issues=len(expected_keys & actual_keys),
        code_match=code_match,
        scope_match=scope_match,
        severity_match=severity_match,
        false_positives=len(actual_keys - expected_keys),
    )


def summarize_reports(
    reports: list[tuple[list[ValidationIssue], ValidationReport]],
) -> dict[str, int | float]:
    totals: Counter[str] = Counter()
    for expected, report in reports:
        metrics = compare_issues(expected, report.issues)
        for key, value in metrics.as_dict().items():
            if isinstance(value, int):
                totals[key] += value
    expected_total = max(totals["expected_issues"], 1)
    return {
        **dict(totals),
        "detection_recall": totals["detected_issues"] / expected_total,
        "code_precision": totals["code_match"] / max(totals["detected_issues"], 1),
        "scope_precision": totals["scope_match"] / max(totals["detected_issues"], 1),
        "severity_accuracy": totals["severity_match"] / max(totals["detected_issues"], 1),
    }
