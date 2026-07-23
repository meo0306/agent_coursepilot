from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from evaluation.contracts import (
    HumanReviewMetadata,
    ReviewableRecord,
    Sha256,
    SourceSpan,
    StrictModel,
)


class DatasetEnvelope(StrictModel):
    schema_version: str
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)


class CorpusDocument(ReviewableRecord):
    document_id: str = Field(min_length=1, max_length=160)
    filename: str = Field(min_length=1, max_length=512)
    mime_type: Literal[
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]
    sha256: Sha256
    document_version: str = Field(min_length=1, max_length=120)
    page_count: int | None = Field(default=None, ge=1)
    included_in: list[str] = Field(default_factory=list)
    redistribution_status: str = Field(default="local_only_unverified", max_length=80)


class DS0CorpusDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds0.v1"] = "courserag.ds0.v1"
    documents: list[CorpusDocument] = Field(default_factory=list)


class PageGold(ReviewableRecord):
    record_type: Literal["page"] = "page"
    document_id: str
    document_version: str
    page_number: int = Field(ge=1)
    page_type: Literal["native_text", "scanned", "hybrid", "complex_layout"]
    needs_ocr: bool
    reading_order: list[str] = Field(default_factory=list)
    noise_types: list[str] = Field(default_factory=list)


class SectionGold(ReviewableRecord):
    record_type: Literal["section"] = "section"
    document_id: str
    document_version: str
    section_id: str
    title: str
    level: int = Field(ge=1)
    parent_section_id: str | None = None
    source_span: SourceSpan


class TableGold(ReviewableRecord):
    record_type: Literal["table"] = "table"
    table_id: str
    source_span: SourceSpan
    row_count: int = Field(ge=1)
    column_count: int = Field(ge=1)
    cells: list[list[str]] = Field(min_length=1)


class OCRGold(ReviewableRecord):
    record_type: Literal["ocr"] = "ocr"
    source_span: SourceSpan
    image_sha256: Sha256
    gold_text: str = Field(min_length=1)
    remove_spaces_between_chinese: bool = True
    normalize_full_width: bool = True
    ignore_line_break_difference: bool = True


ParsingGoldRecord = Annotated[
    PageGold | SectionGold | TableGold | OCRGold,
    Field(discriminator="record_type"),
]


class DS1ParsingDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds1.v1"] = "courserag.ds1.v1"
    records: list[ParsingGoldRecord] = Field(default_factory=list)


class EvidenceRecord(ReviewableRecord):
    evidence_id: str = Field(min_length=1, max_length=160)
    source_span: SourceSpan
    source_type: Literal["native_text", "ocr", "verified_content", "synthetic"]
    gold_text: str = Field(min_length=1, max_length=20_000)
    content_sha256: Sha256
    semantic_unit_type: Literal[
        "definition",
        "principle",
        "procedure",
        "list",
        "table",
        "example",
        "comparison",
        "formula",
        "application",
        "other",
    ]
    requires_parent: bool = False
    necessary_neighbor_text: list[str] = Field(default_factory=list)


class DS2EvidenceDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds2.v1"] = "courserag.ds2.v1"
    evidence: list[EvidenceRecord] = Field(default_factory=list)


class KnowledgePointRecord(ReviewableRecord):
    gold_kp_id: str
    course_id: str
    canonical_name: str = Field(min_length=1, max_length=240)
    aliases: list[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=4000)
    parent_gold_kp_id: str | None = None
    section_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(min_length=1)
    roles: list[str] = Field(default_factory=list)
    importance: Literal["core", "supporting", "optional"]
    granularity: Literal["atomic", "composite", "too_broad", "too_narrow"]


class DS3KnowledgePointDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds3.v1"] = "courserag.ds3.v1"
    knowledge_points: list[KnowledgePointRecord] = Field(default_factory=list)


class QueryProcessingExpected(StrictModel):
    normalized_query: str
    linked_knowledge_points: list[str] = Field(default_factory=list)
    filters: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)
    route: str
    allowed_expansions: list[str] = Field(default_factory=list)
    forbidden_expansions: list[str] = Field(default_factory=list)
    must_preserve_terms: list[str] = Field(default_factory=list)
    must_preserve_filters: bool = True


class QueryProcessingCase(ReviewableRecord):
    raw_query: str = Field(min_length=1, max_length=4000)
    expected: QueryProcessingExpected


class DS4QueryProcessingDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds4.v1"] = "courserag.ds4.v1"
    cases: list[QueryProcessingCase] = Field(default_factory=list)


class GoldClaim(StrictModel):
    claim_id: str
    claim_text: str = Field(min_length=1, max_length=8000)
    importance: Literal["required", "optional"] = "required"
    required_evidence_ids: list[str] = Field(min_length=1)


class EvidenceGroup(StrictModel):
    group_id: str
    sufficiency: Literal["complete", "partial"]
    required_evidence_ids: list[str] = Field(min_length=1)


class RetrievalQACase(ReviewableRecord):
    query: str = Field(min_length=1, max_length=4000)
    query_type: Literal[
        "exact_fact",
        "definition",
        "paraphrase",
        "comparison",
        "procedure",
        "application",
        "cross_section",
        "unanswerable",
    ]
    answerable: bool
    difficulty: Literal["easy", "medium", "hard"]
    gold_answer_type: Literal[
        "factoid",
        "list",
        "explanatory",
        "comparison",
        "procedure",
        "unanswerable",
    ]
    gold_short_answers: list[str] = Field(default_factory=list)
    gold_claims: list[GoldClaim] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    expected_knowledge_points: list[str] = Field(default_factory=list)
    filters: dict[str, str | int | bool | list[str]] = Field(default_factory=dict)
    gold_evidence_groups: list[EvidenceGroup] = Field(default_factory=list)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    properties: dict[str, bool] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_answerability(self) -> RetrievalQACase:
        if self.answerable:
            if self.gold_answer_type == "unanswerable":
                raise ValueError("answerable cases cannot use unanswerable gold_answer_type")
            if not self.gold_evidence_groups:
                raise ValueError("answerable cases require at least one evidence group")
        else:
            if self.gold_answer_type != "unanswerable":
                raise ValueError("unanswerable cases require unanswerable gold_answer_type")
            if self.gold_claims or self.gold_evidence_groups or self.gold_short_answers:
                raise ValueError("unanswerable cases cannot contain answer Gold")
        return self


class DS5RetrievalQADataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds5.v1"] = "courserag.ds5.v1"
    cases: list[RetrievalQACase] = Field(default_factory=list)


class QACitationHumanAssessment(StrictModel):
    citation_id: str = Field(min_length=1, max_length=160)
    supports_claim: bool
    supported_gold_claim_ids: list[str] = Field(default_factory=list)


class QAClaimHumanAssessment(StrictModel):
    system_claim_id: str = Field(min_length=1, max_length=160)
    label: Literal[
        "correct_supported",
        "correct_but_uncited",
        "unsupported",
        "contradictory",
        "irrelevant",
    ]
    matched_gold_claim_ids: list[str] = Field(default_factory=list)
    citations: list[QACitationHumanAssessment] = Field(default_factory=list)


class QAHumanReviewRecord(StrictModel):
    metadata: HumanReviewMetadata
    case_id: str = Field(min_length=1, max_length=160)
    system_answer_id: str = Field(min_length=1, max_length=160)
    claims: list[QAClaimHumanAssessment]
    missed_gold_claim_ids: list[str]
    conciseness_pass: bool
    answer_should_be_refused: bool
    system_refused: bool


class QAHumanScoreDataset(DatasetEnvelope):
    schema_version: Literal["courserag.qa-human-scores.v1"] = "courserag.qa-human-scores.v1"
    records: list[QAHumanReviewRecord] = Field(default_factory=list)


class CitationMigrationCase(ReviewableRecord):
    before_document_sha256: Sha256
    after_document_sha256: Sha256
    old_evidence_id: str
    expected_status: Literal["valid", "migrated", "needs_review", "invalid"]
    expected_new_evidence_id: str | None = None
    change_description: str = Field(min_length=1, max_length=2000)


class DS6CitationMigrationDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds6.v1"] = "courserag.ds6.v1"
    cases: list[CitationMigrationCase] = Field(default_factory=list)


class IncrementalWritebackCase(ReviewableRecord):
    operation: Literal[
        "rename_document",
        "modify_section",
        "add_section",
        "delete_section",
        "replace_ocr_page",
        "change_chunker",
        "change_kp_prompt",
        "change_embedding",
        "change_reranker",
        "writeback",
        "trigger_enrichment",
    ]
    affected_section_ids: list[str] = Field(default_factory=list)
    reusable_artifact_ids: list[str] = Field(default_factory=list)
    should_trigger_kp_extraction: bool
    should_create_index_version: bool
    preserve_review_status: bool


class DS7IncrementalWritebackDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds7.v1"] = "courserag.ds7.v1"
    cases: list[IncrementalWritebackCase] = Field(default_factory=list)


class PerformanceWorkloadCase(ReviewableRecord):
    workload_type: Literal[
        "full_build",
        "single_document_build",
        "single_section_update",
        "ocr_batch",
        "enrichment_batch",
        "search",
        "search_rerank",
        "context",
        "qa",
        "qa_abstention",
    ]
    referenced_case_ids: list[str] = Field(default_factory=list)
    cold_start: bool
    repetitions: int = Field(default=1, ge=1, le=1000)


class DS8PerformanceDataset(DatasetEnvelope):
    schema_version: Literal["courserag.ds8.v1"] = "courserag.ds8.v1"
    cases: list[PerformanceWorkloadCase] = Field(default_factory=list)
