from __future__ import annotations

import hashlib
import json
from pathlib import Path

from coursepilot.evals.formal_schemas import (
    CPDS4P13PilotDataset,
    CPDS4ValidationDataset,
    CPDS5P13PilotDataset,
    CPDS5RepairDataset,
)
from evaluation.p13_cp_ds45_data import DS4_PATH, DS5_PATH, FIXTURE_PATH, generate

ROOT = Path(__file__).resolve().parents[2]


def test_p13_candidates_have_exact_distribution_and_hybrid_provenance() -> None:
    ds4 = CPDS4P13PilotDataset.model_validate_json((ROOT / DS4_PATH).read_text(encoding="utf-8"))
    ds5 = CPDS5P13PilotDataset.model_validate_json((ROOT / DS5_PATH).read_text(encoding="utf-8"))
    assert len(ds4.cases) == 30
    assert len(ds5.cases) == 15
    assert {
        item.artifact_type: sum(case.artifact_type == item.artifact_type for case in ds4.cases)
        for item in ds4.cases
    } == {"lesson": 10, "exam": 10, "ppt": 10}
    assert {
        item.artifact_type: sum(case.artifact_type == item.artifact_type for case in ds5.cases)
        for item in ds5.cases
    } == {"lesson": 5, "exam": 5, "ppt": 5}
    assert sum(case.clean_artifact for case in ds4.cases) == 3
    fixtures = json.loads((ROOT / FIXTURE_PATH).read_text(encoding="utf-8"))
    assert fixtures["source_strategy"] == "hybrid"
    assert set(fixtures["upstream"]) == {"ds2", "ds3"}
    assert len(fixtures["fixtures"]) == 9
    assert len(fixtures["variants"]) == 30


def test_p13_generation_is_byte_stable() -> None:
    first = generate(ROOT)
    ds4_path = ROOT / DS4_PATH
    ds5_path = ROOT / DS5_PATH
    fixture_path = ROOT / FIXTURE_PATH
    first_bytes = (ds4_path.read_bytes(), ds5_path.read_bytes(), fixture_path.read_bytes())
    second = generate(ROOT)
    assert first["bundle_sha256"] == second["bundle_sha256"]
    assert first_bytes == (ds4_path.read_bytes(), ds5_path.read_bytes(), fixture_path.read_bytes())
    assert (
        hashlib.sha256(first_bytes[0]).hexdigest()
        == json.loads(
            (
                ROOT / "datasets/coursepilot_eval/v1/provenance/p13_gold_bundle_manifest.json"
            ).read_text(encoding="utf-8")
        )["candidate_hashes"]["ds4"]
    )


def test_p13_review_ui_prioritizes_human_readable_checks() -> None:
    result = generate(ROOT)
    review_root = ROOT / result["review_path"]
    first = (review_root / "index.html").read_text(encoding="utf-8")
    second = (review_root / "second_review.html").read_text(encoding="utf-8")

    assert first.count("class='card ") == 45
    assert second.count("class='card ") == 27
    assert "你只需要判断" in first
    assert "正确值" in first and "故障值" in first
    assert "当前筛选项全部通过" in first
    assert "<details><summary>存疑时再看：完整 Gold / Fixture JSON" in first
    assert f"p13_first_review_{result['bundle_sha256'][:12]}.json" in first
    assert f"p13_second_review_{result['bundle_sha256'][:12]}.json" in second


def test_legacy_cp_ds4_ds5_pilots_remain_valid() -> None:
    root = ROOT / "datasets/coursepilot_eval/v1/candidates"
    CPDS4ValidationDataset.model_validate_json(
        (root / "cp_ds4/pilot.json").read_text(encoding="utf-8")
    )
    CPDS5RepairDataset.model_validate_json((root / "cp_ds5/pilot.json").read_text(encoding="utf-8"))


def test_p13_gold_exists_after_exact_owner_approval() -> None:
    assert (ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds4/p13_validation.json").is_file()
    assert (ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds5/p13_repair.json").is_file()
