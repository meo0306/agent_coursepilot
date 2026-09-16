import json
import shutil
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from coursepilot.evals.p18_metrics import aggregate_human_reviews, aggregate_run_rows
from coursepilot.integration.fault_isolation import inject_fault
from evaluation.p18_case_adapters import validate_case_mapping
from evaluation.p18_human_review import build_review_package
from evaluation.p18_loader import P18DatasetBoundaryError, load_p18_dev, load_p18_test
from evaluation.p18_report import build_final_report
from evaluation.p18_runner import (
    P18Budget,
    P18BudgetExceeded,
    P18Ledger,
    is_provider_off_peak,
    prepare_dev_revision_checkpoint,
)

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "datasets/coursepilot_eval/v1"


def test_p18_dev_loader_never_returns_test_blind_or_sys_journeys() -> None:
    loaded = load_p18_dev(DATASET)
    assert len(loaded.components["cp_ds1"]) == 6
    assert len(loaded.components["cp_ds2"]) == 6
    assert len(loaded.components["cp_ds3"]) == 6
    assert len(loaded.components["cp_ds4"]) == 60
    assert len(loaded.components["cp_ds5"]) == 42
    assert len(loaded.components["cp_ds6"]) == 12
    assert len(loaded.components["cp_ds7"]) == 9
    assert len(loaded.components["cp_ds8"]) == 20
    assert loaded.record_count == 161
    assert loaded.components["sys_ds1"] == ()
    assert all(
        getattr(case, "split", getattr(case, "split_role", None)) in {"dev", "dev_contract"}
        for cases in loaded.components.values()
        for case in cases
    )


def test_all_p18_business_dev_cases_map_without_provider_calls() -> None:
    loaded = load_p18_dev(DATASET)
    mappings = [
        validate_case_mapping(case)
        for component in ("cp_ds1", "cp_ds2", "cp_ds3")
        for case in loaded.components[component]
    ]
    assert len(mappings) == 18
    assert all(item["evidence_count"] >= 2 for item in mappings)
    assert all(item["planned_items"] >= 1 for item in mappings)
    exam = [item for item in mappings if item["artifact_type"] == "exam"]
    assert all(item["planned_score"] > 0 for item in exam)


def test_p18_dev_fault_variants_use_the_stable_error_boundary() -> None:
    loaded = load_p18_dev(DATASET)
    checked = 0
    for case in loaded.components["cp_ds8"]:
        for index, expected in enumerate(case.variants):
            actual = inject_fault(case.scenario_family, index)
            assert actual.error_class == expected.expected_error_class
            assert actual.user_status == expected.expected_user_status
            assert actual.side_effect_count == expected.expected_side_effect_count
            assert actual.retryable is expected.retry_rule.startswith("仅在同一幂等键")
            checked += 1
    assert checked == 20


def test_p18_test_loader_refuses_unlocked_repository(tmp_path: Path) -> None:
    dataset = tmp_path / "coursepilot_eval/v1"
    shutil.copytree(DATASET, dataset)
    (dataset / "test.lock.json").write_text(
        json.dumps(
            {
                "schema_version": "course-eval.test-lock.v1",
                "dataset_id": "coursepilot-eval",
                "dataset_version": "v1",
                "locked": False,
                "test_ids_sha256": None,
                "approved_manifest_sha256": None,
                "locked_at": None,
                "locked_by": None,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(P18DatasetBoundaryError, match="not locked"):
        load_p18_test(dataset)


def test_p18_budget_reserves_worst_case_and_is_resume_bound(tmp_path: Path) -> None:
    budget = P18Budget(
        max_cost_cny=Decimal("0.01"),
        max_input_tokens=10_000,
        max_output_tokens=10_000,
        max_requests=2,
    )
    ledger = P18Ledger(tmp_path / "ledger.json", budget, resume=False)
    ledger.reserve("one", 1000, 1000)
    with pytest.raises(P18BudgetExceeded):
        ledger.reserve("two", 9000, 9000)
    resumed = P18Ledger(tmp_path / "ledger.json", budget, resume=True)
    assert resumed.totals()["requests"] == 1


def test_p18_ledger_implements_structured_response_checkpoint(tmp_path: Path) -> None:
    ledger = P18Ledger(tmp_path / "ledger.json", P18Budget(), resume=False)
    ledger.authorize_request(
        request_sha256="a" * 64,
        prompt_name="lesson/p18",
        profile_id="planner_main",
        estimated_input_tokens=100,
        configured_max_output_tokens=200,
    )
    response = {"request_sha256": "a" * 64, "parsed": {"ok": True}}
    ledger.save("a" * 64, response)
    ledger.record_invocation(
        {
            "request_sha256": "a" * 64,
            "status": "success",
            "usage": {"input_tokens": 80, "output_tokens": 40},
        }
    )
    assert ledger.load("a" * 64) == response
    assert ledger.totals()["input_tokens"] == 80
    assert ledger.totals()["output_tokens"] == 40
    ledger.record_invocation(
        {
            "request_sha256": "a" * 64,
            "status": "cached",
            "usage": None,
        }
    )
    assert ledger.totals()["input_tokens"] == 80
    assert ledger.totals()["output_tokens"] == 40


def test_p18_ledger_blocks_ambiguous_resume_but_reuses_saved_response(tmp_path: Path) -> None:
    ledger = P18Ledger(tmp_path / "ambiguous.json", P18Budget(), resume=False)
    ledger.reserve("ambiguous", 10, 10)
    with pytest.raises(P18BudgetExceeded, match="AMBIGUOUS"):
        ledger.reserve("ambiguous", 10, 10)
    ledger.save("ambiguous", {"result": {"ok": True}})
    assert ledger.load("ambiguous") == {"result": {"ok": True}}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-24T10:00:00+08:00", False),
        ("2026-08-24T13:00:00+08:00", True),
        ("2026-08-24T20:00:00+08:00", True),
        ("2026-08-23T10:00:00+08:00", True),
    ],
)
def test_p18_provider_window_uses_beijing_rules(value: str, expected: bool) -> None:
    now = datetime.fromisoformat(value).astimezone(ZoneInfo("Asia/Shanghai"))
    assert is_provider_off_peak(now) is expected


def test_peak_pause_does_not_reserve_provider_budget(tmp_path: Path) -> None:
    calls = 0

    def pause() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("paused")

    ledger = P18Ledger(
        tmp_path / "peak.json",
        P18Budget(),
        resume=False,
        provider_window_guard=pause,
    )
    with pytest.raises(RuntimeError, match="paused"):
        ledger.authorize_request(
            request_sha256="b" * 64,
            prompt_name="exam/p18",
            profile_id="generator_main",
            estimated_input_tokens=100,
            configured_max_output_tokens=200,
        )
    assert calls == 1
    assert ledger.totals()["requests"] == 0
    ledger.record_invocation(
        {
            "request_sha256": "b" * 64,
            "status": "failed",
            "provider_called": False,
            "error_category": "budget_exceeded",
        }
    )
    assert ledger.totals()["requests"] == 0


def test_p18_revision_reopens_only_successful_b10_contract_failures(tmp_path: Path) -> None:
    source = tmp_path / "r1"
    source.mkdir()
    P18Ledger(source / "ledger.json", P18Budget(), resume=False)
    rows = [
        {
            "component": "cp_ds1",
            "record_id": "a",
            "track": "cp_b10",
            "status": "succeeded",
            "contract_pass": False,
        },
        {
            "component": "cp_ds2",
            "record_id": "b",
            "track": "cp_b10",
            "status": "failed",
            "contract_pass": False,
        },
        {
            "component": "cp_ds1",
            "record_id": "a",
            "track": "cp_b0",
            "status": "succeeded",
            "contract_pass": False,
        },
    ]
    (source / "rows.json").write_text(json.dumps(rows), encoding="utf-8")
    target = tmp_path / "r2"
    manifest = prepare_dev_revision_checkpoint(source_dir=source, target_dir=target)
    carried = json.loads((target / "rows.json").read_text(encoding="utf-8"))
    assert len(manifest["reopened_rows"]) == 1
    assert {(row["record_id"], row["track"]) for row in carried} == {
        ("a", "cp_b0"),
        ("b", "cp_b10"),
    }


def test_p18_metrics_keep_failed_and_fallback_rows() -> None:
    report = aggregate_run_rows(
        [
            {
                "track": "cp_b10",
                "status": "succeeded",
                "fallback": False,
                "contract_pass": True,
                "latency_ms": 10,
            },
            {
                "track": "cp_b10",
                "status": "failed",
                "fallback": True,
                "contract_pass": False,
                "latency_ms": 20,
            },
        ]
    )
    track = report["tracks"]["cp_b10"]
    assert track["samples"] == 2
    assert track["failed"] == 1
    assert track["fallback_samples"] == 1
    assert track["contract_pass_rate"] == 0.5


def test_p18_review_package_is_blinded_and_downloadable(tmp_path: Path) -> None:
    paths = build_review_package(
        artifacts=[
            {
                "case_id": "c1",
                "track": "cp_b10",
                "artifact_type": "lesson",
                "artifact": {"title": "x"},
            }
        ],
        output_dir=tmp_path,
        seed="fixed",
    )
    html = Path(paths["review_html"]).read_text(encoding="utf-8")
    assert "cp_b10" not in html
    assert "download='p18_review_decisions.json'" in html


def test_human_aggregate_uses_all_units() -> None:
    result = aggregate_human_reviews(
        [
            {
                "artifact_status": "accepted",
                "rubric_scores": {"L-H1": 5},
                "edit_burden": 1,
                "critical_defect": False,
            }
        ]
    )
    assert result["acceptable_rate"] == 1
    assert result["mean_rubric"] == 5


def test_failed_formal_gate_does_not_emit_public_metric_candidates() -> None:
    report = build_final_report(
        automatic={"l0": {"generation_failures": 1}},
        human={
            "review_units": 24,
            "acceptable_rate": 0.9,
            "mean_rubric": 4.5,
            "mean_edit_burden": 1.0,
        },
        locked_test=True,
    )
    assert report["status"] == "gate_failed"
    assert report["public_metric_candidates"] == []
