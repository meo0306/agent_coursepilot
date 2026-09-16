"""Deterministic DS3 Knowledge Point metrics without LLM judging."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from courserag.domain.knowledge_point import (
    KnowledgePointDraft,
    PublishScore,
    normalized_knowledge_point_name,
)
from courserag.evals.schemas import KnowledgePointRecord as GoldKnowledgePoint


@dataclass(frozen=True)
class KnowledgePointMatch:
    gold_kp_id: str
    system_stable_key: str
    basis: str


@dataclass(frozen=True)
class AmbiguousKnowledgePointMatch:
    system_stable_key: str
    candidate_gold_ids: tuple[str, ...]
    reason: str


def match_knowledge_points(
    gold: Sequence[GoldKnowledgePoint],
    system: Sequence[KnowledgePointDraft],
) -> tuple[tuple[KnowledgePointMatch, ...], tuple[AmbiguousKnowledgePointMatch, ...]]:
    """Return only unambiguous one-to-one exact name/Alias matches."""

    by_course: dict[str, list[GoldKnowledgePoint]] = {}
    for gold_item in gold:
        by_course.setdefault(gold_item.course_id, []).append(gold_item)
    proposed: list[KnowledgePointMatch] = []
    ambiguous: list[AmbiguousKnowledgePointMatch] = []
    for draft in system:
        candidates: dict[str, str] = {}
        system_canonical = normalized_knowledge_point_name(draft.canonical_name)
        system_aliases = {normalized_knowledge_point_name(alias) for alias in draft.aliases}
        for gold_item in by_course.get(draft.course_id, []):
            gold_canonical = normalized_knowledge_point_name(gold_item.canonical_name)
            gold_aliases = {normalized_knowledge_point_name(alias) for alias in gold_item.aliases}
            basis: str | None = None
            if system_canonical == gold_canonical:
                basis = "canonical_exact"
            elif system_canonical in gold_aliases:
                basis = "system_canonical_to_gold_alias"
            elif gold_canonical in system_aliases:
                basis = "system_alias_to_gold_canonical"
            elif system_aliases & gold_aliases:
                basis = "alias_exact"
            if basis is not None:
                candidates[gold_item.gold_kp_id] = basis
        if len(candidates) == 1:
            gold_id, basis = next(iter(candidates.items()))
            proposed.append(
                KnowledgePointMatch(
                    gold_kp_id=gold_id,
                    system_stable_key=draft.stable_key,
                    basis=basis,
                )
            )
        elif candidates:
            ambiguous.append(
                AmbiguousKnowledgePointMatch(
                    system_stable_key=draft.stable_key,
                    candidate_gold_ids=tuple(sorted(candidates)),
                    reason="multiple_gold_name_or_alias_matches",
                )
            )
    by_gold: dict[str, list[KnowledgePointMatch]] = {}
    for match in proposed:
        by_gold.setdefault(match.gold_kp_id, []).append(match)
    matches: list[KnowledgePointMatch] = []
    for gold_id, items in by_gold.items():
        if len(items) == 1:
            matches.append(items[0])
            continue
        for proposed_match in items:
            ambiguous.append(
                AmbiguousKnowledgePointMatch(
                    system_stable_key=proposed_match.system_stable_key,
                    candidate_gold_ids=(gold_id,),
                    reason="multiple_system_candidates_for_one_gold",
                )
            )
    return tuple(sorted(matches, key=lambda item: item.gold_kp_id)), tuple(
        sorted(ambiguous, key=lambda item: item.system_stable_key)
    )


def knowledge_point_metric_report(
    gold: Sequence[GoldKnowledgePoint],
    system: Sequence[KnowledgePointDraft],
    matches: Sequence[KnowledgePointMatch],
    *,
    evidence_adapter: Mapping[str, str] | None = None,
    resolvable_gold_ids: set[str] | None = None,
) -> dict[str, float | int | None]:
    selected_gold = (
        [item for item in gold if item.gold_kp_id in resolvable_gold_ids]
        if resolvable_gold_ids is not None
        else list(gold)
    )
    selected_ids = {item.gold_kp_id for item in selected_gold}
    selected_matches = [item for item in matches if item.gold_kp_id in selected_ids]
    matched_system = {item.system_stable_key for item in selected_matches}
    precision = _ratio(len(matched_system), len(system))
    recall = _ratio(len(selected_matches), len(selected_gold))
    report: dict[str, float | int | None] = {
        "gold_count": len(selected_gold),
        "system_count": len(system),
        "matched_count": len(selected_matches),
        "precision": precision,
        "recall": recall,
        "f1": _f1(precision, recall),
    }
    report.update(_alias_metrics(selected_gold, system, selected_matches))
    report.update(
        _evidence_metrics(
            selected_gold,
            system,
            selected_matches,
            evidence_adapter or {},
        )
    )
    return report


def threshold_report(
    gold: Sequence[GoldKnowledgePoint],
    system: Sequence[KnowledgePointDraft],
    matches: Sequence[KnowledgePointMatch],
    scores: Mapping[str, PublishScore],
    thresholds: Sequence[float],
) -> tuple[dict[str, float | int], ...]:
    matched_keys = {item.system_stable_key for item in matches}
    rows: list[dict[str, float | int]] = []
    for threshold in thresholds:
        published = [
            item
            for item in system
            if scores[item.stable_key].deterministic_checks_passed
            and scores[item.stable_key].total >= threshold
        ]
        true_positive = sum(item.stable_key in matched_keys for item in published)
        precision = _ratio(true_positive, len(published))
        recall = _ratio(true_positive, len(gold))
        rows.append(
            {
                "threshold": threshold,
                "published_count": len(published),
                "true_positive_count": true_positive,
                "precision": precision,
                "recall": recall,
                "f1": _f1(precision, recall),
            }
        )
    return tuple(rows)


def _alias_metrics(
    gold: Sequence[GoldKnowledgePoint],
    system: Sequence[KnowledgePointDraft],
    matches: Sequence[KnowledgePointMatch],
) -> dict[str, float | int]:
    gold_by_id = {item.gold_kp_id: item for item in gold}
    system_by_id = {item.stable_key: item for item in system}
    expected = 0
    recovered = 0
    for match in matches:
        expected_aliases = {
            normalized_knowledge_point_name(alias) for alias in gold_by_id[match.gold_kp_id].aliases
        }
        system_names = {
            normalized_knowledge_point_name(alias)
            for alias in system_by_id[match.system_stable_key].aliases
        }
        expected += len(expected_aliases)
        recovered += len(expected_aliases & system_names)
    return {
        "gold_alias_count": expected,
        "recovered_alias_count": recovered,
        "alias_recall": _ratio(recovered, expected),
    }


def _evidence_metrics(
    gold: Sequence[GoldKnowledgePoint],
    system: Sequence[KnowledgePointDraft],
    matches: Sequence[KnowledgePointMatch],
    adapter: Mapping[str, str],
) -> dict[str, float | int]:
    gold_by_id = {item.gold_kp_id: item for item in gold}
    system_by_id = {item.stable_key: item for item in system}
    correct = 0
    linked = 0
    expected = 0
    for match in matches:
        gold_ids = set(gold_by_id[match.gold_kp_id].evidence_ids)
        system_ids = {
            adapter[item.evidence_id]
            for item in system_by_id[match.system_stable_key].evidence_refs
            if item.evidence_id in adapter
        }
        correct += len(gold_ids & system_ids)
        linked += len(system_ids)
        expected += len(gold_ids)
    return {
        "mapped_system_evidence_link_count": linked,
        "correct_evidence_link_count": correct,
        "expected_gold_evidence_link_count": expected,
        "evidence_link_precision": _ratio(correct, linked),
        "evidence_link_recall": _ratio(correct, expected),
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 6) if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return round(2 * precision * recall / (precision + recall), 6) if precision + recall else 0.0
