from __future__ import annotations

import pytest

from courserag.evals.p09_metrics import (
    abstention_metrics,
    answerability_metrics,
    boundary_preservation,
    budget_compliance,
    categorical_accuracy,
    citation_resolvability,
    claim_citation_completeness,
    complete_group_coverage,
    context_gold_evidence_coverage,
    context_precision,
    duplicate_context_rate,
    evidence_id_overlap_metrics,
    list_set_f1,
    preserve_rate,
    set_precision_recall_f1,
    short_answer_exact_match,
    short_answer_token_f1,
)
from courserag.evals.schemas import EvidenceGroup


def test_context_metrics_use_complete_groups_and_necessary_tokens() -> None:
    groups = [
        EvidenceGroup(group_id="g1", sufficiency="complete", required_evidence_ids=["e1", "e2"])
    ]
    coverage = context_gold_evidence_coverage(["e1", "e2", "e3"], groups)
    precision = context_precision(
        total_tokens=100,
        relevant_evidence_tokens=60,
        necessary_neighbor_tokens=20,
    )
    duplicate = duplicate_context_rate(duplicate_tokens=10, total_tokens=100)
    assert coverage.value == 1.0
    assert precision.value == 0.8
    assert duplicate.value == 0.1
    with pytest.raises(ValueError):
        context_precision(
            total_tokens=10,
            relevant_evidence_tokens=9,
            necessary_neighbor_tokens=2,
        )


def test_short_answer_list_and_answerability_metrics() -> None:
    assert short_answer_exact_match(" AGI ", ["agi"]).value == 1.0
    assert short_answer_token_f1("通用人工智能", ["通用人工智能系统"]).value is not None
    assert list_set_f1(["A", "B"], ["b", "a"]).value == 1.0
    metrics = answerability_metrics(
        predicted_answerable=[True, True, False],
        gold_answerable=[True, False, False],
    )
    assert metrics["answerability_precision"].value == 0.5
    assert metrics["answerability_recall"].value == 1.0
    assert metrics["answerability_f1"].value == pytest.approx(2 / 3)


def test_query_context_and_citation_metrics() -> None:
    groups = [
        EvidenceGroup(group_id="g1", sufficiency="complete", required_evidence_ids=["e1", "e2"]),
        EvidenceGroup(group_id="g2", sufficiency="complete", required_evidence_ids=["e3"]),
    ]
    assert categorical_accuracy("route", ["a", "b"], ["a", "c"]).value == 0.5
    assert (
        set_precision_recall_f1("kp", predicted=["a", "b"], gold=["b", "c"])["kp_f1"].value == 0.5
    )
    assert preserve_rate(preserved=[True, False, True]).value == pytest.approx(2 / 3)
    assert complete_group_coverage(["e1", "e2"], groups).value == 0.5
    assert budget_compliance(token_count=100, max_tokens=100, item_count=8, max_items=8).value == 1
    assert boundary_preservation(complete_items=3, total_items=4).value == 0.75
    assert (
        evidence_id_overlap_metrics(predicted_evidence_ids=["e1"], gold_evidence_ids=["e1", "e2"])[
            "evidence_id_overlap_recall"
        ].value
        == 0.5
    )
    assert citation_resolvability(resolvable=[True, True]).value == 1
    assert claim_citation_completeness(claims_with_citations=2, total_claims=2).value == 1
    abstention = abstention_metrics(
        predicted_answerable=[True, False, False], gold_answerable=[True, False, True]
    )
    assert abstention["unanswerable_recall"].value == 1
    assert abstention["false_abstention_rate"].value == 0.5
