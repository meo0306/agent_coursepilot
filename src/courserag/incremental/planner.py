"""Deterministic Section diff and artifact impact planning.

Ambiguity always expands work.  Reuse is never inferred from a missing match.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ChangeKind(StrEnum):
    UNCHANGED = "unchanged"
    MOVED_OR_RENAMED = "moved_or_renamed"
    MODIFIED = "modified"
    ADDED = "added"
    REMOVED = "removed"
    AMBIGUOUS = "ambiguous"


class ImpactAction(StrEnum):
    REUSE = "reuse"
    REPROCESS = "reprocess"


class ArtifactKind(StrEnum):
    PARSED_SECTION = "parsed_section"
    EVIDENCE = "evidence"
    CHUNK = "chunk"
    KNOWLEDGE_POINT_CANDIDATE = "knowledge_point_candidate"
    EMBEDDING = "embedding"
    SPARSE_INDEX = "sparse_index"


class IncrementalProfileChange(StrictFrozenModel):
    parser_or_ocr: bool = False
    chunker: bool = False
    knowledge_point: bool = False
    embedding: bool = False
    reranker: bool = False


class SectionSnapshot(StrictFrozenModel):
    section_id: str = Field(min_length=1, max_length=160)
    stable_path: str = Field(min_length=1, max_length=1024)
    parent_path: str | None = Field(default=None, max_length=1024)
    heading: str = ""
    ordinal: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    block_sha256: tuple[str, ...] = ()

    @property
    def structure_key(self) -> str:
        payload = [self.parent_path, _normalize(self.heading), list(self.block_sha256)]
        return hashlib.sha256(_canonical(payload)).hexdigest()


class SectionImpact(StrictFrozenModel):
    change_kind: ChangeKind
    before_section_id: str | None = None
    after_section_id: str | None = None
    before_path: str | None = None
    after_path: str | None = None
    action: ImpactAction
    boundary_expansion: bool = False
    reusable_artifacts: tuple[ArtifactKind, ...] = ()
    invalidated_artifacts: tuple[ArtifactKind, ...] = ()
    reason_codes: tuple[str, ...] = ()


class IncrementalBuildPlan(StrictFrozenModel):
    source_document_id: str = Field(min_length=1)
    source_version_id: str = Field(min_length=1)
    target_version_id: str = Field(min_length=1)
    profile_change: IncrementalProfileChange
    impacts: tuple[SectionImpact, ...]
    theoretical_reusable_artifacts: int = Field(ge=0)
    planned_reused_artifacts: int = Field(ge=0)
    change_coverage: float = Field(ge=0, le=1)

    @property
    def plan_sha256(self) -> str:
        return hashlib.sha256(
            _canonical(self.model_dump(mode="json", exclude={"plan_sha256"}))
        ).hexdigest()

    @property
    def reused_artifact_ratio(self) -> float:
        if self.theoretical_reusable_artifacts == 0:
            return 1.0
        return self.planned_reused_artifacts / self.theoretical_reusable_artifacts

    @model_validator(mode="after")
    def validate_reuse(self) -> IncrementalBuildPlan:
        if self.planned_reused_artifacts > self.theoretical_reusable_artifacts:
            raise ValueError("planned reuse cannot exceed theoretical reuse")
        if self.change_coverage < 1 and self.planned_reused_artifacts:
            raise ValueError("artifact reuse requires complete change coverage")
        return self


_ALL_ARTIFACTS = tuple(ArtifactKind)


def build_incremental_plan(
    *,
    source_document_id: str,
    source_version_id: str,
    target_version_id: str,
    before: tuple[SectionSnapshot, ...],
    after: tuple[SectionSnapshot, ...],
    profile_change: IncrementalProfileChange | None = None,
) -> IncrementalBuildPlan:
    profile_change = profile_change or IncrementalProfileChange()
    _require_unique(before, "before")
    _require_unique(after, "after")
    raw = _match_sections(before, after)
    expanded = _apply_boundary_and_profile_impacts(raw, after, profile_change)
    theoretical = sum(len(item.reusable_artifacts) for item in expanded)
    planned = (
        theoretical if all(item.change_kind is not ChangeKind.AMBIGUOUS for item in expanded) else 0
    )
    coverage = 1.0
    return IncrementalBuildPlan(
        source_document_id=source_document_id,
        source_version_id=source_version_id,
        target_version_id=target_version_id,
        profile_change=profile_change,
        impacts=tuple(expanded),
        theoretical_reusable_artifacts=theoretical,
        planned_reused_artifacts=planned,
        change_coverage=coverage,
    )


def _match_sections(
    before: tuple[SectionSnapshot, ...], after: tuple[SectionSnapshot, ...]
) -> list[SectionImpact]:
    after_by_path = {item.stable_path: item for item in after}
    content_counts_before = Counter(item.content_sha256 for item in before)
    content_counts_after = Counter(item.content_sha256 for item in after)
    after_by_content: dict[str, list[SectionSnapshot]] = defaultdict(list)
    after_by_structure: dict[str, list[SectionSnapshot]] = defaultdict(list)
    for item in after:
        after_by_content[item.content_sha256].append(item)
        after_by_structure[item.structure_key].append(item)

    matched_after: set[str] = set()
    impacts: list[SectionImpact] = []
    for old in sorted(before, key=lambda item: item.ordinal):
        same_path = after_by_path.get(old.stable_path)
        if same_path is not None and same_path.section_id not in matched_after:
            matched_after.add(same_path.section_id)
            kind = (
                ChangeKind.UNCHANGED
                if same_path.content_sha256 == old.content_sha256
                else ChangeKind.MODIFIED
            )
            impacts.append(_impact(old, same_path, kind))
            continue
        content_matches = [
            item
            for item in after_by_content[old.content_sha256]
            if item.section_id not in matched_after
        ]
        if (
            len(content_matches) == 1
            and content_counts_before[old.content_sha256] == 1
            and content_counts_after[old.content_sha256] == 1
        ):
            target = content_matches[0]
            matched_after.add(target.section_id)
            impacts.append(_impact(old, target, ChangeKind.MOVED_OR_RENAMED))
            continue
        structural = [
            item
            for item in after_by_structure[old.structure_key]
            if item.section_id not in matched_after
        ]
        if len(structural) == 1:
            target = structural[0]
            matched_after.add(target.section_id)
            impacts.append(_impact(old, target, ChangeKind.MODIFIED))
            continue
        if len(content_matches) > 1 or len(structural) > 1:
            impacts.append(_impact(old, None, ChangeKind.AMBIGUOUS))
        else:
            impacts.append(_impact(old, None, ChangeKind.REMOVED))
    for item in sorted(after, key=lambda value: value.ordinal):
        if item.section_id not in matched_after:
            impacts.append(_impact(None, item, ChangeKind.ADDED))
    return impacts


def _impact(
    before: SectionSnapshot | None, after: SectionSnapshot | None, kind: ChangeKind
) -> SectionImpact:
    reusable: tuple[ArtifactKind, ...] = (
        _ALL_ARTIFACTS
        if kind
        in {
            ChangeKind.UNCHANGED,
            ChangeKind.MOVED_OR_RENAMED,
        }
        else ()
    )
    return SectionImpact(
        change_kind=kind,
        before_section_id=before.section_id if before else None,
        after_section_id=after.section_id if after else None,
        before_path=before.stable_path if before else None,
        after_path=after.stable_path if after else None,
        action=ImpactAction.REUSE if reusable else ImpactAction.REPROCESS,
        reusable_artifacts=reusable,
        invalidated_artifacts=() if reusable else _ALL_ARTIFACTS,
        reason_codes=(kind.value.upper(),),
    )


def _apply_boundary_and_profile_impacts(
    impacts: list[SectionImpact],
    after: tuple[SectionSnapshot, ...],
    profile: IncrementalProfileChange,
) -> list[SectionImpact]:
    by_after = {
        item.after_section_id: index for index, item in enumerate(impacts) if item.after_section_id
    }
    changed_ordinals = {
        section.ordinal
        for section in after
        if (impact_index := by_after.get(section.section_id)) is not None
        and impacts[impact_index].change_kind
        not in {
            ChangeKind.UNCHANGED,
            ChangeKind.MOVED_OR_RENAMED,
        }
    }
    boundary_ids = {
        section.section_id
        for section in after
        if any(abs(section.ordinal - changed) == 1 for changed in changed_ordinals)
    }
    output: list[SectionImpact] = []
    for item in impacts:
        invalidate = set(item.invalidated_artifacts)
        reusable = set(item.reusable_artifacts)
        reasons = list(item.reason_codes)
        boundary = item.after_section_id in boundary_ids and item.action is ImpactAction.REUSE
        if boundary:
            invalidate.update({ArtifactKind.CHUNK, ArtifactKind.SPARSE_INDEX})
            reusable.difference_update(invalidate)
            reasons.append("BOUNDARY_NEIGHBOR")
        if profile.parser_or_ocr:
            invalidate.update(_ALL_ARTIFACTS)
            reasons.append("PARSER_OR_OCR_PROFILE_CHANGED")
        else:
            if profile.chunker:
                invalidate.update(
                    {ArtifactKind.CHUNK, ArtifactKind.EMBEDDING, ArtifactKind.SPARSE_INDEX}
                )
                reasons.append("CHUNK_PROFILE_CHANGED")
            if profile.knowledge_point:
                invalidate.add(ArtifactKind.KNOWLEDGE_POINT_CANDIDATE)
                reasons.append("KNOWLEDGE_POINT_PROFILE_CHANGED")
            if profile.embedding:
                invalidate.add(ArtifactKind.EMBEDDING)
                reasons.append("EMBEDDING_PROFILE_CHANGED")
            if profile.reranker:
                reasons.append("RERANKER_PROFILE_NO_REBUILD")
        reusable.difference_update(invalidate)
        output.append(
            item.model_copy(
                update={
                    "action": ImpactAction.REUSE if reusable else ImpactAction.REPROCESS,
                    "boundary_expansion": boundary,
                    "reusable_artifacts": tuple(sorted(reusable, key=str)),
                    "invalidated_artifacts": tuple(sorted(invalidate, key=str)),
                    "reason_codes": tuple(dict.fromkeys(reasons)),
                }
            )
        )
    return output


def _require_unique(values: tuple[SectionSnapshot, ...], label: str) -> None:
    if len({item.section_id for item in values}) != len(values):
        raise ValueError(f"{label} Section IDs must be unique")
    if len({item.stable_path for item in values}) != len(values):
        raise ValueError(f"{label} Section paths must be unique")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
