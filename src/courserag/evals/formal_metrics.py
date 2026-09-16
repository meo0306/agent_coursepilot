from __future__ import annotations

from collections.abc import Sequence

from courserag.evals.schemas import (
    EvidenceGroup,
    QACitationHumanAssessment,
    QAClaimHumanAssessment,
    QAHumanReviewRecord,
)
from evaluation.contracts import MetricResult

CitationAssessment = QACitationHumanAssessment
ClaimAssessment = QAClaimHumanAssessment


class ClaimLabel:
    """Compatibility constants backed by the frozen human-score literals."""

    CORRECT_SUPPORTED = "correct_supported"
    CORRECT_BUT_UNCITED = "correct_but_uncited"
    UNSUPPORTED = "unsupported"
    CONTRADICTORY = "contradictory"
    IRRELEVANT = "irrelevant"


def complete_evidence_group_recall_at_k(
    ranked_evidence_ids: list[str],
    groups: list[EvidenceGroup],
    *,
    k: int,
) -> MetricResult:
    if k < 1:
        raise ValueError("k must be positive")
    complete_groups = [group for group in groups if group.sufficiency == "complete"]
    if not complete_groups:
        return MetricResult.ratio("complete_evidence_group_recall_at_k", 0, 0)
    retrieved = set(ranked_evidence_ids[:k])
    hit = any(set(group.required_evidence_ids).issubset(retrieved) for group in complete_groups)
    return MetricResult.ratio(
        "complete_evidence_group_recall_at_k",
        int(hit),
        1,
        details={"k": k, "complete_group_count": len(complete_groups)},
    )


def claim_metrics(
    assessments: list[ClaimAssessment],
    *,
    required_gold_claim_ids: set[str],
) -> dict[str, MetricResult]:
    total_claims = len(assessments)
    correct_supported = sum(
        assessment.label == ClaimLabel.CORRECT_SUPPORTED for assessment in assessments
    )
    unsupported = sum(
        assessment.label in {ClaimLabel.UNSUPPORTED, ClaimLabel.CORRECT_BUT_UNCITED}
        for assessment in assessments
    )
    contradictory = sum(assessment.label == ClaimLabel.CONTRADICTORY for assessment in assessments)
    irrelevant = sum(assessment.label == ClaimLabel.IRRELEVANT for assessment in assessments)

    covered_gold_claims = {
        claim_id
        for assessment in assessments
        if assessment.label
        in {
            ClaimLabel.CORRECT_SUPPORTED,
            ClaimLabel.CORRECT_BUT_UNCITED,
        }
        for claim_id in assessment.matched_gold_claim_ids
        if claim_id in required_gold_claim_ids
    }
    citation_links = [citation for assessment in assessments for citation in assessment.citations]
    supported_links = [citation for citation in citation_links if citation.supports_claim]
    claims_with_support = sum(
        any(citation.supports_claim for citation in assessment.citations)
        for assessment in assessments
    )
    cited_gold_claims = {
        claim_id
        for citation in supported_links
        for claim_id in citation.supported_gold_claim_ids
        if claim_id in required_gold_claim_ids
    }

    return {
        "gold_claim_coverage": MetricResult.ratio(
            "gold_claim_coverage",
            len(covered_gold_claims),
            len(required_gold_claim_ids),
        ),
        "correct_claim_precision": MetricResult.ratio(
            "correct_claim_precision",
            correct_supported,
            total_claims,
        ),
        "unsupported_claim_rate": MetricResult.ratio(
            "unsupported_claim_rate",
            unsupported,
            total_claims,
        ),
        "contradictory_claim_rate": MetricResult.ratio(
            "contradictory_claim_rate",
            contradictory,
            total_claims,
        ),
        "irrelevant_claim_rate": MetricResult.ratio(
            "irrelevant_claim_rate",
            irrelevant,
            total_claims,
        ),
        "citation_claim_support_rate": MetricResult.ratio(
            "citation_claim_support_rate",
            claims_with_support,
            total_claims,
        ),
        "citation_precision": MetricResult.ratio(
            "citation_precision",
            len(supported_links),
            len(citation_links),
        ),
        "citation_recall": MetricResult.ratio(
            "citation_recall",
            len(cited_gold_claims),
            len(required_gold_claim_ids),
        ),
    }


def claim_aware_answerability_metrics(
    *,
    system_answered: Sequence[bool],
    gold_answerable: Sequence[bool],
    answered_correctly: Sequence[bool],
) -> dict[str, MetricResult]:
    """Score answerability using human-validated answer correctness.

    ``answered_correctly`` must already apply the frozen Claim-level rule:
    there is no contradictory Claim and Required Gold Claim Coverage reaches
    the frozen threshold.  Merely choosing to answer is not a true positive.
    """

    if not (len(system_answered) == len(gold_answerable) == len(answered_correctly)):
        raise ValueError("answerability inputs must have equal length")
    if any(
        correct and not answered
        for correct, answered in zip(answered_correctly, system_answered, strict=True)
    ):
        raise ValueError("an unanswered Case cannot be marked answered correctly")

    true_positive = sum(
        answered and gold and correct
        for answered, gold, correct in zip(
            system_answered, gold_answerable, answered_correctly, strict=True
        )
    )
    predicted_positive = sum(system_answered)
    actual_positive = sum(gold_answerable)
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = true_positive / actual_positive if actual_positive else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    unanswerable = sum(not value for value in gold_answerable)
    false_answers = sum(
        answered and not gold
        for answered, gold in zip(system_answered, gold_answerable, strict=True)
    )
    false_abstentions = sum(
        not answered and gold
        for answered, gold in zip(system_answered, gold_answerable, strict=True)
    )
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
        "false_answer_rate": MetricResult.ratio("false_answer_rate", false_answers, unanswerable),
        "false_abstention_rate": MetricResult.ratio(
            "false_abstention_rate", false_abstentions, actual_positive
        ),
    }


def answer_conciseness_pass_rate(
    reviews: Sequence[QAHumanReviewRecord],
) -> MetricResult:
    return MetricResult.ratio(
        "answer_conciseness_pass_rate",
        sum(review.conciseness_pass for review in reviews),
        len(reviews),
    )
