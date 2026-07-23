from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from coursepilot.evals.formal_metrics import (
    RecoveryObservation,
    RepairObservation,
    json_leaf_changes,
    recovery_metrics,
    repair_metrics,
    validation_issue_metrics,
)
from coursepilot.evals.formal_schemas import (
    IssueScope,
    RecoveryExpectation,
    ValidationIssue,
)
from courserag.evals.formal_metrics import (
    CitationAssessment,
    ClaimAssessment,
    ClaimLabel,
    answer_conciseness_pass_rate,
    claim_metrics,
    complete_evidence_group_recall_at_k,
)
from courserag.evals.schemas import EvidenceGroup, QAHumanReviewRecord


def _issue(
    code: str,
    path: str,
    *,
    severity: str = "error",
    allowed_parent_paths: list[str] | None = None,
) -> ValidationIssue:
    return ValidationIssue(
        code=code,
        severity=severity,
        scope=IssueScope(
            artifact_type="lesson",
            item_id="session-1",
            json_path=path,
        ),
        allowed_parent_paths=allowed_parent_paths or [],
        auto_repairable=True,
    )


def test_complete_evidence_group_recall_requires_a_whole_group():
    groups = [
        EvidenceGroup(
            group_id="group-1",
            sufficiency="complete",
            required_evidence_ids=["e1", "e2"],
        ),
        EvidenceGroup(
            group_id="supporting",
            sufficiency="partial",
            required_evidence_ids=["e3"],
        ),
    ]

    assert complete_evidence_group_recall_at_k(["e1", "e3"], groups, k=2).value == 0
    assert complete_evidence_group_recall_at_k(["e1", "e2"], groups, k=2).value == 1
    result = complete_evidence_group_recall_at_k([], groups[1:], k=1)
    assert result.value is None
    assert not result.applicable


def test_claim_metrics_use_human_claim_and_citation_labels():
    metrics = claim_metrics(
        [
            ClaimAssessment(
                system_claim_id="system-1",
                label=ClaimLabel.CORRECT_SUPPORTED,
                matched_gold_claim_ids=["gold-1"],
                citations=[
                    CitationAssessment(
                        citation_id="citation-1",
                        supports_claim=True,
                        supported_gold_claim_ids=["gold-1"],
                    )
                ],
            ),
            ClaimAssessment(
                system_claim_id="system-2",
                label=ClaimLabel.CORRECT_BUT_UNCITED,
                matched_gold_claim_ids=["gold-2"],
            ),
            ClaimAssessment(
                system_claim_id="system-3",
                label=ClaimLabel.CONTRADICTORY,
            ),
            ClaimAssessment(
                system_claim_id="system-4",
                label=ClaimLabel.IRRELEVANT,
            ),
        ],
        required_gold_claim_ids={"gold-1", "gold-2"},
    )

    assert metrics["gold_claim_coverage"].value == 0.5
    assert metrics["correct_claim_precision"].value == pytest.approx(1 / 4)
    assert metrics["unsupported_claim_rate"].value == pytest.approx(1 / 4)
    assert metrics["contradictory_claim_rate"].value == pytest.approx(1 / 4)
    assert metrics["irrelevant_claim_rate"].value == pytest.approx(1 / 4)
    assert metrics["citation_precision"].value == 1
    assert metrics["citation_recall"].value == 0.5


def test_empty_claim_denominators_are_not_reported_as_perfect():
    metrics = claim_metrics([], required_gold_claim_ids=set())

    assert all(not result.applicable for result in metrics.values())
    assert all(result.value is None for result in metrics.values())


def test_answer_conciseness_uses_reviewed_answer_denominator():
    metadata = {
        "review_id": "review-1",
        "reviewer_id": "reviewer-1",
        "rubric_version": "qa-v1",
        "reviewed_at": datetime(2026, 7, 24, tzinfo=UTC),
        "blinded_sample_id": "blind-1",
    }
    reviews = [
        QAHumanReviewRecord(
            metadata=metadata,
            case_id="case-1",
            system_answer_id="answer-1",
            claims=[],
            missed_gold_claim_ids=[],
            conciseness_pass=True,
            answer_should_be_refused=False,
            system_refused=False,
        ),
        QAHumanReviewRecord(
            metadata={**metadata, "review_id": "review-2", "blinded_sample_id": "blind-2"},
            case_id="case-2",
            system_answer_id="answer-2",
            claims=[],
            missed_gold_claim_ids=[],
            conciseness_pass=False,
            answer_should_be_refused=True,
            system_refused=False,
        ),
    ]

    assert answer_conciseness_pass_rate(reviews).value == 0.5
    assert answer_conciseness_pass_rate([]).value is None


def test_validation_metrics_match_code_and_allowed_scope_one_to_one():
    gold = [
        _issue(
            "TIME_MISMATCH",
            "$.sessions[0].minutes",
            allowed_parent_paths=["$.sessions[0]"],
        )
    ]
    predicted = [
        _issue("TIME_MISMATCH", "$.sessions[0]"),
        _issue("TIME_MISMATCH", "$.sessions[0]"),
    ]

    metrics = validation_issue_metrics(gold, predicted)

    assert metrics["issue_detection_precision"].value == 0.5
    assert metrics["issue_detection_recall"].value == 1
    assert metrics["scope_localization_accuracy"].value == 1


def test_clean_artifact_false_positive_only_counts_severe_issues():
    warning = _issue("STYLE", "$.title", severity="warning")
    severe = _issue("BROKEN", "$.title", severity="critical")

    assert validation_issue_metrics([], [warning])["clean_artifact_false_positive_rate"].value == 0
    assert validation_issue_metrics([], [severe])["clean_artifact_false_positive_rate"].value == 1


def test_repair_patch_metrics_detect_targeting_regression_and_preservation():
    before = {"title": "kept", "sessions": [{"minutes": 20}], "owner": "teacher"}
    after = {"title": "kept", "sessions": [{"minutes": 45}], "owner": "changed"}
    target_issue = _issue("TIME_MISMATCH", "$.sessions[0].minutes")
    regression = _issue("OWNER_CHANGED", "$.owner", severity="critical")
    observation = RepairObservation(
        artifact_before=before,
        artifact_after=after,
        allowed_paths=["$.sessions[0].minutes"],
        original_correct_paths=["$.title"],
        expected_resolved_issue_codes=["TIME_MISMATCH"],
        issues_before=[target_issue],
        issues_by_round=[[regression]],
        max_repair_rounds=2,
    )

    metrics = repair_metrics(observation)

    assert json_leaf_changes(before, after) == {
        "$.sessions[0].minutes",
        "$.owner",
    }
    assert metrics["repair_attempt_success_rate"].value == 1
    assert metrics["targeted_modification_rate"].value == 0.5
    assert metrics["unauthorized_modification_rate"].value == 0.5
    assert metrics["regression_rate"].value == 1
    assert metrics["preservation_rate"].value == 1
    assert metrics["issue_reduction"].value == -2


def test_recovery_metrics_follow_expected_denominators():
    expectations = [
        RecoveryExpectation(
            interrupt_reached=True,
            resume_succeeds=True,
            completed_nodes_reused=2,
            completed_nodes_before_resume=2,
            edited_fields_preserved=2,
            edited_fields_total=2,
            duplicate_side_effects=0,
            replayed_side_effect_attempts=2,
            approval_scope_correct=True,
            stale_version_detected=True,
        )
    ]
    observations = [
        RecoveryObservation(
            interrupt_reached=True,
            resume_succeeds=True,
            completed_nodes_reused=2,
            edited_fields_preserved=1,
            duplicate_side_effects=1,
            replayed_side_effect_attempts=2,
            approval_scope_correct=False,
            stale_version_detected=True,
        )
    ]

    metrics = recovery_metrics(expectations, observations)

    assert metrics["interrupt_reach_rate"].value == 1
    assert metrics["resume_success_rate"].value == 1
    assert metrics["completed_node_reuse_rate"].value == 1
    assert metrics["human_edit_preservation_rate"].value == 0.5
    assert metrics["duplicate_side_effect_rate"].value == 0.5
    assert metrics["approval_scope_accuracy"].value == 0
    assert metrics["stale_version_detection_rate"].value == 1


def test_duplicate_side_effect_count_cannot_exceed_replay_attempts():
    with pytest.raises(ValidationError, match="cannot exceed"):
        RecoveryObservation(
            interrupt_reached=True,
            resume_succeeds=True,
            completed_nodes_reused=0,
            edited_fields_preserved=0,
            duplicate_side_effects=2,
            replayed_side_effect_attempts=1,
            approval_scope_correct=True,
        )
