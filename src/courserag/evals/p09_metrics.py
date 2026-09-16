"""Deterministic Context and QA metrics for the frozen P09 evaluation protocol."""

from __future__ import annotations

import unicodedata
from collections import Counter

from courserag.evals.schemas import EvidenceGroup
from evaluation.contracts import MetricResult


def categorical_accuracy(name: str, predictions: list[str], gold: list[str]) -> MetricResult:
    if len(predictions) != len(gold):
        raise ValueError("predictions and Gold labels must have equal length")
    return MetricResult.ratio(
        name, sum(left == right for left, right in zip(predictions, gold, strict=True)), len(gold)
    )


def set_precision_recall_f1(
    name: str, *, predicted: list[str], gold: list[str]
) -> dict[str, MetricResult]:
    predicted_set = set(predicted)
    gold_set = set(gold)
    overlap = len(predicted_set & gold_set)
    precision = overlap / len(predicted_set) if predicted_set else 0.0
    recall = overlap / len(gold_set) if gold_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        f"{name}_precision": MetricResult.ratio(f"{name}_precision", overlap, len(predicted_set)),
        f"{name}_recall": MetricResult.ratio(f"{name}_recall", overlap, len(gold_set)),
        f"{name}_f1": MetricResult(
            name=f"{name}_f1", value=f1, numerator=f1, denominator=1, applicable=True
        ),
    }


def preserve_rate(*, preserved: list[bool], name: str = "preserve_rate") -> MetricResult:
    return MetricResult.ratio(name, sum(preserved), len(preserved))


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def context_gold_evidence_coverage(
    selected_evidence_ids: list[str], groups: list[EvidenceGroup]
) -> MetricResult:
    gold = {
        evidence_id
        for group in groups
        if group.sufficiency == "complete"
        for evidence_id in group.required_evidence_ids
    }
    covered = gold.intersection(selected_evidence_ids)
    return MetricResult.ratio(
        "context_gold_evidence_coverage",
        len(covered),
        len(gold),
    )


def complete_group_coverage(
    selected_evidence_ids: list[str], groups: list[EvidenceGroup]
) -> MetricResult:
    selected = set(selected_evidence_ids)
    complete = [group for group in groups if group.sufficiency == "complete"]
    covered = sum(set(group.required_evidence_ids).issubset(selected) for group in complete)
    return MetricResult.ratio("complete_group_coverage", covered, len(complete))


def budget_compliance(
    *, token_count: int, max_tokens: int, item_count: int, max_items: int
) -> MetricResult:
    if min(token_count, max_tokens, item_count, max_items) < 0 or max_tokens == 0 or max_items == 0:
        raise ValueError("Context budgets must be positive and counts non-negative")
    passed = token_count <= max_tokens and item_count <= max_items
    return MetricResult.ratio("budget_compliance", int(passed), 1)


def boundary_preservation(*, complete_items: int, total_items: int) -> MetricResult:
    if complete_items < 0 or total_items < 0 or complete_items > total_items:
        raise ValueError("complete Context items must be between zero and total")
    return MetricResult.ratio("boundary_preservation", complete_items, total_items)


def context_precision(
    *,
    total_tokens: int,
    relevant_evidence_tokens: int,
    necessary_neighbor_tokens: int,
) -> MetricResult:
    if min(total_tokens, relevant_evidence_tokens, necessary_neighbor_tokens) < 0:
        raise ValueError("Context token counts cannot be negative")
    relevant = relevant_evidence_tokens + necessary_neighbor_tokens
    if relevant > total_tokens:
        raise ValueError("relevant and necessary Context tokens cannot exceed total tokens")
    return MetricResult.ratio("context_precision", relevant, total_tokens)


def duplicate_context_rate(*, duplicate_tokens: int, total_tokens: int) -> MetricResult:
    if min(duplicate_tokens, total_tokens) < 0 or duplicate_tokens > total_tokens:
        raise ValueError("duplicate Context tokens must be between zero and total tokens")
    return MetricResult.ratio("duplicate_context_rate", duplicate_tokens, total_tokens)


def short_answer_exact_match(prediction: str, gold_answers: list[str]) -> MetricResult:
    if not gold_answers:
        return MetricResult.ratio("short_answer_exact_match", 0, 0)
    prediction_normalized = _normalize(prediction)
    matched = any(prediction_normalized == _normalize(item) for item in gold_answers)
    return MetricResult.ratio("short_answer_exact_match", int(matched), 1)


def short_answer_token_f1(prediction: str, gold_answers: list[str]) -> MetricResult:
    if not gold_answers:
        return MetricResult.ratio("short_answer_token_f1", 0, 0)
    prediction_tokens = Counter(
        character for character in _normalize(prediction) if not character.isspace()
    )
    if not prediction_tokens:
        return MetricResult.ratio("short_answer_token_f1", 0, 1)
    best = 0.0
    for answer in gold_answers:
        gold_tokens = Counter(
            character for character in _normalize(answer) if not character.isspace()
        )
        overlap = sum((prediction_tokens & gold_tokens).values())
        precision = overlap / sum(prediction_tokens.values())
        recall = overlap / sum(gold_tokens.values()) if gold_tokens else 0.0
        score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        best = max(best, score)
    return MetricResult(
        name="short_answer_token_f1",
        value=best,
        numerator=best,
        denominator=1,
        applicable=True,
    )


def list_set_f1(predicted_items: list[str], gold_items: list[str]) -> MetricResult:
    if not gold_items:
        return MetricResult.ratio("list_set_f1", 0, 0)
    predicted = {_normalize(item) for item in predicted_items}
    gold = {_normalize(item) for item in gold_items}
    overlap = len(predicted.intersection(gold))
    precision = overlap / len(predicted) if predicted else 0.0
    recall = overlap / len(gold)
    score = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return MetricResult(
        name="list_set_f1",
        value=score,
        numerator=score,
        denominator=1,
        applicable=True,
    )


def answerability_metrics(
    *, predicted_answerable: list[bool], gold_answerable: list[bool]
) -> dict[str, MetricResult]:
    if len(predicted_answerable) != len(gold_answerable):
        raise ValueError("answerability predictions and Gold labels must have equal length")
    true_positive = sum(
        predicted and gold
        for predicted, gold in zip(predicted_answerable, gold_answerable, strict=True)
    )
    predicted_positive = sum(predicted_answerable)
    actual_positive = sum(gold_answerable)
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = true_positive / actual_positive if actual_positive else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "answerability_precision": MetricResult.ratio(
            "answerability_precision", true_positive, predicted_positive
        ),
        "answerability_recall": MetricResult.ratio(
            "answerability_recall", true_positive, actual_positive
        ),
        "answerability_f1": MetricResult(
            name="answerability_f1",
            value=f1,
            numerator=f1,
            denominator=1 if gold_answerable else 0,
            applicable=bool(gold_answerable),
        ),
    }


def evidence_id_overlap_metrics(
    *, predicted_evidence_ids: list[str], gold_evidence_ids: list[str]
) -> dict[str, MetricResult]:
    """Diagnostic ID overlap; this is not Claim-level Citation quality.

    Frozen Citation Precision/Recall requires a human judgement for every
    Claim-Citation link.  Keeping the Evidence identity proxy under a distinct
    metric namespace prevents it from being used as formal Citation evidence.
    """

    return set_precision_recall_f1(
        "evidence_id_overlap", predicted=predicted_evidence_ids, gold=gold_evidence_ids
    )


def citation_resolvability(*, resolvable: list[bool]) -> MetricResult:
    return MetricResult.ratio("citation_resolvability", sum(resolvable), len(resolvable))


def claim_citation_completeness(*, claims_with_citations: int, total_claims: int) -> MetricResult:
    if claims_with_citations < 0 or total_claims < 0 or claims_with_citations > total_claims:
        raise ValueError("cited claims must be between zero and total claims")
    return MetricResult.ratio("claim_citation_completeness", claims_with_citations, total_claims)


def abstention_metrics(
    *, predicted_answerable: list[bool], gold_answerable: list[bool]
) -> dict[str, MetricResult]:
    if len(predicted_answerable) != len(gold_answerable):
        raise ValueError("answerability predictions and Gold labels must have equal length")
    unanswerable = sum(not value for value in gold_answerable)
    correctly_abstained = sum(
        not predicted and not gold
        for predicted, gold in zip(predicted_answerable, gold_answerable, strict=True)
    )
    false_answers = sum(
        predicted and not gold
        for predicted, gold in zip(predicted_answerable, gold_answerable, strict=True)
    )
    false_abstentions = sum(
        not predicted and gold
        for predicted, gold in zip(predicted_answerable, gold_answerable, strict=True)
    )
    return {
        "unanswerable_recall": MetricResult.ratio(
            "unanswerable_recall", correctly_abstained, unanswerable
        ),
        "false_answer_rate": MetricResult.ratio("false_answer_rate", false_answers, unanswerable),
        "false_abstention_rate": MetricResult.ratio(
            "false_abstention_rate", false_abstentions, sum(gold_answerable)
        ),
    }
