from pathlib import Path

from coursepilot.evals.p13_metrics import compare_issues
from coursepilot.validation.models import IssueScope, ValidationIssue


def test_p13_metric_matches_code_and_scope() -> None:
    expected = [
        ValidationIssue(
            issue_id="e",
            code="X",
            severity="error",
            layer="L1",
            scope=IssueScope(artifact_type="lesson", json_path="$.x"),
            auto_repairable=False,
        )
    ]
    result = compare_issues(expected, expected)
    assert result.detected_issues == 1
    assert result.scope_match == 1


def test_approved_p13_files_are_present() -> None:
    root = Path(__file__).parents[2]
    assert (root / "datasets/coursepilot_eval/v1/approved/cp_ds4/p13_validation.json").exists()
    assert (root / "datasets/coursepilot_eval/v1/approved/cp_ds5/p13_repair.json").exists()
