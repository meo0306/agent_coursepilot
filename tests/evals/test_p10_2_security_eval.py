from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from courserag.security.detector import DetectorScore, SecurityTextWindow
from courserag.security.prompt_injection import load_prompt_injection_profile
from courserag.security.windowing import SecurityWindowBuilder
from evaluation.io import atomic_write_json
from evaluation.p10_2_security_data import generate_dev_candidate, sha256_file
from evaluation.p10_2_security_eval import _document, run_dev_threshold_grid


class CharacterTokenizer:
    tokenizer_id = "character-v1"

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))


class LabelBoundFakeDetector:
    detector_id = "fake-prompt-guard"

    def __init__(self, attack_window_ids: frozenset[str]) -> None:
        self.attack_window_ids = attack_window_ids

    def validate_environment(self) -> None:
        return None

    def score(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[DetectorScore, ...]:
        return tuple(
            DetectorScore(
                window_id=window.window_id,
                attack_score=(0.95 if window.window_id in self.attack_window_ids else 0.05),
                detector_id=self.detector_id,
                model_revision="fake-v1",
            )
            for window in windows
        )


def test_approved_dev_grid_selects_one_candidate_without_test_access(tmp_path: Path) -> None:
    candidate = generate_dev_candidate()
    dataset_path = tmp_path / "candidate.json"
    atomic_write_json(dataset_path, candidate.model_dump(mode="json"))
    approval_path = tmp_path / "approval.json"
    atomic_write_json(
        approval_path,
        {
            "schema_version": "courserag.p10-2-security-dev-approval.v1",
            "dataset_sha256": sha256_file(dataset_path),
            "status": "approved",
            "reviewer": "course_owner",
            "approved_at": datetime.now(UTC).isoformat(),
            "approved_case_ids": [case.record_id for case in candidate.cases],
        },
    )
    builder = SecurityWindowBuilder(CharacterTokenizer())
    attack_window_ids = frozenset(
        window.window_id
        for case in candidate.cases
        if case.expected_marked
        for window in builder.build(_document(case.record_id, case.blocks))
    )
    output = tmp_path / "report.json"
    profile = tmp_path / "candidate_profile.json"
    report_path, candidate_path = run_dev_threshold_grid(
        dataset_path=dataset_path,
        approval_path=approval_path,
        detector=LabelBoundFakeDetector(attack_window_ids),
        window_builder=builder,
        auxiliary_rules=load_prompt_injection_profile(
            "resources/security_profiles/prompt_injection_candidate_v2.json"
        ),
        model_manifest_sha256="a" * 64,
        output_path=output,
        candidate_profile_path=profile,
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert candidate_path == profile
    assert report["status"] == "passed"
    assert report["test_access"] is False
    assert report["external_provider_calls"] == 0
    assert report["fallbacks"] == 0
    assert len(report["threshold_grid"]) == 6
