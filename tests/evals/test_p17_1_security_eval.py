from __future__ import annotations

from courserag.security.dual_hypothesis import DualHypothesisWindowScore
from evaluation.p17_1_security_data import build_calibration_candidate
from evaluation.p17_1_security_eval import (
    select_calibration_candidates,
    select_diagnostic_repair_candidates,
)


def _score(case_id: str, attack: float, safe: float) -> DualHypothesisWindowScore:
    return DualHypothesisWindowScore(
        window_id=f"secwin_{case_id[-3:] * 8}",
        attack_score=attack,
        safe_scope_score=safe,
        decision_margin=attack - safe,
        marked=False,
        scope="operative",
        hikma_score=attack,
        attack_semantic_score=attack,
        safe_semantic_score=safe,
        structured_score=0,
        scope_score=0,
        attack_prototype_id="attack",
        safe_prototype_id="safe",
    )


def test_calibration_selects_high_recall_candidate_under_specificity_constraint() -> None:
    dataset = build_calibration_candidate()
    rows = tuple(
        (
            case,
            _score(
                case.record_id,
                0.9 if case.label == "malicious" else 0.2,
                0.1 if case.label == "malicious" else 0.8,
            ),
        )
        for case in dataset.cases
    )
    finalists = select_calibration_candidates(rows, limit=2)
    assert len(finalists) == 2
    assert finalists[0]["recall"] == 1
    assert finalists[0]["specificity"] == 1
    assert finalists[0]["minimum_group_recall"] == 1


def test_calibration_returns_no_candidate_when_specificity_is_impossible() -> None:
    dataset = build_calibration_candidate()
    rows = tuple((case, _score(case.record_id, 0.9, 0.0)) for case in dataset.cases)
    assert select_calibration_candidates(rows, limit=2) == []


def test_diagnostic_repair_selects_one_recall_safe_candidate() -> None:
    dataset = build_calibration_candidate()
    rows = tuple(
        (
            case,
            _score(
                case.record_id,
                0.92 if case.label == "malicious" else 0.15,
                0.08 if case.label == "malicious" else 0.9,
            ),
        )
        for case in dataset.cases
    )

    finalists, frontier = select_diagnostic_repair_candidates(rows, limit=1)

    assert len(finalists) == 1
    assert finalists[0]["recall"] == 1
    assert finalists[0]["minimum_group_recall"] == 1
    assert finalists[0]["specificity"] == 1
    assert finalists[0]["false_positive_ids"] == []
    assert len(frontier) == 10
