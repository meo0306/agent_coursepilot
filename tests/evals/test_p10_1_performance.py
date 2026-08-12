from __future__ import annotations

from pathlib import Path

from evaluation.p10_1_performance import (
    _percentile,
    _SectionUpdateWorkload,
    _stage_environment,
)


def test_percentile_is_deterministic_for_short_ds8_samples() -> None:
    assert _percentile([1.0], 0.95) == 1.0
    assert _percentile([1.0, 2.0, 3.0], 0.5) == 2.0
    assert _percentile([1.0, 2.0, 3.0], 0.95) == 2.9


def test_ds8_stage_environment_reuses_identical_warm_workload(tmp_path: Path) -> None:
    workload = _SectionUpdateWorkload()
    with _stage_environment(tmp_path, "single_section_update", Path.cwd()) as environment:
        cold = environment.runner.run(workload, environment.context, force=True)
        warm = environment.runner.run(workload, environment.context, force=False)

    assert cold.id == warm.id
    assert cold.artifact_id is not None
