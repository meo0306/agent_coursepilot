from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coursepilot.evals.formal_schemas import (
    CPDS1LessonDataset,
    CPDS1P14PilotDataset,
    P14FixtureBundle,
)
from evaluation.p14_cp_ds1_data import (
    FIXTURE_PATH,
    MANIFEST_PATH,
    PILOT_PATH,
    generate,
)

ROOT = Path(__file__).resolve().parents[2]


def test_p14_candidate_has_three_templates_and_one_negative_fixture() -> None:
    dataset = CPDS1P14PilotDataset.model_validate_json(
        (ROOT / PILOT_PATH).read_text(encoding="utf-8")
    )
    fixtures = P14FixtureBundle.model_validate_json(
        (ROOT / FIXTURE_PATH).read_text(encoding="utf-8")
    )
    assert len(dataset.cases) == 3
    assert {case.template_id for case in dataset.cases} == {
        "lesson_standard_university_v1",
        "lesson_lab_practice_v1",
        "lesson_seminar_v1",
    }
    assert len(fixtures.context_fixtures) == 4
    assert fixtures.negative_case.provider_calls_allowed == 0
    assert fixtures.negative_case.side_effects_allowed == 0


def test_p14_candidate_uses_only_ds3_calibration_and_two_courses() -> None:
    dataset = CPDS1P14PilotDataset.model_validate_json(
        (ROOT / PILOT_PATH).read_text(encoding="utf-8")
    )
    split = json.loads(
        (ROOT / "datasets/courserag_eval/v1/provenance/ds3_p07_split.json").read_text(
            encoding="utf-8"
        )
    )
    calibration = set(split["calibration_ids"])
    assert all(set(case.required_knowledge_point_ids) <= calibration for case in dataset.cases)
    assert {case.course_id for case in dataset.cases} == {
        "course_ai_algorithms_systems",
        "course_ai_general_education",
    }
    assert all(case.review_status.value == "candidate" for case in dataset.cases)


def test_p14_generation_is_byte_stable() -> None:
    first = generate(ROOT)
    first_bytes = (
        (ROOT / PILOT_PATH).read_bytes(),
        (ROOT / FIXTURE_PATH).read_bytes(),
        (ROOT / MANIFEST_PATH).read_bytes(),
    )
    second = generate(ROOT)
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first_bytes == (
        (ROOT / PILOT_PATH).read_bytes(),
        (ROOT / FIXTURE_PATH).read_bytes(),
        (ROOT / MANIFEST_PATH).read_bytes(),
    )
    assert hashlib.sha256(first_bytes[0]).hexdigest() == first["pilot_sha256"]


def test_p14_review_page_shows_readable_gold_and_hides_raw_json() -> None:
    result = generate(ROOT)
    review_root = ROOT / result["review_path"]
    first = (review_root / "index.html").read_text(encoding="utf-8")
    second = (review_root / "second_review.html").read_text(encoding="utf-8")
    assert first.count("class='card '") == 3
    assert second.count("class='card '") == 3
    assert "Transformer" in first
    assert "感知机" in first
    assert "职业自动化风险" in first
    assert "你只需要判断" in first
    assert "必要邻接" in first
    assert "非 Gold 合同负例" in first
    assert "完整 Fixture JSON" in first
    assert "p14_first_review_" in first
    assert "p14_second_review_" in second
    assert "id='export-review'" in first
    assert "coursepilot.p14-review-decisions.v1" in first
    assert "localStorage" in first


def test_legacy_cp_ds1_pilot_remains_valid() -> None:
    CPDS1LessonDataset.model_validate_json(
        (ROOT / "datasets/coursepilot_eval/v1/candidates/cp_ds1/pilot.json").read_text(
            encoding="utf-8"
        )
    )
