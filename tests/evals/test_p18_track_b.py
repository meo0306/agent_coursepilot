from pathlib import Path

from evaluation.p18_loader import load_p18_test
from evaluation.p18_track_b import LiveProbe, run_faults, run_journeys

ROOT = Path("datasets/coursepilot_eval/v1")


def test_locked_faults_use_production_error_mapping() -> None:
    loaded = load_p18_test(ROOT)
    report = run_faults(loaded.components["cp_ds8"])
    assert report["variant_count"] == 10
    assert report["passed_count"] == 10
    assert all(item["duplicate_side_effect_count"] == 0 for item in report["records"])


def test_missing_formal_index_is_reported_without_faking_journey_success() -> None:
    loaded = load_p18_test(ROOT)
    probe = LiveProbe(
        coursepilot_healthy=True,
        courserag_healthy=True,
        capabilities_available=True,
        formal_index_available=False,
    )
    report = run_journeys(loaded.components["sys_ds1"], probe)
    assert report["journey_count"] == 8
    assert report["contract_passed_count"] == 8
    assert report["live_passed_count"] == 1
    assert report["blocked_count"] == 7


def test_formal_index_allows_all_contract_valid_journeys() -> None:
    loaded = load_p18_test(ROOT)
    probe = LiveProbe(
        coursepilot_healthy=True,
        courserag_healthy=True,
        capabilities_available=True,
        formal_index_available=True,
        available_courses=("course_ai_algorithms_systems", "course_ai_general_education"),
    )
    report = run_journeys(loaded.components["sys_ds1"], probe)
    assert report["contract_passed_count"] == 8
    assert report["live_passed_count"] == 8
    assert report["blocked_count"] == 0
