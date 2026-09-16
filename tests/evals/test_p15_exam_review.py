import json
from pathlib import Path

import pytest

from coursepilot.llm import CoursePilotLLMBudgetExceeded
from evaluation.p15_exam_review import (
    RUBRIC,
    LegacyBaselineCheckpoint,
    PriorProviderUsage,
    ReviewBudgetLimits,
    _fixed_legacy_blueprint,
    build_review_package,
    estimate_legacy_baseline,
    finalize_decisions,
)

ROOT = Path(__file__).resolve().parents[2]


def _question(track: str) -> dict:
    if track == "cp_b0":
        return {
            "question_type": "single_choice",
            "difficulty": "medium",
            "score": 4,
            "question_text": "Legacy stem",
            "options": {"A": "yes", "B": "no"},
            "correct_answer": "A",
            "explanation": "Legacy explanation",
            "knowledge_point": "KP",
            "references": [{"chunk_id": "ev-1"}],
        }
    return {
        "question_id": "q-1",
        "slot_id": "slot-1",
        "question_number": 1,
        "question_type": "single_choice",
        "difficulty": "medium",
        "score": 4,
        "content_role": "definition",
        "stem": "P15 stem",
        "options": {"A": "yes", "B": "no"},
        "answer": "A",
        "explanation": "P15 explanation",
        "knowledge_point_ids": ["kp-1"],
        "evidence_ids": ["ev-1"],
    }


def _write_sources(tmp_path: Path) -> tuple[Path, Path, Path]:
    dataset = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    case_ids = [item["record_id"] for item in dataset["cases"]]
    validation = {
        key: True
        for key in (
            "schema_valid",
            "question_count_valid",
            "score_valid",
            "option_valid",
            "answer_valid",
            "explanation_valid",
            "knowledge_coverage_valid",
            "citation_valid",
            "duplicate_valid",
        )
    }
    baseline = {
        "status": "completed",
        "comparison_contract": "fixed_approved_blueprint_legacy_question_generator",
        "hard_cap_ok": True,
        "fallback_count": 0,
        "model_switch_count": 0,
        "actual": {"provider_requests": 15, "input_tokens": 10, "output_tokens": 20},
        "cases": [
            {
                "case_id": case_id,
                "blueprint": {"chapter_range": case_id},
                "questions": [_question("cp_b0")],
                "validation_report": validation,
            }
            for case_id in case_ids
        ],
    }
    state = {
        "cases": {
            f"p3:{case_id}": {
                "case_id": case_id,
                "status": "completed",
                "questions": [_question("p15")],
                "global_report": {"errors": []},
            }
            for case_id in case_ids
        }
    }
    report = {
        "functional_gate": {"all_three_cases_completed": True},
        "actual": {"provider_requests": 53, "input_tokens": 100, "output_tokens": 200},
    }
    paths = (tmp_path / "baseline.json", tmp_path / "state.json", tmp_path / "report.json")
    for path, payload in zip(paths, (baseline, state, report), strict=True):
        path.write_text(json.dumps(payload), encoding="utf-8")
    return paths


def test_p15_cp_b0_preflight_is_network_free_and_covers_all_cases() -> None:
    result = estimate_legacy_baseline(ROOT)

    assert result["external_calls_made"] == 0
    assert result["case_count"] == 3
    assert result["planned_questions"] == 45
    assert result["maximum_requests"] == 12
    assert result["conditional_repair_requests"] == 0
    assert result["authorization_required"] is True


def test_fixed_legacy_blueprint_has_one_group_per_approved_question_type() -> None:
    dataset = json.loads(
        (ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    targets = {item["target_id"]: item for item in dataset["targets"]}

    for case in dataset["cases"]:
        blueprint = _fixed_legacy_blueprint(case, targets)
        raw = case["blueprint"]

        assert len(blueprint.question_groups) == 4
        assert {item.question_type: item.count for item in blueprint.question_groups} == raw[
            "question_counts"
        ]
        assert blueprint.total_score == raw["required_total_score"]


def test_legacy_checkpoint_counts_prior_requests_against_cumulative_cap(
    tmp_path: Path,
) -> None:
    checkpoint = LegacyBaselineCheckpoint(
        tmp_path / "checkpoint",
        resume=False,
        limits=ReviewBudgetLimits(
            max_cost_cny=0.45,
            max_input_tokens=100_000,
            max_output_tokens=150_000,
            max_requests=16,
        ),
        prior_usage=PriorProviderUsage(
            provider_requests=16,
            input_tokens=59_756,
            output_tokens=72_495,
        ),
    )

    with pytest.raises(
        CoursePilotLLMBudgetExceeded,
        match="P15_CP_B0_PROVIDER_BUDGET_CAP_EXCEEDED",
    ):
        checkpoint.authorize_request(
            request_sha256="a" * 64,
            prompt_name="exam/generate_single_choice",
            profile_id="generator_main",
            estimated_input_tokens=1,
            configured_max_output_tokens=1,
        )


def test_legacy_checkpoint_recovers_billed_judgement_parse_failure(
    tmp_path: Path,
) -> None:
    checkpoint = LegacyBaselineCheckpoint(
        tmp_path / "checkpoint",
        resume=False,
        limits=ReviewBudgetLimits(
            max_cost_cny=0.45,
            max_input_tokens=100_000,
            max_output_tokens=150_000,
            max_requests=28,
        ),
        prior_usage=PriorProviderUsage(),
    )
    result = {
        "blueprint_id": "bp-1",
        "questions": [
            {
                "question_type": "judgement",
                "knowledge_point": "NeRF",
                "difficulty": "medium",
                "score": 5,
                "question_text": "NeRF is a neural radiance field.",
                "options": {"A": "正确", "B": "错误"},
                "correct_answer": "A",
                "explanation": "Supported by the source.",
                "references": [{"chunk_id": "evidence-1"}],
            }
        ],
    }
    request_sha256 = "b" * 64
    invocation = {
        "status": "failed",
        "error_category": "structured_parse_error",
        "schema": "QuestionSet",
        "request_sha256": request_sha256,
        "prompt_name": "exam/generate_judgement",
        "prompt_sha256": "c" * 64,
        "profile_id": "generator_main",
        "attempts": [
            {
                "error_message": (
                    f"Failed to parse QuestionSet from completion {json.dumps(result)}. "
                    "Got: validation error"
                ),
                "usage": {"input_tokens": 10, "output_tokens": 20},
            }
        ],
    }
    checkpoint.audit_path.write_text(json.dumps(invocation) + "\n", encoding="utf-8")

    assert checkpoint.reconcile_parseable_failures() == 1
    cached = checkpoint.load(request_sha256)
    assert cached is not None
    assert cached["result"]["questions"][0]["correct_answer"] == "正确"
    assert cached["reconciled_from_billed_parse_failure"] is True


def test_legacy_checkpoint_allows_only_monotonic_limit_revision(tmp_path: Path) -> None:
    root = tmp_path / "checkpoint"
    prior = PriorProviderUsage()
    LegacyBaselineCheckpoint(
        root,
        resume=False,
        limits=ReviewBudgetLimits(0.45, 100_000, 150_000, 28),
        prior_usage=prior,
    )
    LegacyBaselineCheckpoint(
        root,
        resume=True,
        limits=ReviewBudgetLimits(0.45, 130_000, 150_000, 30),
        prior_usage=prior,
    )

    with pytest.raises(RuntimeError, match="cannot decrease"):
        LegacyBaselineCheckpoint(
            root,
            resume=True,
            limits=ReviewBudgetLimits(0.45, 120_000, 150_000, 30),
            prior_usage=prior,
        )


def test_build_p15_blinded_review_package_has_six_exams_and_download(tmp_path: Path) -> None:
    baseline, state, report = _write_sources(tmp_path)
    output = tmp_path / "review"

    result = build_review_package(
        ROOT,
        baseline_report_path=baseline,
        p15_state_path=state,
        p15_report_path=report,
        output_dir=output,
    )

    assert result["blind_exam_count"] == 6
    assert result["review_question_count"] == 6
    page = (output / "review.html").read_text(encoding="utf-8")
    assert "校验并下载最终决策 JSON" in page
    assert "localStorage.setItem" in page
    assert "new Blob" in page
    assert "document.body.appendChild(link)" in page
    assert "link.download=filename" in page
    assert "p15_exam_review_decisions.json" in page
    assert "p15_exam_review_progress.json" in page
    assert "download-progress" in page
    assert all(key in page for key in RUBRIC)
    assert "cp_b0" not in page


def test_finalize_p15_decisions_unblinds_and_reports_quality_debt(tmp_path: Path) -> None:
    baseline, state, report = _write_sources(tmp_path)
    output = tmp_path / "review"
    build_review_package(
        ROOT,
        baseline_report_path=baseline,
        p15_state_path=state,
        p15_report_path=report,
        output_dir=output,
    )
    template = json.loads((output / "review_decisions_template.json").read_text(encoding="utf-8"))
    key = json.loads((output / "blinding_key.json").read_text(encoding="utf-8"))
    tracks = {item["blind_question_id"]: item["track"] for item in key["items"]}
    for decision in template["decisions"]:
        score = 3 if tracks[decision["blind_question_id"]] == "p15" else 4
        decision.update(
            {
                "rubric_scores": {rubric: score for rubric in RUBRIC},
                "edit_burden": 2 if score == 3 else 1,
                "critical_defect": False,
                "question_status": "minor_edit",
                "notes": "",
            }
        )
    decisions_path = output / "decisions.json"
    decisions_path.write_text(json.dumps(template), encoding="utf-8")

    result = finalize_decisions(
        package_manifest_path=output / "package_manifest.json",
        blinding_key_path=output / "blinding_key.json",
        decisions_path=decisions_path,
        output_path=output / "summary.json",
    )

    assert result["decision_count"] == 6
    assert result["track_metrics"]["cp_b0"]["overall_rubric_mean"] == 4
    assert result["track_metrics"]["p15"]["overall_rubric_mean"] == 3
    assert result["recommended_phase_status"] == "completed_with_quality_debt"


def test_finalize_p15_serious_decision_requires_note(tmp_path: Path) -> None:
    baseline, state, report = _write_sources(tmp_path)
    output = tmp_path / "review"
    build_review_package(
        ROOT,
        baseline_report_path=baseline,
        p15_state_path=state,
        p15_report_path=report,
        output_dir=output,
    )
    template = json.loads((output / "review_decisions_template.json").read_text(encoding="utf-8"))
    for decision in template["decisions"]:
        decision.update(
            {
                "rubric_scores": {rubric: 3 for rubric in RUBRIC},
                "edit_burden": 3,
                "critical_defect": False,
                "question_status": "major_edit",
                "notes": "",
            }
        )
    decisions_path = output / "decisions.json"
    decisions_path.write_text(json.dumps(template), encoding="utf-8")

    with pytest.raises(ValueError, match="require notes"):
        finalize_decisions(
            package_manifest_path=output / "package_manifest.json",
            blinding_key_path=output / "blinding_key.json",
            decisions_path=decisions_path,
            output_path=output / "summary.json",
        )
