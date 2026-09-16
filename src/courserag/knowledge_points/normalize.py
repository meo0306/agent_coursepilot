"""Deterministic Candidate validation, normalization and exact consolidation."""

from __future__ import annotations

import re
from collections import OrderedDict
from collections.abc import Iterable

from courserag.domain.knowledge_point import (
    KnowledgePointCandidate,
    KnowledgePointDraft,
    KnowledgePointEvidenceRef,
    SectionWindow,
    WindowExtractionResult,
    normalized_knowledge_point_name,
    stable_knowledge_point_key,
)

_PURE_NUMBERING = re.compile(r"^[\W_]*(?:第?[一二三四五六七八九十百千\d]+[章节条项]?)[\W_]*$")
_GENERIC_NAMES = frozenset(
    {
        "概述",
        "总结",
        "本章小结",
        "学习目标",
        "知识点",
        "introduction",
        "summary",
        "overview",
    }
)


def is_valid_candidate(candidate: KnowledgePointCandidate) -> bool:
    normalized = normalized_knowledge_point_name(candidate.canonical_name)
    if len(normalized) < 2 or len(normalized) > 240:
        return False
    if normalized in _GENERIC_NAMES or _PURE_NUMBERING.fullmatch(normalized):
        return False
    return bool(candidate.summary.strip() and candidate.evidence_refs)


def consolidate_candidates(
    windows: tuple[SectionWindow, ...],
    results: tuple[WindowExtractionResult, ...],
) -> tuple[KnowledgePointDraft, ...]:
    window_by_id = {item.window_id: item for item in windows}
    result_by_id = {item.window_id: item for item in results}
    if set(result_by_id) - set(window_by_id):
        raise ValueError("Extraction Result references an unknown Section Window")

    grouped: OrderedDict[tuple[str, str], list[tuple[SectionWindow, KnowledgePointCandidate]]] = (
        OrderedDict()
    )
    for window in windows:
        result = result_by_id.get(window.window_id)
        if result is None:
            continue
        allowed = {item.evidence_id for item in window.evidence}
        for candidate in result.candidates:
            if not is_valid_candidate(candidate):
                continue
            if not {item.evidence_id for item in candidate.evidence_refs}.issubset(allowed):
                raise ValueError("Knowledge Point Candidate references Evidence outside its Window")
            normalized = normalized_knowledge_point_name(candidate.canonical_name)
            grouped.setdefault((window.course_id, normalized), []).append((window, candidate))

    drafts: list[KnowledgePointDraft] = []
    for (course_id, normalized), entries in grouped.items():
        first_window, first = entries[0]
        aliases = _unique_strings(alias for _, candidate in entries for alias in candidate.aliases)
        evidence_refs = _merge_evidence_refs(
            item for _, candidate in entries for item in candidate.evidence_refs
        )
        primary_ids = tuple(item.evidence_id for item in evidence_refs if item.is_primary)
        sections = tuple(dict.fromkeys(window.section_id for window, _ in entries))
        window_ids = tuple(dict.fromkeys(window.window_id for window, _ in entries))
        ambiguity = tuple(
            dict.fromkeys(flag for _, candidate in entries for flag in candidate.ambiguity_flags)
        )
        parent_names = {
            normalized_knowledge_point_name(candidate.parent_name)
            for _, candidate in entries
            if candidate.parent_name
        }
        parent_name = first.parent_name if len(parent_names) == 1 else None
        if len(parent_names) > 1:
            ambiguity = (*ambiguity, "PARENT_CONFLICT")
        drafts.append(
            KnowledgePointDraft(
                knowledge_base_id=first_window.knowledge_base_id,
                course_id=course_id,
                stable_key=stable_knowledge_point_key(course_id, normalized, primary_ids),
                canonical_name=first.canonical_name.strip(),
                normalized_name=normalized,
                aliases=aliases,
                summary=max((candidate.summary.strip() for _, candidate in entries), key=len),
                parent_name=parent_name,
                section_ids=sections,
                window_ids=window_ids,
                evidence_refs=evidence_refs,
                ambiguity_flags=ambiguity,
                duplicate_count=max(0, len(entries) - 1),
            )
        )
    return tuple(drafts)


def _unique_strings(values: Iterable[str]) -> tuple[str, ...]:
    by_normalized: dict[str, str] = {}
    for value in values:
        text = value.strip()
        if text:
            by_normalized.setdefault(normalized_knowledge_point_name(text), text)
    return tuple(by_normalized.values())


def _merge_evidence_refs(
    values: Iterable[KnowledgePointEvidenceRef],
) -> tuple[KnowledgePointEvidenceRef, ...]:
    merged: OrderedDict[str, KnowledgePointEvidenceRef] = OrderedDict()
    for value in values:
        existing = merged.get(value.evidence_id)
        if existing is None:
            merged[value.evidence_id] = value
        elif value.is_primary and not existing.is_primary:
            merged[value.evidence_id] = value
    return tuple(merged.values())
