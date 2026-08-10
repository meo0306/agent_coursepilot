from pathlib import Path

import pytest

from evaluation.p09_dev_loader import load_p09_test_bundle
from evaluation.p10_component_eval import run_component_test
from evaluation.p10_formal_eval import (
    FORMAL_COHERE_SEARCH_UNIT_CAP,
    FORMAL_DEEPSEEK_TOKEN_CAP,
    _formal_usage,
    _restored_p08_cohere_units,
)

ROOT = Path(__file__).resolve().parents[2]


def test_test_loaders_fail_closed_before_the_lock(tmp_path: Path) -> None:
    dataset_root = ROOT / "datasets/courserag_eval/v1"
    with pytest.raises(ValueError, match="locked Test set"):
        load_p09_test_bundle(dataset_root)
    with pytest.raises(ValueError, match="locked Test set"):
        run_component_test(ROOT, tmp_path / "component.json")


def test_formal_usage_uses_cumulative_provider_high_water_mark() -> None:
    deepseek, cohere = _formal_usage(
        {
            "b7": {"usage": {"deepseek_total_tokens": 0, "cohere_search_units": 80}},
            "q2": {"usage": {"deepseek_total_tokens": 300_000, "cohere_search_units": 80}},
            "q3": {"usage": {"deepseek_total_tokens": 400_000, "cohere_search_units": 120}},
        }
    )
    assert deepseek == 700_000
    assert cohere == 120
    assert deepseek <= FORMAL_DEEPSEEK_TOKEN_CAP
    assert cohere <= FORMAL_COHERE_SEARCH_UNIT_CAP


def test_retrieval_resume_budget_counts_only_succeeded_cohere_cases(tmp_path: Path) -> None:
    checkpoint = tmp_path / "checkpoint.json"
    checkpoint.write_text(
        """{
          "cases": {
            "b5_cohere:one": {"status": "succeeded", "result": {"usage": {"search_units": 1}}},
            "b5_cohere:two": {"status": "failed", "result": {"usage": {"search_units": 9}}},
            "b4_hybrid_rrf:three": {"status": "succeeded", "result": {"usage": {}}}
          }
        }""",
        encoding="utf-8",
    )
    assert _restored_p08_cohere_units(checkpoint) == 1
