from __future__ import annotations

from evaluation.p17_3_security_tri_state import select_tri_state_candidate


def _row(index: int, *, malicious: bool) -> dict[str, object]:
    high = 0.9 if malicious else 0.1
    low = 0.1 if malicious else 0.9
    return {
        "record_id": f"case-{index:03d}",
        "label": "malicious" if malicious else "hard_negative",
        "language": "en" if index % 2 else "zh",
        "family": "policy_override" if malicious else "quoted",
        "construction_group": f"group-{index % 12}",
        "scope": "operative" if malicious else "quoted",
        "hikma_score": high,
        "attack_semantic_score": high,
        "safe_semantic_score": low,
        "structured_score": high,
        "scope_score": low,
        "attack_prototype_id": "attack",
        "safe_prototype_id": "safe",
    }


def test_tri_state_candidate_has_zero_malicious_safe_and_bounded_false_attack() -> None:
    rows = [_row(index, malicious=index < 120) for index in range(240)]

    candidate = select_tri_state_candidate(rows)

    assert candidate is not None
    assert candidate["malicious_safe"] == 0
    assert candidate["malicious_capture_recall"] == 1
    assert candidate["hard_negative_attack"] <= 3
    assert candidate["hard_negative_attack_specificity"] >= 0.975
    assert candidate["safe_boundary"] < candidate["attack_boundary"]
