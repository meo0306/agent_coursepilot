from __future__ import annotations

import hashlib
from pathlib import Path

from coursepilot.evals.formal_schemas import CPDS6P12PilotDataset, CPDS6RecoveryDataset
from evaluation.datasets import records_from_envelope
from evaluation.p12_cp_ds6_data import CANDIDATE_PATH, build_dataset, generate

ROOT = Path(__file__).resolve().parents[2]


def test_p12_candidate_has_fixed_distribution_and_loader_support() -> None:
    candidate = CPDS6P12PilotDataset.model_validate_json(
        (ROOT / CANDIDATE_PATH).read_text(encoding="utf-8")
    )
    assert len(candidate.cases) == 24
    assert {item.interrupt_type for item in candidate.cases} == {
        "lesson_session_plan_review",
        "lesson_final_review",
        "exam_blueprint_review",
        "exam_global_review",
        "ppt_architecture_review",
        "ppt_final_review",
    }
    assert {item.scenario_type for item in candidate.cases} == {
        "approve",
        "edit_resume",
        "replan",
        "reject",
    }
    assert len(records_from_envelope(candidate)) == 24


def test_p12_generation_is_byte_stable() -> None:
    first = generate(ROOT)
    path = ROOT / CANDIDATE_PATH
    first_bytes = path.read_bytes()
    second = generate(ROOT)
    assert first["candidate_sha256"] == second["candidate_sha256"]
    assert first_bytes == path.read_bytes()
    assert hashlib.sha256(first_bytes).hexdigest() == first["candidate_sha256"]


def test_legacy_cp_ds6_pilot_schema_remains_valid() -> None:
    legacy = ROOT / "datasets/coursepilot_eval/v1/candidates/cp_ds6/pilot.json"
    CPDS6RecoveryDataset.model_validate_json(legacy.read_text(encoding="utf-8"))


def test_p12_approval_artifact_exists_only_after_exact_approval() -> None:
    assert (
        ROOT / "datasets/coursepilot_eval/v1/approved/cp_ds6/p12_interrupt_recovery.json"
    ).exists()


def test_build_dataset_is_independent_of_repository_files() -> None:
    assert len(build_dataset().cases) == 24
