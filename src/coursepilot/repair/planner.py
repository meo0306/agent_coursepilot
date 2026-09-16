from __future__ import annotations

from coursepilot.repair.models import RepairAction, RepairPlan
from coursepilot.validation.models import IssueLayer, Severity, ValidationReport


class RepairPlanner:
    """Derives repair scope from validator output; models never choose paths."""

    def plan(
        self,
        report: ValidationReport,
        *,
        allowed_paths: list[str],
        forbidden_paths: list[str] | None = None,
        max_rounds: int = 2,
    ) -> RepairPlan:
        forbidden = forbidden_paths or []
        actions: list[RepairAction] = []
        for issue in report.issues:
            strategy = (
                "human_review" if issue.severity is Severity.CRITICAL else issue.repair_strategy
            )
            profile = None
            if strategy == "model_patch":
                profile = (
                    "content_repair_main"
                    if issue.layer in (IssueLayer.L3, IssueLayer.L4)
                    else "json_repair_light"
                )
            actions.append(
                RepairAction(
                    issue_ids=[issue.issue_id],
                    strategy=strategy,  # type: ignore[arg-type]
                    target_scope=issue.scope.json_path,
                    allowed_paths=list(allowed_paths),
                    validator_layers=[issue.layer.value],
                    model_profile=profile,
                )
            )
        return RepairPlan(
            artifact_id=report.artifact_id,
            artifact_version=report.artifact_version,
            actions=actions,
            max_model_calls=max_rounds,
            allowed_json_paths=list(allowed_paths),
            forbidden_json_paths=forbidden,
            requires_full_regeneration=False,
        )
