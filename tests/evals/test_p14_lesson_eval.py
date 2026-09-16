import json
from pathlib import Path

import pytest

from core.settings import settings
from coursepilot.llm import CoursePilotLLMBudgetExceeded
from evaluation.p14_lesson_eval import (
    P14BudgetLedger,
    P14ResponseCheckpoint,
    _strict_provider_settings,
    estimate_blueprint_smoke_budget,
    run_blueprint_smoke,
    run_real_pilot,
)


def test_p14_checkpoint_persists_response_and_audit_atomically(tmp_path: Path) -> None:
    checkpoint = P14ResponseCheckpoint(tmp_path / "checkpoint", resume=False)
    response = {
        "request_sha256": "request-1",
        "result": {"answer": "ok"},
        "usage": {"total_tokens": 12},
    }
    checkpoint.save("request-1", response)
    checkpoint.record_invocation(
        {
            "request_sha256": "request-1",
            "prompt_name": "lesson/p14_plan_blueprint",
            "prompt_sha256": "a" * 64,
            "schema": "LessonBlueprint",
            "status": "success",
        }
    )

    resumed = P14ResponseCheckpoint(tmp_path / "checkpoint", resume=True)
    assert resumed.load("request-1")["result"] == {"answer": "ok"}
    audit = json.loads(resumed.audit_path.read_text(encoding="utf-8"))
    assert audit[0]["status"] == "success"
    assert not list(resumed.root.rglob("*.tmp"))


def test_p14_checkpoint_requires_explicit_resume(tmp_path: Path) -> None:
    root = tmp_path / "checkpoint"
    checkpoint = P14ResponseCheckpoint(root, resume=False)
    checkpoint.save("request-1", {"request_sha256": "request-1", "result": {}})

    with pytest.raises(RuntimeError, match="pass --resume"):
        P14ResponseCheckpoint(root, resume=False)


def test_p14_provider_settings_use_dedicated_profile_and_restore() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    old_profile = settings.COURSEPILOT_MODEL_PROFILE_PATH
    old_retries = settings.COURSEPILOT_LLM_MAX_RETRIES

    with _strict_provider_settings(repository_root):
        profile_path = Path(settings.COURSEPILOT_MODEL_PROFILE_PATH)
        profiles = {
            item["profile_id"]: item
            for item in json.loads(profile_path.read_text(encoding="utf-8"))["profiles"]
        }
        assert profiles["planner_main"]["timeout_seconds"] == 180
        assert profiles["generator_main"]["timeout_seconds"] == 240
        assert profiles["content_repair_main"]["timeout_seconds"] == 180
        assert settings.COURSEPILOT_LLM_MAX_RETRIES == 1

    assert settings.COURSEPILOT_MODEL_PROFILE_PATH == old_profile
    assert settings.COURSEPILOT_LLM_MAX_RETRIES == old_retries


def test_p14_blueprint_smoke_preflight_stays_below_authorized_cap() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    report = estimate_blueprint_smoke_budget(repository_root)

    assert report["record_id"] == "p14-lesson-02-perceptron-lab"
    assert report["logical_request_count"] == 1
    assert report["authorized_cost_cap_cny"] == 0.03
    assert report["within_limits"] is True


def test_p14_blueprint_smoke_does_not_execute_downstream_stages(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from agents.coursepilot.lesson.generator import LessonGenerator

    repository_root = Path(__file__).resolve().parents[2]
    original = LessonGenerator.build_blueprint

    def deterministic_blueprint(self, **kwargs):
        fake = LessonGenerator(use_model=False)
        return original(fake, **kwargs)

    monkeypatch.setattr(LessonGenerator, "build_blueprint", deterministic_blueprint)
    report = run_blueprint_smoke(
        repository_root,
        checkpoint_dir=tmp_path / "checkpoint",
    )

    assert report["status"] == "completed"
    assert report["executed_stages"] == ["p14_blueprint"]
    assert report["excluded_stages"] == [
        "cp_b0",
        "session_generation",
        "repair",
        "full_pilot",
    ]
    assert report["usage"]["provider_request_count"] == 0


def test_p14_budget_ledger_settles_actual_usage_and_blocks_before_dispatch(
    tmp_path: Path,
) -> None:
    ledger = P14BudgetLedger(tmp_path / "budget.json", resume=False)
    ledger.authorize(
        request_sha256="request-1",
        prompt_name="lesson/p14_plan_blueprint",
        profile_id="planner_main",
        estimated_input_tokens=3_000,
        configured_max_output_tokens=4_096,
    )
    ledger.settle(
        {
            "request_sha256": "request-1",
            "status": "success",
            "provider_called": True,
            "usage": {"input_tokens": 3_095, "output_tokens": 7_621},
        }
    )
    summary = ledger.summary()
    assert summary["committed_or_reserved_cost_cny"] == 0.018337
    assert summary["pending_request_count"] == 0

    with pytest.raises(CoursePilotLLMBudgetExceeded, match="would exceed"):
        ledger.authorize(
            request_sha256="request-too-large",
            prompt_name="lesson/p14_generate_session",
            profile_id="generator_main",
            estimated_input_tokens=20_000,
            configured_max_output_tokens=120_000,
        )
    assert "request-too-large" not in ledger.document["requests"]


def test_real_runner_executes_replan_as_a_second_planner_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    prompts: list[str] = []

    def fake_generate_structured(*, prompt_name, fallback, **_kwargs):
        prompts.append(prompt_name)
        return fallback()

    monkeypatch.setattr(
        "agents.coursepilot.lesson.generator.generate_structured", fake_generate_structured
    )
    monkeypatch.setattr(
        "agents.coursepilot.nodes.lesson_nodes.generate_structured", fake_generate_structured
    )
    report = run_real_pilot(
        Path(__file__).resolve().parents[2],
        checkpoint_dir=tmp_path / "checkpoint",
        resume=False,
    )

    assert report["status"] == "completed"
    assert prompts.count("lesson/p14_plan_blueprint") == 4
    assert prompts.count("lesson/p14_generate_session") == 5
    assert prompts.count("lesson/extract_knowledge_points") == 3
