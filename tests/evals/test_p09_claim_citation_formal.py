import json
from pathlib import Path

import pytest

from courserag.evals.schemas import P09ClaimCitationPhase2Approval
from evaluation.p09_claim_citation_formal import (
    PHASE2_DECISIONS_SHA256,
    _require_hash,
    write_formal_claim_citation_report,
)

ROOT = Path(__file__).resolve().parents[2]


def test_formal_claim_citation_report_is_reproducible_and_fail_closed(
    tmp_path: Path,
) -> None:
    first = write_formal_claim_citation_report(ROOT, tmp_path / "first")
    second = write_formal_claim_citation_report(ROOT, tmp_path / "second")
    report = json.loads(Path(first["formal_report"]).read_text(encoding="utf-8"))
    approval = P09ClaimCitationPhase2Approval.model_validate_json(
        Path(first["phase2_approval"]).read_text(encoding="utf-8")
    )
    metrics = {name: value["value"] for name, value in report["formal_metrics"].items()}

    assert approval.decisions_sha256 == PHASE2_DECISIONS_SHA256
    assert approval.reviewer_id == "course_owner"
    assert report["test_access"] is False
    assert report["provider_calls"] == {"cohere": 0, "deepseek": 0, "other": 0}
    assert report["status"] == "failed"
    assert report["freeze_eligible"] is False
    assert report["freeze_candidate"] is None
    assert report["failed_checks"] == ["qa_failure_rate_0", "short_answer_token_f1_q2_delta"]
    assert metrics["gold_claim_coverage"] == pytest.approx(99 / 117)
    assert metrics["correct_claim_precision"] == pytest.approx(144 / 150)
    assert metrics["unsupported_claim_rate"] == pytest.approx(6 / 150)
    assert metrics["citation_precision"] == pytest.approx(144 / 150)
    assert metrics["citation_recall"] == pytest.approx(94 / 117)
    assert report["citation_f1"] == pytest.approx(0.8747576580069795)
    assert metrics["answerability_precision"] == 1
    assert metrics["answerability_recall"] == pytest.approx(47 / 48)
    assert report["answer_conciseness_pass_rate"] == pytest.approx(45 / 47)
    assert report["corrected_automatic_metrics"]["q2"]["short_answer_case_count"] == 9
    assert report["corrected_automatic_metrics"]["q3"]["list_case_count"] == 2
    for key in (
        "phase2_approval_sha256",
        "formal_report_sha256",
        "formal_manifest_sha256",
    ):
        assert first[key] == second[key]


def test_formal_report_rejects_a_changed_fixed_input(tmp_path: Path) -> None:
    value = tmp_path / "changed.json"
    value.write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Hash mismatch"):
        _require_hash(value, "0" * 64)
