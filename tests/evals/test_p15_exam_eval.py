from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from coursepilot.llm import CoursePilotLLMBudgetExceeded
from evaluation.p15_exam_eval import (
    P15ResponseCheckpoint,
    _evidence_payload,
    build_blueprint,
    run_real,
)


def test_p15_response_checkpoint_is_atomic_and_resumable(tmp_path: Path) -> None:
    checkpoint = P15ResponseCheckpoint(tmp_path / "checkpoint", resume=False)
    checkpoint.save("a" * 64, {"request_sha256": "a" * 64, "result": {"ok": True}})
    checkpoint.record_invocation({"request_sha256": "a" * 64, "status": "success"})

    resumed = P15ResponseCheckpoint(tmp_path / "checkpoint", resume=True)
    assert resumed.load("a" * 64)["result"] == {"ok": True}
    assert not list((tmp_path / "checkpoint").rglob("*.tmp"))


def test_p15_budget_reservation_is_durable_and_released_by_audit(tmp_path: Path) -> None:
    checkpoint = P15ResponseCheckpoint(tmp_path / "checkpoint", resume=False)
    request_hash = "b" * 64
    checkpoint.authorize_request(
        request_sha256=request_hash,
        prompt_name="exam/p15_generate_batch",
        profile_id="generator_main",
        estimated_input_tokens=100,
        configured_max_output_tokens=200,
    )
    with pytest.raises(
        CoursePilotLLMBudgetExceeded,
        match="P15_AMBIGUOUS_REQUEST_PENDING_RECONCILIATION",
    ):
        P15ResponseCheckpoint(tmp_path / "checkpoint", resume=True).authorize_request(
            request_sha256=request_hash,
            prompt_name="exam/p15_generate_batch",
            profile_id="generator_main",
            estimated_input_tokens=100,
            configured_max_output_tokens=200,
        )

    checkpoint.record_invocation(
        {
            "request_sha256": request_hash,
            "status": "success",
            "provider_called": True,
            "usage": {"input_tokens": 90, "output_tokens": 150},
        }
    )
    assert checkpoint.provider_usage_totals() == (90, 150, 1)
    state = json.loads(checkpoint.state_path.read_text(encoding="utf-8"))
    assert state["budget_reservations"] == {}


def test_p15_usage_audit_excludes_requests_confirmed_not_sent(tmp_path: Path) -> None:
    checkpoint = P15ResponseCheckpoint(tmp_path / "checkpoint", resume=False)
    checkpoint.record_invocation(
        {
            "request_sha256": "c" * 64,
            "status": "failed",
            "provider_called": True,
            "attempts": [
                {
                    "status": "failed",
                    "billing_status": "not_sent",
                    "usage": {"input_tokens": 900, "output_tokens": 0},
                },
                {
                    "status": "failed",
                    "billing_status": "unknown_pending_reconciliation",
                    "usage": {"input_tokens": 800, "output_tokens": 20},
                },
            ],
        }
    )

    assert checkpoint.provider_usage_totals() == (800, 20, 1)


def test_p15_payload_contains_bounded_evidence_text() -> None:
    root = Path.cwd()
    raw = json.loads(
        (root / "datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    targets = {item["target_id"]: item for item in raw["targets"]}
    blueprint = build_blueprint(raw["cases"][0], targets)
    evidence = _evidence_payload(blueprint, blueprint.batches[0], targets)
    assert evidence
    assert evidence[0]["evidence"]["text"]
    assert "full_document" not in evidence[0]


def test_p15_real_runner_offline_fake_provider_executes_variant_matrix(
    tmp_path: Path, monkeypatch
) -> None:
    import coursepilot.llm

    def fake_generate(
        *,
        prompt_name: str,
        output_schema: type[BaseModel],
        payload: dict,
        fallback,
        profile_id: str,
        allow_fallback: bool,
    ) -> BaseModel:
        if output_schema.__name__ == "PlannerAcknowledgement":
            return output_schema(acknowledgement="approved")
        rows = []
        for slot in payload["slots"]:
            marker = hashlib.sha256(f"stem:{slot['slot_id']}".encode()).hexdigest()
            answer_marker = hashlib.sha256(f"answer:{slot['slot_id']}".encode()).hexdigest()
            is_multiple = slot["question_type"] == "multiple_choice"
            is_choice = slot["question_type"] in {"single_choice", "multiple_choice"}
            options = (
                {"A": answer_marker, "B": answer_marker[::-1], "C": answer_marker[::2]}
                if is_choice
                else {}
            )
            rows.append(
                {
                    "slot_id": slot["slot_id"],
                    "stem": "Question " + marker,
                    "options": options,
                    "option_assessments": {
                        key: {
                            "is_correct": key == "A" or (is_multiple and key == "B"),
                            "rationale": "Bounded evidence classification.",
                            "evidence_ids": slot["evidence_ids"],
                        }
                        for key in options
                    },
                    "answer": "A,B" if is_multiple else "A" if is_choice else answer_marker,
                    "explanation": "The bounded evidence supports the answer.",
                }
            )
        return output_schema(questions=rows)

    monkeypatch.setattr(coursepilot.llm, "generate_structured", fake_generate)
    report = run_real(
        Path.cwd(),
        output_dir=tmp_path / "p3",
        experiment="p3",
        resume=False,
    )
    assert report["logical_requests"] == 17
    assert report["provider_requests"] == 0
    assert all(case["global_report"]["citation_resolvable"] for case in report["cases"])
    assert (tmp_path / "p3" / "checkpoint" / "state.json").exists()

    pressure_case = "p15-exam-03-llm-midterm"
    expected = {"p0": 5, "p1": 5, "p2": 5}
    for experiment, request_count in expected.items():
        variant = run_real(
            Path.cwd(),
            output_dir=tmp_path / experiment,
            experiment=experiment,
            case_ids={pressure_case},
            include_planner=False,
            resume=False,
        )
        assert variant["logical_requests"] == request_count
        assert variant["provider_requests"] == 0
        assert variant["cases"][0]["global_report"]["citation_resolvable"] is True


def test_p15_p3_executes_bounded_global_repair(tmp_path: Path, monkeypatch) -> None:
    import coursepilot.llm

    raw = json.loads(
        Path("datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    targets = {item["target_id"]: item for item in raw["targets"]}
    blueprint = build_blueprint(raw["cases"][0], targets)
    duplicate_slots = {blueprint.slots[0].slot_id, blueprint.slots[1].slot_id}

    def fake_generate(**kwargs) -> BaseModel:
        schema = kwargs["output_schema"]
        payload = kwargs["payload"]
        if schema.__name__ == "PlannerAcknowledgement":
            return schema(acknowledgement="approved")
        repairing = kwargs["prompt_name"] == "exam/p15_repair_question"
        rows = []
        for slot in payload["slots"]:
            marker = hashlib.sha256(f"stem:{slot['slot_id']}".encode()).hexdigest()
            answer_marker = hashlib.sha256(f"answer:{slot['slot_id']}".encode()).hexdigest()
            is_multiple = slot["question_type"] == "multiple_choice"
            is_choice = slot["question_type"] in {"single_choice", "multiple_choice"}
            options = (
                {
                    "A": answer_marker,
                    "B": answer_marker[::-1],
                    "C": answer_marker[::2],
                }
                if is_choice
                else {}
            )
            stem = (
                f"Repaired independent scenario {marker}"
                if repairing
                else "Same duplicated stem"
                if slot["slot_id"] in duplicate_slots
                else f"Independent scenario {marker}"
            )
            rows.append(
                {
                    "slot_id": slot["slot_id"],
                    "stem": stem,
                    "options": options,
                    "option_assessments": {
                        key: {
                            "is_correct": key == "A" or (is_multiple and key == "B"),
                            "rationale": f"Evidence classification {marker}",
                            "evidence_ids": slot["evidence_ids"],
                        }
                        for key in options
                    },
                    "answer": "A,B" if is_multiple else "A" if is_choice else answer_marker,
                    "explanation": f"Evidence explanation {marker}",
                }
            )
        return schema(questions=rows)

    monkeypatch.setattr(coursepilot.llm, "generate_structured", fake_generate)
    report = run_real(
        Path.cwd(),
        output_dir=tmp_path / "repair",
        experiment="p3",
        case_ids={raw["cases"][0]["record_id"]},
        include_planner=False,
    )
    result = report["cases"][0]
    assert result["status"] == "completed"
    assert result["repair_events"]
    assert len(result["repair_events"]) <= 4
    assert result["global_report"]["errors"] == []


def test_p15_runner_records_batch_failure_without_aborting_case(
    tmp_path: Path, monkeypatch
) -> None:
    import coursepilot.llm

    raw = json.loads(
        Path("datasets/coursepilot_eval/v1/approved/cp_ds2/p15_exam_pilot.json").read_text(
            encoding="utf-8"
        )
    )
    targets = {item["target_id"]: item for item in raw["targets"]}
    blueprint = build_blueprint(raw["cases"][0], targets)
    failed_slot = blueprint.batches[0].slot_ids[0]

    def fake_generate(**kwargs) -> BaseModel:
        schema = kwargs["output_schema"]
        payload = kwargs["payload"]
        if any(slot["slot_id"] == failed_slot for slot in payload["slots"]):
            raise ValueError("provider returned null")
        rows = []
        for slot in payload["slots"]:
            marker = hashlib.sha256(slot["slot_id"].encode()).hexdigest()
            rows.append(
                {
                    "slot_id": slot["slot_id"],
                    "stem": f"Independent scenario {marker}",
                    "options": {"A": f"supported-{marker}", "B": f"unsupported-{marker}"},
                    "answer": "A",
                    "explanation": f"Evidence explanation {marker}",
                }
            )
        return schema(questions=rows)

    monkeypatch.setattr(coursepilot.llm, "generate_structured", fake_generate)
    report = run_real(
        Path.cwd(),
        output_dir=tmp_path / "failure",
        experiment="p3",
        case_ids={raw["cases"][0]["record_id"]},
        include_planner=False,
    )
    result = report["cases"][0]
    assert result["status"] == "needs_review"
    assert result["batch_failures"]
    assert result["global_report"]["question_count_valid"] is False
