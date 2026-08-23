from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from coursepilot.domain.context import ContextPackageRef


class ContextBindingStatus(StrEnum):
    COMPATIBLE = "compatible"
    STALE_PRIMARY_INDEX = "stale_primary_index"
    STALE_VERIFIED_OVERLAY = "stale_verified_overlay"
    MISSING_EVIDENCE = "missing_evidence"
    CHANGED_EVIDENCE = "changed_evidence"
    CROSS_COURSE_EVIDENCE = "cross_course_evidence"


class ContextBindingValidation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ContextBindingStatus
    stale: bool
    changed_evidence_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


def validate_context_binding(
    reference: ContextPackageRef,
    *,
    course_id: str,
    primary_index_version: str,
    verified_overlay_version: str | None,
    evidence_hashes: dict[str, str],
) -> ContextBindingValidation:
    if reference.course_id != course_id:
        return ContextBindingValidation(
            status=ContextBindingStatus.CROSS_COURSE_EVIDENCE,
            stale=True,
            reason="Context binding course differs from request course",
        )
    if reference.index_version != primary_index_version:
        return ContextBindingValidation(
            status=ContextBindingStatus.STALE_PRIMARY_INDEX,
            stale=True,
            reason="Primary index version changed",
        )
    if reference.verified_overlay_version != verified_overlay_version:
        return ContextBindingValidation(
            status=ContextBindingStatus.STALE_VERIFIED_OVERLAY,
            stale=True,
            reason="Verified overlay version changed",
        )
    missing = sorted(set(reference.evidence_ids) - set(evidence_hashes))
    changed = sorted(
        evidence_id
        for evidence_id, expected_hash in reference.evidence_versions.items()
        if evidence_id in evidence_hashes and evidence_hashes[evidence_id] != expected_hash
    )
    if missing:
        return ContextBindingValidation(
            status=ContextBindingStatus.MISSING_EVIDENCE,
            stale=True,
            changed_evidence_ids=missing,
            reason="Context Evidence is no longer resolvable",
        )
    if changed:
        return ContextBindingValidation(
            status=ContextBindingStatus.CHANGED_EVIDENCE,
            stale=True,
            changed_evidence_ids=changed,
            reason="Context Evidence content hash changed",
        )
    return ContextBindingValidation(status=ContextBindingStatus.COMPATIBLE, stale=False)
