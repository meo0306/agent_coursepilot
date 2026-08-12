from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from courserag.security.detector import SecurityAxisSignal, SecurityTextWindow
from courserag.security.ensemble import (
    MultiAxisSecurityEnsemble,
    MultiAxisSecurityProfile,
    SecurityAxisProfile,
)
from courserag.security.windowing import SecurityWindowBuilder
from evaluation.io import atomic_write_json
from evaluation.p10_3_multi_axis_dev import _validate_protocol
from evaluation.p10_3_security_data import (
    P103DevApproval,
    generate_dev_candidate,
    sha256_file,
)
from evaluation.p10_3_security_eval import run_qualification_dev


class CharacterTokenizer:
    tokenizer_id = "character-v1"

    def offsets(self, text: str) -> tuple[tuple[int, int], ...]:
        return tuple((index, index + 1) for index in range(len(text)))


class LabelFakeAxis:
    detector_id = "test/label-axis"

    def __init__(self, positive_record_ids: frozenset[str]) -> None:
        self.positive_record_ids = positive_record_ids

    def validate_environment(self) -> None:
        return None

    def detect(self, windows: tuple[SecurityTextWindow, ...]) -> tuple[SecurityAxisSignal, ...]:
        output = []
        for window in windows:
            record_id = window.segments[0].block_id.removesuffix("-block-1")
            output.append(
                SecurityAxisSignal(
                    signal_id="secsig_" + window.window_id.removeprefix("secwin_"),
                    window_id=window.window_id,
                    axis_id="general_untrusted_instruction",
                    score=1 if record_id in self.positive_record_ids else 0,
                    detector_id=self.detector_id,
                    decision_ready=record_id in self.positive_record_ids,
                )
            )
        return tuple(output)


def _inputs(tmp_path: Path):
    dataset = generate_dev_candidate()
    dataset_path = tmp_path / "dataset.json"
    approval_path = tmp_path / "approval.json"
    atomic_write_json(dataset_path, dataset.model_dump(mode="json"))
    atomic_write_json(
        approval_path,
        P103DevApproval(
            dataset_sha256=sha256_file(dataset_path),
            first_review_sha256="1" * 64,
            second_review_sha256="2" * 64,
            status="approved",
            reviewer="course_owner",
            approved_at=datetime.now(UTC),
            approved_case_ids=tuple(case.record_id for case in dataset.cases),
        ).model_dump(mode="json"),
    )
    profile = MultiAxisSecurityProfile(
        name="test",
        version="1",
        axes=(
            SecurityAxisProfile(
                axis_id="general_untrusted_instruction",
                detector_id=LabelFakeAxis.detector_id,
                decision_threshold=0.5,
            ),
            SecurityAxisProfile(
                axis_id="role_impersonation", detector_id=LabelFakeAxis.detector_id
            ),
            SecurityAxisProfile(axis_id="secret_extraction", detector_id=LabelFakeAxis.detector_id),
            SecurityAxisProfile(axis_id="tool_coercion", detector_id=LabelFakeAxis.detector_id),
            SecurityAxisProfile(
                axis_id="obfuscation_modifier", detector_id=LabelFakeAxis.detector_id
            ),
        ),
        hikma_manifest_sha256="3" * 64,
        structured_profile_sha256="4" * 64,
    )
    positive_ids = frozenset(case.record_id for case in dataset.cases if case.expected_marked)
    ensemble = MultiAxisSecurityEnsemble(profile, (LabelFakeAxis(positive_ids),))
    return dataset_path, approval_path, ensemble


def test_qualification_runner_emits_candidate_without_blind_access(tmp_path: Path) -> None:
    dataset_path, approval_path, ensemble = _inputs(tmp_path)
    report_path, candidate_path = run_qualification_dev(
        dataset_path=dataset_path,
        approval_path=approval_path,
        ensemble=ensemble,
        window_builder=SecurityWindowBuilder(CharacterTokenizer()),
        output_path=tmp_path / "report.json",
        candidate_profile_path=tmp_path / "profile.json",
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert candidate_path is not None
    assert report["status"] == "passed"
    assert report["metrics"]["recall"] == 1
    assert report["metrics"]["specificity"] == 1
    assert report["blind_access"] is False
    assert report["test_access"] is False
    assert report["external_provider_calls"] == 0
    assert report["fallbacks"] == 0


def test_qualification_runner_refuses_overwrite(tmp_path: Path) -> None:
    dataset_path, approval_path, ensemble = _inputs(tmp_path)
    output = tmp_path / "report.json"
    output.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="refusing rerun/overwrite"):
        run_qualification_dev(
            dataset_path=dataset_path,
            approval_path=approval_path,
            ensemble=ensemble,
            window_builder=SecurityWindowBuilder(CharacterTokenizer()),
            output_path=output,
            candidate_profile_path=tmp_path / "profile.json",
        )


def test_repository_qualification_protocol_binds_exact_inputs() -> None:
    protocol_path = Path(
        "resources/security_profiles/p10_3_qualification_protocol_candidate_v1.json"
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    _validate_protocol(
        protocol,
        dataset=Path(protocol["dataset_path"]),
        profile=Path(protocol["profile_path"]),
        approval=Path(protocol["approval_path"]),
    )
