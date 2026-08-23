from __future__ import annotations

from typing import Any

from coursepilot.validation.models import ValidationReport


def legacy_error_messages(report: ValidationReport) -> list[str]:
    return [f"{issue.code} at {issue.scope.json_path}" for issue in report.issues]


def report_to_legacy_flags(
    report: ValidationReport, flags: dict[str, tuple[str, ...]]
) -> dict[str, Any]:
    codes = report.issue_codes()
    result: dict[str, Any] = {
        name: not any(code in codes for code in related) for name, related in flags.items()
    }
    result["errors"] = legacy_error_messages(report)
    return result
