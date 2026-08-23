from coursepilot.repair.models import PatchOperation
from coursepilot.repair.planner import RepairPlanner
from coursepilot.repair.service import TargetedRepairService
from coursepilot.validation.models import IssueScope, ValidationIssue, ValidationReport


def test_critical_patch_is_candidate_needing_review() -> None:
    report = ValidationReport(
        artifact_id="a",
        artifact_version=1,
        artifact_type="lesson",
        validator_profile="v1",
        issues=[
            ValidationIssue(
                issue_id="i",
                code="LESSON_SCHEMA_REQUIRED_FIELD_MISSING",
                severity="critical",
                layer="L0",
                scope=IssueScope(artifact_type="lesson", json_path="$.x"),
                auto_repairable=True,
            )
        ],
    )
    plan = RepairPlanner().plan(report, allowed_paths=["$.x"])
    result = TargetedRepairService().apply(
        {"x": "old"},
        report,
        plan,
        [PatchOperation(op="replace", path="$.x", value="new", expected_value="old", issue_id="i")],
        revalidate=lambda _: ValidationReport(
            artifact_id="a", artifact_version=1, artifact_type="lesson", validator_profile="v1"
        ),
        output_artifact_version=2,
    )
    assert result.status == "needs_review"
    assert result.output_artifact_version == 2
