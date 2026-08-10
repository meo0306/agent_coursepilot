import json
from pathlib import Path

from evaluation.manifest import sha256_file
from evaluation.p09_dev_loader import load_p09_dev_bundle
from evaluation.p09_generation_reliability import (
    DELTA_DEEPSEEK_TOKEN_CAP,
    FRESH_CASE_IDS,
    GenerationReliabilityDeltaSystem,
    prepare_protocol,
)
from evaluation.p09_retrieval_qa_eval import P09SystemResult

ROOT = Path(__file__).resolve().parents[2]


class FakeFreshSystem:
    label = "fake-fresh"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def run(self, case: object) -> P09SystemResult:
        record_id = case.qa.record_id  # type: ignore[attr-defined]
        self.calls.append(record_id)
        return P09SystemResult(answer_status="answered", answer="fresh")


def test_fresh_case_set_is_exactly_11_main_plus_one_diagnostic() -> None:
    bundle = load_p09_dev_bundle(ROOT / "datasets/courserag_eval/v1")
    cases = {case.qa.record_id: case for case in bundle.cases}
    assert len(FRESH_CASE_IDS) == 12
    assert len(set(FRESH_CASE_IDS)) == 12
    assert set(FRESH_CASE_IDS).issubset(cases)
    assert (
        sum(cases[value].qa.evaluation_stratum == "retrieval_main" for value in FRESH_CASE_IDS)
        == 11
    )
    assert (
        sum(
            cases[value].qa.evaluation_stratum == "upstream_gap_diagnostic"
            for value in FRESH_CASE_IDS
        )
        == 1
    )
    assert all(cases[value].qa.split == "dev" for value in FRESH_CASE_IDS)


def test_protocol_is_preregistered_with_fixed_budget_and_no_test(tmp_path: Path) -> None:
    path, digest = prepare_protocol(ROOT, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert digest == sha256_file(path)
    assert payload["status"] == "preregistered_before_provider_calls"
    assert payload["fresh_case_ids"] == list(FRESH_CASE_IDS)
    assert payload["deepseek_additional_token_cap"] == DELTA_DEEPSEEK_TOKEN_CAP
    assert payload["cohere_additional_search_units"] == 0
    assert payload["test_access"] is False
    assert payload["post_run_prompt_tuning_allowed"] is False


def test_delta_system_calls_provider_only_for_fresh_cases() -> None:
    bundle = load_p09_dev_bundle(ROOT / "datasets/courserag_eval/v1")
    fresh = FakeFreshSystem()
    fixed = {
        case.qa.record_id: P09SystemResult(answer_status="answered", answer="fixed")
        for case in bundle.cases
    }
    system = GenerationReliabilityDeltaSystem(
        fresh_system=fresh,
        fixed_results=fixed,
        profile_sha256="a" * 64,
    )
    for case in bundle.cases:
        result = system.run(case)
        expected = "fresh" if case.qa.record_id in FRESH_CASE_IDS else "fixed"
        assert result.answer == expected
    assert fresh.calls == [
        case.qa.record_id for case in bundle.cases if case.qa.record_id in FRESH_CASE_IDS
    ]
