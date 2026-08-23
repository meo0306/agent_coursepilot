from __future__ import annotations

from typing import Any

from coursepilot.repair.models import PatchOperation, RepairPlan, RepairResult
from coursepilot.repair.patch import PatchApplyError, apply_patch
from coursepilot.validation.models import Severity, ValidationReport


class TargetedRepairService:
    """Apply a constrained candidate patch and require a caller-supplied revalidator."""

    def apply(
        self,
        document: dict[str, Any],
        report: ValidationReport,
        plan: RepairPlan,
        operations: list[PatchOperation],
        *,
        revalidate,
        preservation_paths: list[str] | None = None,
        output_artifact_version: int | str | None = None,
    ) -> RepairResult:
        try:
            candidate = apply_patch(
                document,
                operations,
                allowed_paths=plan.allowed_json_paths,
                forbidden_paths=plan.forbidden_json_paths,
            )
        except PatchApplyError as exc:
            return RepairResult(
                status="rejected",
                source_artifact_version=report.artifact_version,
                reason=str(exc),
            )

        before_paths = _leaf_values(document)
        after_paths = _leaf_values(candidate)
        changed_paths = {
            path
            for path in set(before_paths) | set(after_paths)
            if before_paths.get(path) != after_paths.get(path)
        }
        unauthorized = sorted(path for path in changed_paths if path not in plan.allowed_json_paths)
        preserved = all(
            before_paths.get(path) == after_paths.get(path) for path in (preservation_paths or [])
        )
        next_report = revalidate(candidate)
        original_ids = {issue.issue_id for issue in report.issues}
        regression_ids = [
            issue.issue_id
            for issue in next_report.issues
            if issue.severity in (Severity.CRITICAL, Severity.ERROR)
            and issue.issue_id not in original_ids
        ]
        resolved = [
            issue.issue_id
            for issue in report.issues
            if issue.issue_id not in {item.issue_id for item in next_report.issues}
        ]
        if unauthorized or not preserved or regression_ids:
            return RepairResult(
                status="rejected",
                source_artifact_version=report.artifact_version,
                applied_operations=operations,
                resolved_issue_ids=resolved,
                unauthorized_paths=unauthorized,
                regression_issue_ids=regression_ids,
                preserved=preserved,
                reason="post-repair preservation or regression check failed",
            )
        requires_review = any(
            issue.severity is Severity.CRITICAL
            for issue in report.issues
            if issue.issue_id in {operation.issue_id for operation in operations}
        )
        return RepairResult(
            status="needs_review" if requires_review else "accepted",
            source_artifact_version=report.artifact_version,
            output_artifact_version=output_artifact_version,
            applied_operations=operations,
            resolved_issue_ids=resolved,
            preserved=preserved,
        )


def _leaf_values(document: Any, path: str = "$") -> dict[str, Any]:
    if isinstance(document, dict):
        result: dict[str, Any] = {}
        for key, value in document.items():
            result.update(_leaf_values(value, f"{path}.{key}"))
        return result or {path: document}
    if isinstance(document, list):
        result = {}
        for index, value in enumerate(document):
            result.update(_leaf_values(value, f"{path}[{index}]"))
        return result or {path: document}
    return {path: document}
