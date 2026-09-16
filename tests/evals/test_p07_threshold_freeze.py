from __future__ import annotations

from pathlib import Path

from evaluation.p07_threshold_freeze import (
    THRESHOLD_CANDIDATE,
    P07ThresholdFreezeCandidate,
    generate_threshold_candidate,
)

ROOT = Path(__file__).resolve().parents[2]


def test_threshold_candidate_binds_completed_calibration_without_changing_threshold() -> None:
    first = generate_threshold_candidate(ROOT)
    second = generate_threshold_candidate(ROOT)

    assert first == second
    assert first.current_threshold == 0.75
    assert first.recommended_threshold == 0.75
    assert first.threshold_change_required is False
    assert first.recommended_metric.f1 == 0.071713
    assert (
        P07ThresholdFreezeCandidate.model_validate_json(
            (ROOT / THRESHOLD_CANDIDATE).read_text(encoding="utf-8")
        )
        == first
    )
