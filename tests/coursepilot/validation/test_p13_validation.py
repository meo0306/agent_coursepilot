from coursepilot.repair.planner import RepairPlanner
from coursepilot.validation.models import IssueScope, Severity, ValidationIssue, ValidationReport


def test_critical_alias_and_report_counts() -> None:
    issue = ValidationIssue(
        issue_id="i1",
        code="LESSON_SCHEMA_REQUIRED_FIELD_MISSING",
        severity="blocking",
        layer="L0",
        scope=IssueScope(
            artifact_type="lesson", item_id="root", json_path="$.session_plan[0].teaching_focus"
        ),
        auto_repairable=True,
    )
    report = ValidationReport(
        artifact_id="a",
        artifact_version=1,
        artifact_type="lesson",
        validator_profile="v1",
        issues=[issue],
    ).finalize()
    assert report.critical_count == 1
    assert report.passed is False


def test_critical_issue_is_human_review_and_paths_are_planner_owned() -> None:
    report = ValidationReport(
        artifact_id="a",
        artifact_version=1,
        artifact_type="lesson",
        validator_profile="v1",
        issues=[
            ValidationIssue(
                issue_id="i1",
                code="LESSON_SCHEMA_REQUIRED_FIELD_MISSING",
                severity=Severity.CRITICAL,
                layer="L0",
                scope=IssueScope(
                    artifact_type="lesson", json_path="$.session_plan[0].teaching_focus"
                ),
                auto_repairable=True,
            )
        ],
    )
    plan = RepairPlanner().plan(report, allowed_paths=["$.session_plan[0].teaching_focus"])
    assert plan.actions[0].strategy == "human_review"
    assert plan.allowed_json_paths == ["$.session_plan[0].teaching_focus"]
