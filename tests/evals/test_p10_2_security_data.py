from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.p10_2_security_approval import approve_dev_candidate
from evaluation.p10_2_security_data import (
    P102SecurityDevCandidate,
    generate_dev_candidate,
    load_approved_dev,
    sha256_file,
    write_release_skeleton,
)


def test_dev_candidate_has_preregistered_distribution() -> None:
    candidate = generate_dev_candidate()

    assert len(candidate.cases) == 160
    assert sum(case.expected_marked for case in candidate.cases) == 80
    assert sum(not case.expected_marked for case in candidate.cases) == 80
    assert {case.language for case in candidate.cases} == {"en", "zh"}
    assert any(case.construction == "cross_block" for case in candidate.cases)
    assert any(case.construction == "long_context" for case in candidate.cases)
    assert candidate.test_content_included is False


def test_release_skeleton_contains_no_blind_test_content(tmp_path: Path) -> None:
    identities = write_release_skeleton(tmp_path)
    candidate = P102SecurityDevCandidate.model_validate_json(
        (tmp_path / "dev_candidate_r1.json").read_text(encoding="utf-8")
    )
    commitment = json.loads((tmp_path / "blind_test_commitment.json").read_text())

    assert identities["dev_candidate_sha256"] == sha256_file(tmp_path / "dev_candidate_r1.json")
    assert len(candidate.cases) == 160
    assert commitment["status"] == "awaiting_independent_construction"
    assert commitment["content_visible_to_implementation"] is False
    assert "cases" not in commitment


def test_dev_loader_requires_exact_owner_approval(tmp_path: Path) -> None:
    write_release_skeleton(tmp_path)
    approval = {
        "schema_version": "courserag.p10-2-security-dev-approval.v1",
        "dataset_sha256": "0" * 64,
        "status": "approved",
        "reviewer": "course_owner",
        "approved_at": "2026-08-11T00:00:00Z",
        "approved_case_ids": [f"p10-2-sec-dev-{index:03d}" for index in range(1, 161)],
    }
    approval_path = tmp_path / "approval.json"
    approval_path.write_text(json.dumps(approval), encoding="utf-8")

    with pytest.raises(ValueError, match="exact Candidate"):
        load_approved_dev(tmp_path / "dev_candidate_r1.json", approval_path)


def test_owner_approval_writer_binds_every_case_and_exact_hash(tmp_path: Path) -> None:
    write_release_skeleton(tmp_path)
    dataset_path = tmp_path / "dev_candidate_r1.json"
    approval_path = tmp_path / "dev_approval.json"

    approve_dev_candidate(
        dataset_path=dataset_path,
        approval_path=approval_path,
        expected_sha256=sha256_file(dataset_path),
        owner_approved=True,
    )

    approved = load_approved_dev(dataset_path, approval_path)
    assert len(approved.cases) == 160
