import pytest

from courserag.evals.p10_metrics import (
    citation_migration_metrics,
    incremental_reuse_metrics,
    l0_gate,
    relative_regression,
)


def test_migration_and_reuse_metrics() -> None:
    migration = citation_migration_metrics(
        [("migrated", "new-1"), ("invalid", None)],
        [("migrated", "new-1"), ("invalid", None)],
    )
    assert migration.success_rate == 1.0
    assert migration.stale_citation_count == 0
    reuse = incremental_reuse_metrics(
        expected_changed_ids={"a", "b"},
        detected_changed_ids={"a", "b", "c"},
        eligible_artifact_ids={"1", "2", "3", "4"},
        reused_artifact_ids={"1", "2", "3"},
    )
    assert reuse.change_coverage == 1.0
    assert reuse.reused_artifact_ratio == 0.75


def test_l0_and_regression_guards() -> None:
    assert l0_gate({"secret_leak": 0, "silent_fallback": 0}) == (True, ())
    assert l0_gate({"secret_leak": 1, "silent_fallback": 0}) == (
        False,
        ("secret_leak",),
    )
    assert relative_regression(baseline=100, candidate=120) == pytest.approx(0.2)
    with pytest.raises(ValueError):
        relative_regression(baseline=0, candidate=1)
