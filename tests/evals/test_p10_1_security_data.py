from __future__ import annotations

import json
from pathlib import Path

from courserag.security import load_prompt_injection_profile
from evaluation.p10_1_security_data import (
    load_blind_commitment,
    load_dev_dataset,
    run_dev_gate,
)

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / "datasets/courserag_eval/releases/p10_1_security"


def test_dev_dataset_is_exactly_30_and_has_no_test_content() -> None:
    dataset = load_dev_dataset(RELEASE / "candidate_dev_r1.json")
    assert len(dataset.cases) == 30
    assert sum(case.expected_marked for case in dataset.cases) == 20
    assert all(case.split == "dev" for case in dataset.cases)
    assert dataset.test_content_included is False


def test_blind_commitment_is_consumed_and_exactly_bound() -> None:
    commitment = load_blind_commitment(RELEASE / "blind_test_commitment.json")
    assert commitment.status == "consumed"
    assert (
        commitment.bundle_sha256
        == "7394dfd462993c54e0b262d63c276e097c83eb2f32c99574472c81fdac0a62ee"
    )
    assert (
        commitment.approved_manifest_sha256
        == "ffe8f58220cf3b1b821d25e25a681a34cef039d8cf20d8ab87c929c5cb71401e"
    )
    assert commitment.locked_by == "course_owner"
    assert commitment.content_visible_to_implementation is False


def test_candidate_profile_passes_dev_gate_without_test_or_provider(tmp_path: Path) -> None:
    output = tmp_path / "dev_report.json"
    run_dev_gate(
        dataset_path=RELEASE / "candidate_dev_r1.json",
        profile=load_prompt_injection_profile(
            ROOT / "resources/security_profiles/prompt_injection_candidate_v2.json"
        ),
        output_path=output,
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "passed"
    assert report["metrics"]["positive_recall"] == 1.0
    assert report["metrics"]["hard_negative_false_positive_rate"] <= 0.10
    assert report["test_access"] is False
    assert report["provider_calls"] == 0
