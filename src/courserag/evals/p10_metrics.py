from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationMetrics:
    total: int
    correct: int
    success_rate: float
    stale_citation_count: int


def citation_migration_metrics(
    expected: list[tuple[str, str | None]],
    actual: list[tuple[str, str | None]],
) -> MigrationMetrics:
    if len(expected) != len(actual):
        raise ValueError("Citation migration result count differs from Gold")
    correct = sum(left == right for left, right in zip(expected, actual, strict=True))
    stale = sum(
        actual_status in {"valid", "migrated"} and actual_id is None
        for actual_status, actual_id in actual
    )
    return MigrationMetrics(
        total=len(expected),
        correct=correct,
        success_rate=correct / len(expected) if expected else 1.0,
        stale_citation_count=stale,
    )


@dataclass(frozen=True)
class ReuseMetrics:
    change_coverage: float
    reused_artifact_ratio: float
    eligible_artifacts: int
    reused_artifacts: int


def incremental_reuse_metrics(
    *,
    expected_changed_ids: set[str],
    detected_changed_ids: set[str],
    eligible_artifact_ids: set[str],
    reused_artifact_ids: set[str],
) -> ReuseMetrics:
    if not reused_artifact_ids <= eligible_artifact_ids:
        raise ValueError("Reused artifacts must be eligible for reuse")
    coverage = (
        len(expected_changed_ids & detected_changed_ids) / len(expected_changed_ids)
        if expected_changed_ids
        else 1.0
    )
    ratio = len(reused_artifact_ids) / len(eligible_artifact_ids) if eligible_artifact_ids else 1.0
    return ReuseMetrics(
        change_coverage=coverage,
        reused_artifact_ratio=ratio,
        eligible_artifacts=len(eligible_artifact_ids),
        reused_artifacts=len(reused_artifact_ids),
    )


def l0_gate(failures: dict[str, int]) -> tuple[bool, tuple[str, ...]]:
    failed = tuple(sorted(name for name, count in failures.items() if count != 0))
    return not failed, failed


def relative_regression(*, baseline: float, candidate: float) -> float:
    if baseline <= 0:
        raise ValueError("Regression baseline must be positive")
    return (candidate - baseline) / baseline
