import hashlib
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
    DocxPaginationGold,
    DocxRenderProfile,
    DS0CorpusDataset,
    DS1ParsingDataset,
    DS1ReviewDecisions,
    DS2EvidenceDataset,
    DS5RetrievalQADataset,
    EvidenceBBox,
    EvidenceGroup,
    EvidenceRecord,
    OCRGold,
    OCRRegion,
    PageGold,
    PageRegion,
    QAHumanReviewRecord,
    RetrievalQACase,
    TableGold,
    TablePageFragment,
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
    assert len(SCHEMA_MODELS) == 107
    assert "course_eval_candidate_revision_history.schema.json" in SCHEMA_MODELS
    assert "courserag_corpus_fixture_manifest.schema.json" in SCHEMA_MODELS
    assert "courserag_ds1_sampling_plan.schema.json" in SCHEMA_MODELS
    assert "courserag_ds1_batch_approval.schema.json" in SCHEMA_MODELS
    assert "courserag_ds1_candidate_manifest.schema.json" in SCHEMA_MODELS
    assert "courserag_ds1_review_decisions.schema.json" in SCHEMA_MODELS
    assert "courserag_p03_eval_identity_snapshot.schema.json" in SCHEMA_MODELS
    assert "courserag_p04_input_work_package.schema.json" in SCHEMA_MODELS
    assert "courserag_p05_ocr_candidate_manifest.schema.json" in SCHEMA_MODELS
    assert "courserag_p05_ocr_batch_approval.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_2_security_dev.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_2_security_dev_approval.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_2_security_blind_commitment.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_3_security_dev.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_3_security_review.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_3_security_dev_approval.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds3_p16_pilot.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds7_p16_pilot.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p16_review_decisions.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p16_bundle_manifest.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p16_bundle_approval.schema.json" in SCHEMA_MODELS
    assert "courserag_p10_3_security_blind_commitment.schema.json" in SCHEMA_MODELS
    assert "courserag_ds3_section_scopes.schema.json" in SCHEMA_MODELS
    assert "courserag_ds3_split.schema.json" in SCHEMA_MODELS
    assert "courserag_ds3_review_decisions.schema.json" in SCHEMA_MODELS
    assert "courserag_p07_gold_bundle_manifest.schema.json" in SCHEMA_MODELS
    assert "courserag_p07_gold_bundle_approval.schema.json" in SCHEMA_MODELS
    assert "courserag_p08_source_packages.schema.json" in SCHEMA_MODELS
    assert "courserag_p08_ds5_split.schema.json" in SCHEMA_MODELS
    assert "courserag_p08_review_decisions.schema.json" in SCHEMA_MODELS
    assert "courserag_p08_gold_bundle_manifest.schema.json" in SCHEMA_MODELS
    assert "courserag_p08_gold_bundle_approval.schema.json" in SCHEMA_MODELS
    assert "courserag_ds0.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds8.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds1_p14_pilot.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds1_p14_fixtures.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p14_review_decisions.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p14_bundle_approval.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds2_p15_pilot.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds2_p15_fixtures.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p15_review_decisions.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p15_bundle_approval.schema.json" in SCHEMA_MODELS
    assert "coursepilot_sys_ds1.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds1_p18.schema.json" in SCHEMA_MODELS
    assert "coursepilot_cp_ds8_p18.schema.json" in SCHEMA_MODELS
    assert "coursepilot_sys_ds1_p18.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p18_bundle_manifest.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p18_review_decisions.schema.json" in SCHEMA_MODELS
    assert "coursepilot_p18_formal_approval.schema.json" in SCHEMA_MODELS
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


def test_derived_corpus_fixture_requires_parent_manifest_and_exclusion_group():
    with pytest.raises(ValidationError, match="parent_document_id"):
        CorpusDocument(
            record_id="corpus-derived-1",
            course_id="course-1",
            document_id="doc-derived-1",
            filename="derived.pdf",
            repository_relative_path="storage_eval/derived.pdf",
            document_role="derived_fixture",
            mime_type="application/pdf",
            sha256=HASH_A,
            document_version="eval-v1-aaaaaaaaaaaaaaaa",
        )

    record = CorpusDocument(
        record_id="corpus-derived-1",
        course_id="course-1",
        document_id="doc-derived-1",
        filename="derived.pdf",
        repository_relative_path="storage_eval/derived.pdf",
        document_role="derived_fixture",
        parent_document_id="doc-primary-1",
        mime_type="application/pdf",
        sha256=HASH_A,
        document_version="eval-v1-aaaaaaaaaaaaaaaa",
        derivation_manifest_sha256=HASH_B,
        mutually_exclusive_variant_group="course-1-document-variants",
    )
    assert record.document_role == "derived_fixture"


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


def test_ds1_supports_regions_ocr_coordinates_and_docx_pagination():
    page = PageGold(
        record_id="page-1",
        document_id="doc-1",
        document_version="v1",
        page_number=1,
        page_type="complex_layout",
        needs_ocr=False,
        page_width=595,
        page_height=842,
        bbox_coordinate_space="pdf_points_top_left",
        reading_order=["region-1"],
        regions=[
            PageRegion(
                region_id="region-1",
                region_type="title",
                bbox=(10, 20, 300, 60),
                block_id="block-1",
                order_index=0,
            )
        ],
        noise_regions=[
            PageRegion(
                region_id="noise-1",
                region_type="page_number",
                text="1",
                bbox=(280, 790, 300, 810),
            )
        ],
    )
    ocr = OCRGold(
        record_id="ocr-1",
        source_span=SourceSpan(
            document_id="doc-1",
            document_version="v1",
            document_sha256=HASH_A,
            page_start=1,
            page_end=1,
        ),
        ocr_input_document_id="doc-scan",
        ocr_input_document_version="v1-scan",
        ocr_input_document_sha256=HASH_B,
        ocr_input_page_number=1,
        image_sha256=HASH_B,
        image_width=100,
        image_height=100,
        dpi=200,
        source_page_width_points=50,
        source_page_height_points=50,
        raw_text="人工核对文本",
        raw_text_sha256=hashlib.sha256("人工核对文本".encode()).hexdigest(),
        gold_text="人工核对文本",
        gold_text_sha256=hashlib.sha256("人工核对文本".encode()).hexdigest(),
        regions=[
            OCRRegion(
                region_id="ocr-region-1",
                bbox=(1, 2, 3, 4),
                source_bbox_pdf_points=(0.5, 1, 1.5, 2),
                role="body",
                gold_text="人工核对文本",
                include_in_body_text=True,
                body_order_index=0,
            )
        ],
        reading_order=["ocr-region-1"],
    )
    pagination = DocxPaginationGold(
        record_id="docx-page-1",
        document_id="docx-1",
        document_version="v1",
        render_profile=DocxRenderProfile(
            provider="fixed-renderer",
            renderer_version="1.0",
            font_manifest_sha256=HASH_A,
            profile_sha256=HASH_B,
        ),
        section_path=["1", "1.1"],
        block_id="block-18",
        source_unit_id="paragraph:18",
        source_text="1.1 标题",
        source_text_sha256=hashlib.sha256("1.1 标题".encode()).hexdigest(),
        paragraph_index=18,
        expected_physical_page_index=4,
        expected_display_page_label="1",
        expected_section_page_index=1,
        rendered_pdf_sha256=HASH_A,
        rendered_pdf_hash_basis="canonical_pdf_without_volatile_metadata",
    )
    dataset = DS1ParsingDataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        records=[page, ocr, pagination],
    )
    assert dataset.records[2].record_type == "docx_pagination"


def test_page_gold_rejects_ambiguous_coordinates_and_invalid_reading_order():
    with pytest.raises(ValidationError, match="coordinate space"):
        PageGold(
            record_id="page-no-coordinate-space",
            document_id="doc-1",
            document_version="v1",
            page_number=1,
            page_type="native_text",
            needs_ocr=False,
            page_width=595,
            page_height=842,
        )

    with pytest.raises(ValidationError, match="content regions only"):
        PageGold(
            record_id="page-noise-in-reading-order",
            document_id="doc-1",
            document_version="v1",
            page_number=1,
            page_type="native_text",
            needs_ocr=False,
            reading_order=["noise-1"],
            noise_regions=[PageRegion(region_id="noise-1", region_type="page_number")],
        )


def test_table_gold_requires_a_rectangular_grid():
    with pytest.raises(ValidationError, match="column_count"):
        TableGold(
            record_id="table-1",
            table_id="table-1",
            source_span=SourceSpan(
                document_id="doc-1",
                document_version="v1",
                document_sha256=HASH_A,
                page_start=1,
                page_end=1,
            ),
            row_count=2,
            column_count=2,
            cells=[["a", "b"], ["c"]],
        )

    with pytest.raises(ValidationError, match="page-fragment rows"):
        TableGold(
            record_id="table-fragment-1",
            table_id="table-fragment-1",
            source_span=SourceSpan(
                document_id="doc-1",
                document_version="v1",
                document_sha256=HASH_A,
                page_start=1,
                page_end=2,
            ),
            row_count=2,
            column_count=2,
            cells=[["a", "b"], ["c", "d"]],
            rendered_page_fragments=[
                TablePageFragment(
                    physical_page_index=1,
                    row_indices=[0, 1],
                    visible_cells=[["a", "b"]],
                    continuation_to_next_page=True,
                )
            ],
        )


def test_ds1_review_decisions_reject_duplicate_record_ids():
    with pytest.raises(ValidationError, match="must be unique"):
        DS1ReviewDecisions(
            candidate_file_sha256=HASH_A,
            reviewed_record_ids=["record-1", "record-1"],
            record_count=2,
        )

    with pytest.raises(ValidationError, match="must be disjoint"):
        DS1ReviewDecisions(
            candidate_file_sha256=HASH_A,
            reviewed_record_ids=["record-1"],
            returned_record_ids=["record-1"],
            record_count=2,
        )


def test_ds2_accepts_ocr_derived_bbox_and_confidence():
    record = EvidenceRecord(
        record_id="evidence-ocr-1",
        evidence_id="ev-ocr-1",
        source_span=SourceSpan(
            document_id="doc-scan-1",
            document_version="v1",
            document_sha256=HASH_A,
            page_start=2,
            page_end=2,
        ),
        source_type="ocr_derived",
        gold_text="人工核对的 OCR 原文",
        content_sha256=HASH_B,
        semantic_unit_type="definition",
        bboxes=[EvidenceBBox(page_number=2, bbox=(10, 20, 100, 80))],
        ocr_confidence=0.91,
    )
    assert record.ocr_confidence == pytest.approx(0.91)


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
        graded_relevance={"ev-1": 2, "ev-support": 1},
        allowed_answer_variants=["同义答案"],
        expected_behavior="answer",
    )
    dataset = DS5RetrievalQADataset(
        dataset_id="courserag-eval",
        dataset_version="v1",
        cases=[case],
    )
    assert dataset.cases[0].answerable is True


def test_unanswerable_expected_behavior_and_graded_relevance_are_typed():
    case = RetrievalQACase(
        record_id="ret-unanswerable-1",
        query="语料中不存在的问题？",
        query_type="unanswerable",
        answerable=False,
        difficulty="hard",
        gold_answer_type="unanswerable",
        expected_behavior="no_relevant_evidence",
    )
    assert case.expected_behavior == "no_relevant_evidence"

    with pytest.raises(ValidationError, match="0, 1 or 2"):
        RetrievalQACase(
            record_id="ret-invalid-grade",
            query="问题",
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
            graded_relevance={"ev-1": 3},
        )


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
