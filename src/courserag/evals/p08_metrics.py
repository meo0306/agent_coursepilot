from __future__ import annotations

import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from courserag.evals.schemas import RetrievalQACase


class RetrievalEvalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    evidence_ids: list[str] = Field(default_factory=list)
    score: float = 0.0


def retrieval_case_metrics(
    case: RetrievalQACase, hits: Sequence[RetrievalEvalHit]
) -> dict[str, float]:
    relevant = {item for item, value in case.graded_relevance.items() if value > 0}
    required = {item for item, value in case.graded_relevance.items() if value == 2}
    hard_negatives = set(case.hard_negative_evidence_ids)
    metrics: dict[str, float] = {}
    for k in (5, 10):
        unique = _unique_evidence(hits[:k])
        matched = relevant & unique
        metrics[f"hit@{k}"] = float(bool(matched))
        metrics[f"recall@{k}"] = len(matched) / len(relevant) if relevant else float(not matched)
        metrics[f"precision@{k}"] = len(matched) / max(1, len(unique))
    first_required = next(
        (rank for rank, hit in enumerate(hits[:10], start=1) if required & set(hit.evidence_ids)),
        None,
    )
    metrics["mrr@10"] = 0.0 if first_required is None else 1.0 / first_required
    metrics["ndcg@10"] = _ndcg(case, hits[:10])
    for k in (5, 8, 10):
        resolved = _unique_evidence(hits[:k])
        groups = case.gold_evidence_groups
        metrics[f"complete_group_recall@{k}"] = (
            sum(set(group.required_evidence_ids) <= resolved for group in groups) / len(groups)
            if groups
            else 1.0
        )
    top10 = _unique_evidence(hits[:10])
    metrics["hard_negative_intrusion@10"] = float(bool(top10 & hard_negatives))
    return metrics


def aggregate_metrics(rows: Sequence[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    names = sorted({name for row in rows for name in row})
    return {name: sum(row.get(name, 0.0) for row in rows) / len(rows) for name in names}


def rejection_curve(
    cases: Sequence[RetrievalQACase],
    hits_by_case: dict[str, Sequence[RetrievalEvalHit]],
) -> list[dict[str, float]]:
    thresholds = sorted({hit.score for hits in hits_by_case.values() for hit in hits[:1]} | {0.0})
    output: list[dict[str, float]] = []
    for threshold in thresholds:
        correct = 0
        for case in cases:
            hits = hits_by_case.get(case.record_id, ())
            accepted = bool(hits and hits[0].score >= threshold)
            correct += accepted == case.answerable
        output.append(
            {"threshold": threshold, "answerability_accuracy": correct / max(1, len(cases))}
        )
    return output


def _unique_evidence(hits: Sequence[RetrievalEvalHit]) -> set[str]:
    return {evidence_id for hit in hits for evidence_id in hit.evidence_ids}


def _ndcg(case: RetrievalQACase, hits: Sequence[RetrievalEvalHit]) -> float:
    seen: set[str] = set()
    gains: list[int] = []
    for hit in hits:
        new = set(hit.evidence_ids) - seen
        seen.update(new)
        gains.append(max((case.graded_relevance.get(item, 0) for item in new), default=0))
    dcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(gains, start=1))
    ideal = sorted(case.graded_relevance.values(), reverse=True)[: len(hits)]
    idcg = sum((2**gain - 1) / math.log2(rank + 1) for rank, gain in enumerate(ideal, start=1))
    return dcg / idcg if idcg else float(not any(gains))
