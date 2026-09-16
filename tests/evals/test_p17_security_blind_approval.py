from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.p17_security_blind_approval import validate_and_build
from evaluation.p17_security_blind_data import build


def _write(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _reviewed_package(tmp_path: Path) -> Path:
    root = tmp_path / "blind"
    build(root)
    candidate = json.loads((root / "blind_candidate_r1.json").read_text(encoding="utf-8"))
    first = json.loads((root / "blind_first_review_r1.json").read_text(encoding="utf-8"))
    second = json.loads((root / "blind_second_review_r1.json").read_text(encoding="utf-8"))
    first["reviewed_at"] = "2026-08-22T20:00:00+08:00"
    second["reviewed_at"] = "2026-08-22T19:00:00+08:00"
    for record in first["records"]:
        record["decision"] = "pass"
    by_id = {case["record_id"]: case for case in candidate["cases"]}
    for record in second["records"]:
        case = by_id[record["record_id"]]
        record["decision_label"] = case["label"]
        record["decision_family"] = case["family"]
    _write(root / "blind_first_review_decisions_r1.json", first)
    _write(root / "blind_second_review_decisions_r1.json", second)
    return root


def test_two_complete_matching_reviews_produce_pending_approval(tmp_path: Path) -> None:
    result = validate_and_build(_reviewed_package(tmp_path))
    assert result["approval_status"] == "pending_course_owner_exact_sha256"
    assert result["record_count"] == 48
    assert result["first_review_pass_count"] == 48
    assert result["second_review_match_count"] == 48
    assert result["blind_runs_completed"] == 0
    assert result["external_provider_calls_allowed"] == 0


def test_second_review_disagreement_fails_closed(tmp_path: Path) -> None:
    root = _reviewed_package(tmp_path)
    second_path = root / "blind_second_review_decisions_r1.json"
    second = json.loads(second_path.read_text(encoding="utf-8"))
    second["records"][0]["decision_label"] = "benign"
    second["records"][0]["decision_family"] = "hard_negative"
    _write(second_path, second)
    with pytest.raises(ValueError, match="second review disagrees"):
        validate_and_build(root)
