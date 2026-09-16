"""Deterministic P18 aggregate metrics over frozen result rows."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean
from typing import Any


def percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def aggregate_run_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate without dropping failed or fallback samples."""

    by_track: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_track[str(row["track"])].append(row)
    tracks: dict[str, dict[str, Any]] = {}
    for track, items in sorted(by_track.items()):
        latencies = [float(item["latency_ms"]) for item in items if item.get("latency_ms")]
        tracks[track] = {
            "samples": len(items),
            "succeeded": sum(item.get("status") == "succeeded" for item in items),
            "failed": sum(item.get("status") != "succeeded" for item in items),
            "fallback_samples": sum(bool(item.get("fallback")) for item in items),
            "contract_pass_rate": _rate(items, "contract_pass"),
            "citation_resolvability": _rate(items, "citations_resolvable"),
            "render_success_rate": _rate(items, "render_success"),
            "trace_completeness": _rate(items, "trace_complete"),
            "p50_latency_ms": percentile(latencies, 0.50),
            "p95_latency_ms": percentile(latencies, 0.95),
            "input_tokens": sum(int(item.get("input_tokens", 0)) for item in items),
            "output_tokens": sum(int(item.get("output_tokens", 0)) for item in items),
            "cost_cny": round(sum(float(item.get("cost_cny", 0)) for item in items), 6),
        }
    return {"sample_count": len(rows), "tracks": tracks, "l0": _l0(rows)}


def aggregate_human_reviews(records: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [score for item in records for score in item.get("rubric_scores", {}).values()]
    burdens = [int(item["edit_burden"]) for item in records]
    acceptable = sum(
        item.get("artifact_status", item.get("question_status", item.get("slide_status")))
        in {"accepted", "minor_edit"}
        for item in records
    )
    return {
        "review_units": len(records),
        "acceptable_rate": acceptable / len(records) if records else None,
        "mean_rubric": mean(scores) if scores else None,
        "mean_edit_burden": mean(burdens) if burdens else None,
        "critical_defects": sum(bool(item.get("critical_defect")) for item in records),
    }


def _rate(items: list[dict[str, Any]], key: str) -> float | None:
    applicable = [item for item in items if item.get(key) is not None]
    return sum(bool(item[key]) for item in applicable) / len(applicable) if applicable else None


def _l0(rows: list[dict[str, Any]]) -> dict[str, int]:
    keys = (
        "cross_course_events",
        "unauthorized_actions",
        "secret_leaks",
        "duplicate_side_effects",
        "silent_fallbacks",
        "unresolved_citations",
        "dangerous_tool_executions",
    )
    return {key: sum(int(row.get(key, 0)) for row in rows) for key in keys}
