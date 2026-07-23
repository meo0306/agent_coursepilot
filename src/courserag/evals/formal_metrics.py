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
        if assessment.label == ClaimLabel.CORRECT_SUPPORTED
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


def answer_conciseness_pass_rate(
    reviews: Sequence[QAHumanReviewRecord],
) -> MetricResult:
    return MetricResult.ratio(
        "answer_conciseness_pass_rate",
        sum(review.conciseness_pass for review in reviews),
        len(reviews),
    )
