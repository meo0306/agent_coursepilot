from __future__ import annotations

from courserag.security.dual_hypothesis import SecurityTriState
from evaluation.p17_3_security_data import build_qualification_candidate
from evaluation.p17_3_security_qualification import (
    qualification_metrics,
    qualification_passed,
)


def _dataset():
    return build_qualification_candidate(
        profile_file_sha256="a" * 64,
        selection_report_sha256="b" * 64,
        prior_text_hashes=set(),
    )


def test_tri_state_qualification_passes_zero_safe_malicious_and_one_false_attack() -> None:
    dataset = _dataset()
    decisions: dict[str, SecurityTriState] = {}
    negative_seen = 0
    for case in dataset.cases:
        if case.label == "malicious":
            decisions[case.record_id] = "attack" if int(case.record_id[-3:]) % 2 else "needs_review"
        else:
            negative_seen += 1
            decisions[case.record_id] = "attack" if negative_seen == 1 else "safe"

    metrics = qualification_metrics(dataset, decisions)

    assert metrics["malicious_safe"] == 0
    assert metrics["malicious_capture_recall"] == 1
    assert metrics["hard_negative_attack_specificity"] >= 0.975
    assert qualification_passed(metrics) is True


def test_tri_state_qualification_fails_when_one_malicious_is_safe() -> None:
    dataset = _dataset()
    decisions: dict[str, SecurityTriState] = {
        case.record_id: "attack" if case.label == "malicious" else "safe" for case in dataset.cases
    }
    malicious = next(case for case in dataset.cases if case.label == "malicious")
    decisions[malicious.record_id] = "safe"

    assert qualification_passed(qualification_metrics(dataset, decisions)) is False


def test_tri_state_qualification_fails_when_false_attacks_exceed_specificity() -> None:
    dataset = _dataset()
    decisions: dict[str, SecurityTriState] = {
        case.record_id: "attack" if case.label == "malicious" else "safe" for case in dataset.cases
    }
    negatives = [case for case in dataset.cases if case.label == "hard_negative"]
    decisions[negatives[0].record_id] = "attack"
    decisions[negatives[1].record_id] = "attack"

    assert qualification_passed(qualification_metrics(dataset, decisions)) is False
