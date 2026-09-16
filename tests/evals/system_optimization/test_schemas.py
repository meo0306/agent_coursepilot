from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from evaluation.system_optimization.dev_loader import load_candidate
from evaluation.system_optimization.schemas import (
    AdequacyStatus,
    ArtifactReviewDecision,
    ArtifactType,
    CaseApprovalDecision,
)


def test_repository_candidate_matrix_is_complete() -> None:
    loaded = load_candidate()

    assert len(loaded.cases.records) == 27
    assert len(loaded.failures.records) == 7
    for artifact in ArtifactType:
        records = [item for item in loaded.cases.records if item.artifact_type is artifact]
        assert len(records) == 9
        assert {item.evidence_package.capacity_tier.value for item in records} == {
            "thin",
            "medium",
            "rich",
        }
        assert {item.candidate_adequacy.status for item in records} == {AdequacyStatus.ADEQUATE}


def test_artifact_review_requires_integer_zero_to_four_burden() -> None:
    with pytest.raises(ValidationError):
        ArtifactReviewDecision(
            blind_artifact_id="blind-1",
            artifact_type=ArtifactType.LESSON,
            artifact_status="accepted",
            rubric_scores={f"L-H{i}": 5 for i in range(1, 9)},
            edit_burden=5,
            critical_defect=False,
            reviewer_id="reviewer-1",
            reviewed_at=datetime.now(UTC),
        )


def test_case_approval_requires_human_identity_time_and_adequacy() -> None:
    with pytest.raises(ValidationError):
        CaseApprovalDecision(record_id="case-1", decision="approve")

    decision = CaseApprovalDecision(
        record_id="case-1",
        decision="approve",
        reviewer_id="reviewer-1",
        reviewed_at=datetime.now(UTC),
        adequacy_decision=AdequacyStatus.ADEQUATE,
    )
    assert decision.decision == "approve"
