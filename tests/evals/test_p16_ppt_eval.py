import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from coursepilot.llm import CoursePilotLLMBudgetExceeded, extract_token_usage
from evaluation.p16_ppt_eval import (
    _BudgetCheckpoint,
    _DeepSeekFlashPricing,
    _is_off_peak,
    _saved_budget_summary,
)

BEIJING = ZoneInfo("Asia/Shanghai")


def _checkpoint(tmp_path, *, now_hour: int = 20) -> _BudgetCheckpoint:
    return _BudgetCheckpoint(
        additional_max_input=230_000,
        additional_max_output=90_000,
        additional_max_requests=32,
        additional_max_cost_cny=Decimal("0.80"),
        console_baseline_cny=Decimal("1.02"),
        console_total_cap_cny=Decimal("1.82"),
        path=tmp_path / "checkpoint.json",
        now=lambda: datetime(2026, 8, 20, now_hour, tzinfo=BEIJING),
    )


def test_p16_new_off_peak_price_matches_provider_console_breakdown() -> None:
    cost = _DeepSeekFlashPricing().cost(
        input_tokens=401_755,
        output_tokens=138_206,
        cache_hit_input_tokens=227_840,
        cache_miss_input_tokens=173_915,
    )

    assert cost == Decimal("0.8941915")


@pytest.mark.parametrize(
    ("hour", "expected"),
    [
        (8, True),
        (9, False),
        (11, False),
        (12, True),
        (13, True),
        (14, False),
        (17, False),
        (18, True),
        (20, True),
    ],
)
def test_p16_off_peak_window(hour: int, expected: bool) -> None:
    assert _is_off_peak(datetime(2026, 8, 20, hour, tzinfo=BEIJING)) is expected


def test_p16_budget_resume_keeps_original_authorization_baseline(tmp_path) -> None:
    legacy_path = tmp_path / "checkpoint.json"
    legacy_path.write_text(
        '{"input_tokens":149491,"output_tokens":44023,"requests":20,"cache":{}}',
        encoding="utf-8",
    )
    checkpoint = _checkpoint(tmp_path)

    checkpoint.authorize_request(
        request_sha256="request-1",
        prompt_name="ppt/p16_generate_slide",
        profile_id="generator_main",
        estimated_input_tokens=6_000,
        configured_max_output_tokens=8_192,
    )
    checkpoint.save(
        "request-1",
        {
            "usage": {
                "input_tokens": 6_000,
                "output_tokens": 2_000,
                "cache_hit_input_tokens": 4_000,
                "cache_miss_input_tokens": 2_000,
            }
        },
    )

    resumed = _checkpoint(tmp_path)
    summary = resumed.summary()
    assert summary["incremental_requests"] == 1
    assert summary["incremental_input_tokens"] == 6_000
    assert summary["incremental_output_tokens"] == 2_000
    assert summary["incremental_cost_cny"] == "0.012200"
    assert summary["estimated_console_total_cny"] == "1.032200"


def test_p16_budget_rejects_peak_time_before_provider_dispatch(tmp_path) -> None:
    checkpoint = _checkpoint(tmp_path, now_hour=10)

    with pytest.raises(CoursePilotLLMBudgetExceeded, match="NOT_OFF_PEAK"):
        checkpoint.authorize_request(
            request_sha256="request-peak",
            prompt_name="ppt/p16_generate_slide",
            profile_id="generator_main",
            estimated_input_tokens=1,
            configured_max_output_tokens=1,
        )


def test_p16_budget_prices_unclassified_input_as_cache_miss(tmp_path) -> None:
    checkpoint = _checkpoint(tmp_path)
    checkpoint.save(
        "request-unknown-cache",
        {"usage": {"input_tokens": 100_000, "output_tokens": 100_000}},
    )

    assert checkpoint.summary()["incremental_cost_cny"] == "0.600000"
    with pytest.raises(CoursePilotLLMBudgetExceeded, match="BUDGET_EXCEEDED"):
        checkpoint.authorize_request(
            request_sha256="request-over-budget",
            prompt_name="ppt/p16_generate_slide",
            profile_id="generator_main",
            estimated_input_tokens=100_000,
            configured_max_output_tokens=30_000,
        )


def test_p16_failed_provider_response_is_counted_for_reconciliation(tmp_path) -> None:
    checkpoint = _checkpoint(tmp_path)
    checkpoint.record_invocation(
        {
            "status": "failed",
            "attempts": [
                {
                    "billing_status": "unknown_pending_reconciliation",
                    "usage": {"input_tokens": 2_000, "output_tokens": 1_000},
                },
                {"billing_status": "not_sent", "usage": {}},
            ],
        }
    )

    summary = checkpoint.summary()
    assert summary["incremental_requests"] == 1
    assert summary["failed_billable_or_unknown_invocations"] == 1
    assert summary["incremental_cost_cny"] == "0.007500"


def test_p16_failed_request_requires_and_limits_manual_retry(tmp_path) -> None:
    request_sha256 = "failed-request"
    checkpoint = _checkpoint(tmp_path)
    failed = {
        "status": "failed",
        "request_sha256": request_sha256,
        "attempts": [
            {
                "billing_status": "unknown_pending_reconciliation",
                "usage": {"input_tokens": 2_000, "output_tokens": 1_000},
            }
        ],
    }
    checkpoint.record_invocation(failed)

    with pytest.raises(CoursePilotLLMBudgetExceeded, match="APPROVAL_REQUIRED"):
        checkpoint.authorize_request(
            request_sha256=request_sha256,
            prompt_name="ppt/p16_generate_slide",
            profile_id="generator_main",
            estimated_input_tokens=2_000,
            configured_max_output_tokens=8_192,
        )

    authorized = _BudgetCheckpoint(
        additional_max_input=230_000,
        additional_max_output=90_000,
        additional_max_requests=32,
        additional_max_cost_cny=Decimal("0.80"),
        console_baseline_cny=Decimal("1.02"),
        console_total_cap_cny=Decimal("1.82"),
        path=tmp_path / "checkpoint.json",
        now=lambda: datetime(2026, 8, 20, 20, tzinfo=BEIJING),
        manual_retry_request_sha256s=frozenset({request_sha256}),
    )
    authorized.authorize_request(
        request_sha256=request_sha256,
        prompt_name="ppt/p16_generate_slide",
        profile_id="generator_main",
        estimated_input_tokens=2_000,
        configured_max_output_tokens=8_192,
    )
    authorized.record_invocation(failed)

    with pytest.raises(CoursePilotLLMBudgetExceeded, match="RETRY_EXHAUSTED"):
        authorized.authorize_request(
            request_sha256=request_sha256,
            prompt_name="ppt/p16_generate_slide",
            profile_id="generator_main",
            estimated_input_tokens=2_000,
            configured_max_output_tokens=8_192,
        )


def test_p16_resume_accepts_only_explicit_output_budget_extension(tmp_path) -> None:
    checkpoint = _checkpoint(tmp_path)
    checkpoint._persist()

    extended = _BudgetCheckpoint(
        additional_max_input=230_000,
        additional_max_output=91_000,
        additional_max_requests=32,
        additional_max_cost_cny=Decimal("0.80"),
        console_baseline_cny=Decimal("1.02"),
        console_total_cap_cny=Decimal("1.82"),
        path=tmp_path / "checkpoint.json",
        now=lambda: datetime(2026, 8, 20, 20, tzinfo=BEIJING),
        approved_previous_additional_max_output=90_000,
    )
    extended._persist()
    saved = json.loads((tmp_path / "checkpoint.json").read_text(encoding="utf-8"))
    assert saved["authorization"]["additional_max_output"] == 91_000

    with pytest.raises(RuntimeError, match="AUTHORIZATION_MISMATCH"):
        _BudgetCheckpoint(
            additional_max_input=231_000,
            additional_max_output=92_000,
            additional_max_requests=32,
            additional_max_cost_cny=Decimal("0.80"),
            console_baseline_cny=Decimal("1.02"),
            console_total_cap_cny=Decimal("1.82"),
            path=tmp_path / "checkpoint.json",
            now=lambda: datetime(2026, 8, 20, 20, tzinfo=BEIJING),
            approved_previous_additional_max_output=91_000,
        )


def test_extract_token_usage_preserves_provider_cache_and_thinking_details() -> None:
    message = SimpleNamespace(
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 50,
            "total_tokens": 150,
            "input_token_details": {"cache_read": 70},
            "output_token_details": {"reasoning": 30},
        }
    )

    assert extract_token_usage(message) == {
        "input_tokens": 100,
        "output_tokens": 50,
        "total_tokens": 150,
        "usage_source": "provider",
        "usage_estimated": False,
        "cache_hit_input_tokens": 70,
        "thinking_output_tokens": 30,
    }


def test_p16_stopped_report_uses_public_budget_summary() -> None:
    summary = _saved_budget_summary(
        {
            "requests": 31,
            "input_tokens": 221_728,
            "output_tokens": 75_059,
            "incremental_cost_cny": "0.1986479",
            "authorization": {
                "start_requests": 20,
                "start_input_tokens": 149_491,
                "start_output_tokens": 44_023,
                "additional_max_requests": 32,
                "additional_max_input": 230_000,
                "additional_max_output": 90_000,
                "additional_max_cost_cny": "0.80",
                "console_baseline_cny": "1.02",
                "console_total_cap_cny": "1.82",
                "pricing_identity": "pricing-v1",
            },
            "failed_invocations": [{}],
            "cache": {"must-not-leak": {"result": "large"}},
        }
    )

    assert summary["incremental_requests"] == 11
    assert summary["incremental_input_tokens"] == 72_237
    assert summary["incremental_output_tokens"] == 31_036
    assert summary["estimated_console_total_cny"] == "1.218648"
    assert "cache" not in summary
