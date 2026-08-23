from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FaultOutcome:
    error_class: str
    user_status: str
    retryable: bool = False
    side_effect_count: int = 0


_FAULTS: dict[str, tuple[FaultOutcome, ...]] = {
    "main_timeout": (FaultOutcome("main_model_timeout", "failed_closed"),),
    "light_timeout": (FaultOutcome("light_model_timeout", "failed_closed"),),
    "rate_limit": (FaultOutcome("provider_rate_limited", "failed_closed"),),
    "invalid_structured_output": (
        FaultOutcome("invalid_json_syntax", "failed_closed"),
        FaultOutcome("structured_schema_missing_field", "failed_closed"),
    ),
    "prompt_token_limit": (FaultOutcome("prompt_too_long", "failed_closed"),),
    "main_structured_output_capability_mismatch": (
        FaultOutcome("unsupported_capability", "failed_closed"),
    ),
    "empty_or_incomplete_context": (
        FaultOutcome("empty_context", "needs_review"),
        FaultOutcome("incomplete_context", "needs_review"),
    ),
    "evidence_unresolvable": (FaultOutcome("unresolvable_evidence", "failed_closed"),),
    "stale_index_or_citation": (
        FaultOutcome("stale_index_version", "needs_review"),
        FaultOutcome("stale_citation_version", "needs_review"),
    ),
    "remote_timeout": (FaultOutcome("courserag_timeout", "failed_closed"),),
    "cross_course_evidence": (FaultOutcome("course_scope_violation", "failed_closed"),),
    "verified_primary_conflict": (FaultOutcome("source_conflict", "needs_review"),),
    "reranker_embedding_failure": (
        FaultOutcome("reranker_timeout", "failed_closed", retryable=True),
        FaultOutcome("embedding_unavailable", "failed_closed", retryable=True),
    ),
    "checkpoint_before_commit_crash": (
        FaultOutcome("recoverable_worker_failure", "failed_closed"),
    ),
    "checkpoint_after_commit_crash": (
        FaultOutcome(
            "recoverable_post_commit_interruption",
            "completed_after_resume",
            True,
            side_effect_count=1,
        ),
    ),
    "lease_takeover": (FaultOutcome("lease_takeover_recovered", "completed_after_resume", True),),
    "checkpointer_unavailable": (
        FaultOutcome("checkpoint_temporarily_unavailable", "completed_after_resume", True),
    ),
    "export_before_database_record": (
        FaultOutcome(
            "recoverable_post_commit_interruption",
            "completed_after_resume",
            True,
            side_effect_count=1,
        ),
    ),
    "writeback_response_lost": (
        FaultOutcome(
            "recoverable_post_commit_interruption",
            "completed_after_resume",
            True,
            side_effect_count=1,
        ),
    ),
    "duplicate_idempotency_key": (
        FaultOutcome(
            "recoverable_post_commit_interruption",
            "completed_after_resume",
            True,
            side_effect_count=1,
        ),
    ),
    "prompt_injection_material": (
        FaultOutcome("untrusted_instruction_flagged", "completed_with_untrusted_material_ignored"),
    ),
    "secret_extraction_request": (FaultOutcome("secret_access_denied", "failed_closed"),),
    "cross_course_request": (FaultOutcome("course_scope_violation", "failed_closed"),),
    "unauthorized_writeback": (FaultOutcome("authorization_denied", "failed_closed"),),
    "export_only_writeback": (FaultOutcome("authorization_denied", "failed_closed"),),
    "placeholder_injection": (FaultOutcome("untrusted_template_content", "failed_closed"),),
    "path_traversal_filename": (FaultOutcome("unsafe_path_rejected", "failed_closed"),),
    "secret_in_trace": (FaultOutcome("secret_redacted", "completed_with_redaction"),),
    "validator_bypass_request": (FaultOutcome("validation_required", "failed_closed"),),
    "oversized_feedback": (FaultOutcome("input_limit_exceeded", "failed_closed"),),
}


def inject_fault(scenario_family: str, variant_index: int) -> FaultOutcome:
    """Return the stable boundary outcome for an explicitly injected fault."""
    outcomes = _FAULTS.get(scenario_family)
    if outcomes is None:
        raise ValueError(f"Unsupported fault scenario: {scenario_family}")
    if variant_index < 0 or variant_index >= len(outcomes):
        raise ValueError(f"Unsupported fault variant: {scenario_family}[{variant_index}]")
    return outcomes[variant_index]
