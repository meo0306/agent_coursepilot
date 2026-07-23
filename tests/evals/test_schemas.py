from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from coursepilot.evals.formal_schemas import (
    CPDS4ValidationDataset,
    IssueScope,
    LessonHumanReview,
    ValidationFaultCase,
    ValidationIssue,
)
from courserag.evals.schemas import (
    CorpusDocument,
    DS0CorpusDataset,
    DS2EvidenceDataset,
    DS5RetrievalQADataset,
    EvidenceGroup,
    EvidenceRecord,
    QAHumanReviewRecord,
    RetrievalQACase,
)
from evaluation.contracts import ApprovalRecord, ReviewStatus, SourceSpan
from evaluation.datasets import (
    load_coursepilot_human_score_jsonl,
    load_qa_human_score_jsonl,
)
from evaluation.schema_export import SCHEMA_MODELS

HASH_A = "a" * 64
HASH_B = "b" * 64


def test_all_p02_dataset_models_have_exported_schema_names():
    assert len(SCHEMA_MODELS) == 25
    assert "courserag_ds0.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds8.schema.json" in SCHEMA_MODELS
    assert "coursepilot_sys_ds1.schema.json" in SCHEMA_MODELS
    assert "courserag_qa_human_score_record.schema.json" in SCHEMA_MODELS
    assert "coursepilot_human_score_record.schema.json" in SCHEMA_MODELS


def test_candidate_corpus_record_is_valid_without_approval():
    record = CorpusDocument(
        record_id="corpus-doc-1",
        document_id="doc-1",
        filename="sample.pdf",
        mime_type="application/pdf",
        sha256=HASH_A,
        document_version="v1",
        review_status="candidate",
    )
    dataset = DS0CorpusDataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        documents=[record],
    )

    assert dataset.documents[0].approval is None


def test_approved_record_requires_human_approval_metadata():
    with pytest.raises(ValidationError, match="human approval"):
        CorpusDocument(
            record_id="corpus-doc-1",
            document_id="doc-1",
            filename="sample.pdf",
            mime_type="application/pdf",
            sha256=HASH_A,
            document_version="v1",
            review_status=ReviewStatus.APPROVED,
        )

    record = CorpusDocument(
        record_id="corpus-doc-1",
        document_id="doc-1",
        filename="sample.pdf",
        mime_type="application/pdf",
        sha256=HASH_A,
        document_version="v1",
        review_status=ReviewStatus.APPROVED,
        approval=ApprovalRecord(
            review_id="review-1",
            reviewer_id="human-1",
            reviewed_at=datetime(2026, 7, 23, tzinfo=UTC),
            candidate_sha256=HASH_A,
            approved_record_sha256=HASH_B,
        ),
    )
    assert record.review_status is ReviewStatus.APPROVED


def test_evidence_requires_source_coordinates_and_answerable_case_requires_group():
    with pytest.raises(ValidationError, match="source span requires"):
        SourceSpan(
            document_id="doc-1",
            document_version="v1",
            document_sha256=HASH_A,
        )

    evidence = EvidenceRecord(
        record_id="evidence-record-1",
        evidence_id="ev-1",
        source_span=SourceSpan(
            document_id="doc-1",
            document_version="v1",
            document_sha256=HASH_A,
            page_start=1,
            page_end=1,
        ),
        source_type="synthetic",
        gold_text="Synthetic evidence text long enough for an adapter case.",
        content_sha256=HASH_B,
        semantic_unit_type="definition",
    )
    dataset = DS2EvidenceDataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        evidence=[evidence],
    )
    assert dataset.evidence[0].source_span.page_start == 1

    with pytest.raises(ValidationError, match="at least one evidence group"):
        RetrievalQACase(
            record_id="ret-1",
            query="What is the synthetic concept?",
            query_type="definition",
            answerable=True,
            difficulty="easy",
            gold_answer_type="explanatory",
        )


def test_unanswerable_case_cannot_contain_gold_and_validation_issue_contract_is_typed():
    with pytest.raises(ValidationError, match="cannot contain answer Gold"):
        RetrievalQACase(
            record_id="ret-1",
            query="Unanswerable?",
            query_type="unanswerable",
            answerable=False,
            difficulty="hard",
            gold_answer_type="unanswerable",
            gold_evidence_groups=[
                EvidenceGroup(
                    group_id="group-1",
                    sufficiency="complete",
                    required_evidence_ids=["ev-1"],
                )
            ],
        )

    issue = ValidationIssue(
        code="LESSON_TIME_TOTAL_MISMATCH",
        severity="error",
        scope=IssueScope(
            artifact_type="lesson",
            item_id="session-1",
            json_path="$.sessions[0].minutes",
        ),
        auto_repairable=True,
    )
    dataset = CPDS4ValidationDataset(
        dataset_id="coursepilot-eval",
        dataset_version="v1",
        cases=[
            ValidationFaultCase(
                record_id="fault-1",
                artifact_type="lesson",
                artifact_fixture_id="lesson-valid-1",
                gold_issues=[issue],
            )
        ],
    )
    assert dataset.cases[0].gold_issues[0].code == "LESSON_TIME_TOTAL_MISMATCH"


def test_answerable_retrieval_case_accepts_evidence_group():
    case = RetrievalQACase(
        record_id="ret-1",
        query="What is the synthetic concept?",
        query_type="definition",
        answerable=True,
        difficulty="easy",
        gold_answer_type="explanatory",
        gold_evidence_groups=[
            EvidenceGroup(
                group_id="group-1",
                sufficiency="complete",
                required_evidence_ids=["ev-1"],
            )
        ],
    )
    dataset = DS5RetrievalQADataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        cases=[case],
    )
    assert dataset.cases[0].answerable is True


def test_human_score_contracts_require_frozen_fields_and_complete_rubrics():
    metadata = {
        "review_id": "review-1",
        "reviewer_id": "reviewer-1",
        "rubric_version": "v1",
        "reviewed_at": datetime(2026, 7, 24, tzinfo=UTC),
        "blinded_sample_id": "blind-1",
    }
    with pytest.raises(ValidationError, match="conciseness_pass"):
        QAHumanReviewRecord(
            metadata=metadata,
            case_id="case-1",
            system_answer_id="answer-1",
            claims=[],
            missed_gold_claim_ids=[],
            answer_should_be_refused=False,
            system_refused=False,
        )

    with pytest.raises(ValidationError, match="at least 8 items"):
        LessonHumanReview(
            metadata=metadata,
            artifact_id="lesson-1",
            rubric_scores={"L-H1": 3},
            edit_burden=2,
            critical_defect=False,
            artifact_status="minor_edit",
        )


def test_coursepilot_human_score_json_schema_enforces_complete_rubric_sizes():
    schema = SCHEMA_MODELS["coursepilot_human_score_record.schema.json"].model_json_schema()
    definitions = schema["$defs"]

    assert definitions["LessonHumanReview"]["properties"]["rubric_scores"]["minProperties"] == 8
    assert definitions["LessonHumanReview"]["properties"]["rubric_scores"]["maxProperties"] == 8
    for review_type in ("ExamQuestionHumanReview", "PPTSlideHumanReview"):
        rubric_schema = definitions[review_type]["properties"]["rubric_scores"]
        assert rubric_schema["minProperties"] == 10
        assert rubric_schema["maxProperties"] == 10


def test_tracked_human_score_jsonl_pilots_are_valid_unapproved_contract_samples():
    root = Path("datasets")
    qa_records = load_qa_human_score_jsonl(
        root / "courserag_eval" / "v1" / "human_scores" / "pilot.jsonl"
    )
    coursepilot_records = load_coursepilot_human_score_jsonl(
        root / "coursepilot_eval" / "v1" / "human_scores" / "pilot.jsonl"
    )

    assert len(qa_records) == 2
    assert len(coursepilot_records) == 3
    assert {record.claims[0].label for record in qa_records} == {
        "correct_supported",
        "irrelevant",
    }
    assert all(record.metadata.review_status is ReviewStatus.CANDIDATE for record in qa_records)
    assert all(
        record.root.metadata.review_status is ReviewStatus.CANDIDATE
        for record in coursepilot_records
    )
