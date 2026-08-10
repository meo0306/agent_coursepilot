from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from evaluation.contracts import (
    HashedArtifact,
    ReviewableRecord,
    Sha256,
    SourceSpan,
    StrictModel,
)

P10Split = Literal["dev", "test"]


class P10DatasetEnvelope(StrictModel):
    dataset_id: str = Field(min_length=1, max_length=160)
    dataset_version: str = Field(min_length=1, max_length=80)


class P10SourceAnchor(StrictModel):
    course_id: str = Field(min_length=1, max_length=160)
    evidence_id: str = Field(min_length=1, max_length=160)
    evidence_record_sha256: Sha256
    exact_text: str = Field(min_length=1, max_length=16000)
    exact_text_sha256: Sha256
    source_span: SourceSpan


class P10DocumentState(StrictModel):
    document_id: str = Field(min_length=1, max_length=160)
    document_version: str = Field(min_length=1, max_length=120)
    document_sha256: Sha256
    artifact: HashedArtifact
    parser_profile_sha256: Sha256
    chunker_profile_sha256: Sha256


class P10CitationJudgment(StrictModel):
    judgment_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    old_anchor: P10SourceAnchor
    expected_status: Literal["valid", "migrated", "needs_review", "invalid"]
    expected_new_anchor: P10SourceAnchor | None = None
    allowed_candidate_anchor_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_expected_target(self) -> P10CitationJudgment:
        if self.expected_status in {"valid", "migrated"} and self.expected_new_anchor is None:
            raise ValueError("valid or migrated Citation Gold requires a new anchor")
        if self.expected_status == "invalid" and self.expected_new_anchor is not None:
            raise ValueError("invalid Citation Gold cannot name a new anchor")
        return self


class P10DS6Case(ReviewableRecord):
    split: P10Split
    transformation: Literal[
        "rename_document",
        "modify_paragraph",
        "insert_blank_page",
        "change_parser_profile",
        "change_chunker_profile",
        "replace_ocr_page",
        "duplicate_source_unit",
        "partial_text_delete",
        "delete_evidence",
    ]
    before: P10DocumentState
    after: P10DocumentState
    change_list: list[str] = Field(min_length=1)
    variant_exclusion_group: str = Field(min_length=1, max_length=160)
    searchable: bool = False
    judgments: list[P10CitationJudgment] = Field(min_length=1)


class P10DS6Dataset(P10DatasetEnvelope):
    schema_version: Literal["courserag.ds6-formal.v1"] = "courserag.ds6-formal.v1"
    cases: list[P10DS6Case] = Field(min_length=1)


class P10WritebackPayload(StrictModel):
    content_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    course_id: str = Field(min_length=1, max_length=160)
    content_type: Literal[
        "verified_question", "verified_answer_explanation", "verified_lesson_fragment"
    ]
    content_text: str = Field(min_length=1, max_length=16000)
    content_sha256: Sha256
    source_record_ids: list[str] = Field(min_length=1)
    source_record_sha256: list[Sha256] = Field(min_length=1)
    source_tier: Literal["teacher_verified"] = "teacher_verified"
    idempotency_key: str = Field(min_length=1, max_length=240)


class P10EnrichmentProbe(StrictModel):
    probe_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    record_count: int = Field(ge=0)
    token_count: int = Field(ge=0)
    age_seconds: int = Field(ge=0)
    manual_trigger: bool
    expected_trigger: bool
    trigger_reason: Literal["none", "record_count", "token_count", "age", "manual"]


class P10DS7Case(ReviewableRecord):
    split: P10Split
    operation: Literal[
        "rename_document",
        "modify_section",
        "add_section",
        "change_chunker",
        "change_kp_prompt",
        "change_embedding",
        "change_reranker",
        "delete_section",
        "replace_ocr_page",
        "writeback_lifecycle",
        "automatic_enrichment_boundaries",
        "manual_enrichment",
    ]
    source_course_id: str = Field(min_length=1, max_length=160)
    source_document_id: str = Field(min_length=1, max_length=160)
    source_fixture_sha256: Sha256
    steps: list[str] = Field(min_length=1)
    affected_section_ids: list[str] = Field(default_factory=list)
    unaffected_section_ids: list[str] = Field(default_factory=list)
    reusable_artifact_kinds: list[str] = Field(default_factory=list)
    invalidated_artifact_kinds: list[str] = Field(default_factory=list)
    should_trigger_kp_extraction: bool
    should_create_index_version: bool
    preserve_review_status: bool
    expected_change_coverage: float = Field(ge=0.0, le=1.0)
    writeback_payloads: list[P10WritebackPayload] = Field(default_factory=list)
    enrichment_probes: list[P10EnrichmentProbe] = Field(default_factory=list)
    expected_duplicate_writes: int = Field(default=0, ge=0)
    expected_primary_overwrites: int = Field(default=0, ge=0)


class P10DS7Dataset(P10DatasetEnvelope):
    schema_version: Literal["courserag.ds7-formal.v1"] = "courserag.ds7-formal.v1"
    cases: list[P10DS7Case] = Field(min_length=1)


class P10DS8Case(ReviewableRecord):
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
    cache_state: Literal["cold", "warm"]
    workload_domain: Literal["offline", "online"]
    referenced_case_ids: list[str] = Field(default_factory=list)
    resolved_dev_query_count: int = Field(default=0, ge=0)
    resolved_test_query_count: int = Field(default=0, ge=0)
    dev_ids_sha256: Sha256
    test_ids_sha256: Sha256
    test_id_resolution: Literal["deferred_until_test_lock"] = "deferred_until_test_lock"
    repetitions: int = Field(ge=1, le=1000)
    concurrency: int = Field(ge=1, le=100)
    timeout_seconds: int = Field(ge=1, le=86400)
    metrics: list[str] = Field(min_length=1)
    profile_refs: list[str] = Field(default_factory=list)


class P10DS8Dataset(P10DatasetEnvelope):
    schema_version: Literal["courserag.ds8-formal.v1"] = "courserag.ds8-formal.v1"
    cases: list[P10DS8Case] = Field(min_length=1)


class P10SecurityCase(ReviewableRecord):
    split: P10Split
    threat_category: Literal[
        "mime_mismatch",
        "unsupported_type",
        "encrypted_pdf",
        "compression_ratio",
        "path_traversal",
        "page_limit",
        "dpi_limit",
        "timeout",
        "cross_course_access",
        "unauthorized_write",
        "unauthorized_revoke",
        "prompt_injection",
        "secret_redaction",
    ]
    fixture: HashedArtifact | None = None
    semantic_content: Literal[False] = False
    input_description: str = Field(min_length=1, max_length=4000)
    expected_disposition: Literal["reject", "fail_closed", "preserve_and_flag", "redact"]
    expected_error_code: str | None = Field(default=None, max_length=160)
    expected_database_writes: int = Field(default=0, ge=0)
    expected_artifacts: int = Field(default=0, ge=0)
    expected_external_calls: int = Field(default=0, ge=0)
    expected_log_assertions: list[str] = Field(default_factory=list)


class P10SecurityDataset(P10DatasetEnvelope):
    schema_version: Literal["courserag.p10-security-control.v1"] = (
        "courserag.p10-security-control.v1"
    )
    cases: list[P10SecurityCase] = Field(min_length=1)


class P10ComponentSplit(StrictModel):
    component: Literal["ds6", "ds7", "security"]
    dev_ids: list[str]
    test_ids: list[str]


class P10ComponentSplitManifest(P10DatasetEnvelope):
    schema_version: Literal["courserag.p10-component-splits.v1"] = (
        "courserag.p10-component-splits.v1"
    )
    global_dev_ids_sha256: Sha256
    global_test_ids_sha256: Sha256
    test_locked: Literal[False] = False
    components: list[P10ComponentSplit] = Field(min_length=3, max_length=3)


class P10FixtureEntry(StrictModel):
    fixture_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    role: Literal["semantic_variant", "non_semantic_security_control"]
    artifact: HashedArtifact
    parent_document_id: str | None = Field(default=None, max_length=160)
    parent_sha256: Sha256 | None = None
    transformation: str = Field(min_length=1, max_length=4000)
    mutually_exclusive_with_parent: bool
    searchable: Literal[False] = False


class P10FixtureManifest(P10DatasetEnvelope):
    schema_version: Literal["courserag.p10-fixture-manifest.v1"] = (
        "courserag.p10-fixture-manifest.v1"
    )
    semantic_source_count: Literal[2] = 2
    generation_policy_sha256: Sha256
    fixtures: list[P10FixtureEntry] = Field(min_length=1)


class P10BundleManifest(P10DatasetEnvelope):
    schema_version: Literal["courserag.p10-input-bundle-manifest.v1"] = (
        "courserag.p10-input-bundle-manifest.v1"
    )
    revision: int = Field(default=1, ge=1)
    review_ui_revision: Literal[2] = 2
    bundle_sha256: Sha256
    approval_scope: Literal["p10_input_gold_only"] = "p10_input_gold_only"
    candidates: dict[str, HashedArtifact]
    candidate_record_sha256: dict[str, dict[str, Sha256]]
    fixture_manifest: HashedArtifact
    component_splits: HashedArtifact
    test_freeze_protocol: HashedArtifact
    upstream_approved: dict[str, HashedArtifact]
    preserved_p09: dict[str, HashedArtifact]
    first_review_ids: list[str] = Field(min_length=1)
    second_review_ids: list[str] = Field(min_length=1)
    review_pack_relative_path: str = Field(min_length=1, max_length=1024)
    review_pack_index_sha256: Sha256
    second_review_index_sha256: Sha256
    l0_zero_tolerance: list[str] = Field(min_length=1)
    l1_thresholds: dict[str, float]


class P10ReviewDecision(StrictModel):
    record_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    decision: Literal["pass", "return"]
    notes: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def validate_return_note(self) -> P10ReviewDecision:
        if self.decision == "return" and not self.notes.strip():
            raise ValueError("returned P10 records require notes")
        return self


class P10ReviewDecisions(P10DatasetEnvelope):
    schema_version: Literal["courserag.p10-review-decisions.v1"] = (
        "courserag.p10-review-decisions.v1"
    )
    bundle_sha256: Sha256
    review_pass: Literal["first", "second"]
    expected_record_ids: list[str] = Field(min_length=1)
    decisions: list[P10ReviewDecision]
    reviewer_id: str | None = Field(default=None, max_length=160)
    reviewed_at: datetime | None = None
    attestation_source: Literal["review_export", "course_owner_conversation_attestation"] = (
        "review_export"
    )
    attestation_statement: str | None = Field(default=None, max_length=4000)
    attestation_statement_sha256: Sha256 | None = None

    @model_validator(mode="after")
    def validate_complete_review(self) -> P10ReviewDecisions:
        decision_ids = [item.record_id for item in self.decisions]
        if len(self.expected_record_ids) != len(set(self.expected_record_ids)):
            raise ValueError("P10 expected review IDs must be unique")
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("P10 review decisions must be unique")
        if set(decision_ids) != set(self.expected_record_ids):
            raise ValueError("P10 review decisions must exactly cover expected IDs")
        if (self.reviewer_id is None) != (self.reviewed_at is None):
            raise ValueError("P10 reviewer and review time must be supplied together")
        has_statement = self.attestation_statement is not None
        has_statement_hash = self.attestation_statement_sha256 is not None
        if self.attestation_source == "review_export":
            if has_statement or has_statement_hash:
                raise ValueError("exported reviews cannot carry a conversation attestation")
        else:
            if self.attestation_statement is None or self.attestation_statement_sha256 is None:
                raise ValueError("conversation attestations require a statement and SHA-256")
            statement_hash = hashlib.sha256(self.attestation_statement.encode("utf-8")).hexdigest()
            if statement_hash != self.attestation_statement_sha256:
                raise ValueError("conversation attestation statement SHA-256 differs")
        return self


class P10BundleApproval(P10DatasetEnvelope):
    schema_version: Literal["courserag.p10-input-bundle-approval.v1"] = (
        "courserag.p10-input-bundle-approval.v1"
    )
    bundle_sha256: Sha256
    reviewer_id: str = Field(min_length=1, max_length=160)
    reviewed_at: datetime
    review_id: str = Field(pattern=r"^[A-Za-z0-9_.:-]+$", max_length=160)
    candidates: dict[str, HashedArtifact]
    approved: dict[str, HashedArtifact]
    approved_record_sha256: dict[str, dict[str, Sha256]]
    first_review_decisions: HashedArtifact
    second_review_decisions: HashedArtifact
    notes: str = Field(default="", max_length=4000)
