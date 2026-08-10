"""Non-generic P05 OCR routing, region, and resource metrics."""

from __future__ import annotations

import math
import statistics
import unicodedata
from collections.abc import Mapping, Sequence

from pydantic import JsonValue

from courserag.evals.parsing_metrics import (
    bbox_iou,
    character_error_rate,
    reading_order_kendall_tau,
)
from courserag.evals.schemas import OCRGold
from courserag.parsers.ocr.types import OCRPageResult
from evaluation.contracts import MetricResult


def routing_metrics(
    predicted: Mapping[str, str],
    gold: Mapping[str, str],
) -> dict[str, MetricResult | dict[str, dict[str, int]]]:
    states = ("native", "ocr", "hybrid")
    if set(predicted) != set(gold):
        raise ValueError("routing predictions and Gold must contain the same page IDs")
    if any(value not in states for value in [*predicted.values(), *gold.values()]):
        raise ValueError("routing states must be native, ocr, or hybrid")
    confusion = {
        expected: {
            actual: sum(
                gold[page_id] == expected and predicted[page_id] == actual for page_id in gold
            )
            for actual in states
        }
        for expected in states
    }
    predicted_positive = {page_id for page_id, mode in predicted.items() if mode != "native"}
    gold_positive = {page_id for page_id, mode in gold.items() if mode != "native"}
    true_positive = len(predicted_positive & gold_positive)
    precision = MetricResult.ratio("ocr_routing_precision", true_positive, len(predicted_positive))
    recall = MetricResult.ratio("ocr_routing_recall", true_positive, len(gold_positive))
    f1 = MetricResult.ratio(
        "ocr_routing_f1",
        2 * true_positive,
        2 * true_positive
        + len(predicted_positive - gold_positive)
        + len(gold_positive - predicted_positive),
    )
    return {precision.name: precision, recall.name: recall, f1.name: f1, "confusion": confusion}


def evaluate_ocr_results(
    gold_records: Sequence[OCRGold],
    results: Sequence[OCRPageResult],
) -> dict[str, JsonValue]:
    if len(gold_records) != len(results):
        raise ValueError("OCR results and Gold must have equal cardinality")
    gold_by_id = {record.record_id: record for record in gold_records}
    result_by_id = {result.page_id: result for result in results}
    if set(gold_by_id) != set(result_by_id):
        raise ValueError("OCR result page IDs must match Gold record IDs")
    body_macro_cer: list[float] = []
    body_edit_total = 0.0
    body_character_total = 0.0
    raw_macro_cer: list[float] = []
    raw_edit_total = 0.0
    raw_character_total = 0.0
    region_ious: list[float] = []
    region_cer_values: list[float] = []
    recalled_regions = 0
    gold_region_count = 0
    excluded_region_count = 0
    predicted_excluded_region_count = 0
    reading_order_values: list[float] = []
    latencies: list[int] = []
    for record_id, gold in gold_by_id.items():
        result = result_by_id[record_id]
        if result.image_sha256 != gold.image_sha256:
            raise ValueError("OCR result image Hash differs from Approved Gold")
        excluded_regions = [region for region in gold.regions if not region.include_in_body_text]
        body_results = [
            region
            for region in result.regions
            if not any(
                _prediction_belongs_to_excluded_region(region.pixel_bbox, excluded.bbox)
                for excluded in excluded_regions
            )
        ]
        predicted_excluded_region_count += len(result.regions) - len(body_results)
        excluded_region_count += len(excluded_regions)
        expected_body = _normalize_gold(gold.gold_text, gold)
        actual_body = _normalize_gold(
            "\n".join(region.text for region in body_results),
            gold,
        )
        body_cer = character_error_rate(actual_body, expected_body)
        body_edit_total += body_cer.numerator
        body_character_total += body_cer.denominator
        if body_cer.value is not None:
            body_macro_cer.append(body_cer.value)
        expected_raw = _normalize_gold(gold.raw_text, gold)
        actual_raw = _normalize_gold(result.text, gold)
        raw_cer = character_error_rate(actual_raw, expected_raw)
        raw_edit_total += raw_cer.numerator
        raw_character_total += raw_cer.denominator
        if raw_cer.value is not None:
            raw_macro_cer.append(raw_cer.value)
        latencies.append(result.duration_ms)
        available = list(body_results)
        matched_by_result_id: dict[str, str] = {}
        for region in (item for item in gold.regions if item.include_in_body_text):
            gold_region_count += 1
            if not available:
                continue
            scores = [bbox_iou(item.pixel_bbox, region.bbox).value or 0.0 for item in available]
            best_index = max(range(len(scores)), key=scores.__getitem__)
            best_iou = scores[best_index]
            best = available.pop(best_index)
            region_ious.append(best_iou)
            if best_iou >= 0.50:
                recalled_regions += 1
                matched_by_result_id[best.region_id] = region.region_id
                region_cer = character_error_rate(
                    _normalize_gold(best.text, gold),
                    _normalize_gold(region.gold_text or "", gold),
                )
                if region_cer.value is not None:
                    region_cer_values.append(region_cer.value)
        predicted_order = [
            matched_by_result_id[region.region_id]
            for region in body_results
            if region.region_id in matched_by_result_id
        ]
        order_metric = reading_order_kendall_tau(predicted_order, gold.reading_order)
        if order_metric.value is not None:
            reading_order_values.append(order_metric.value)
    return {
        "macro_cer": statistics.fmean(body_macro_cer) if body_macro_cer else None,
        "micro_cer": (body_edit_total / body_character_total if body_character_total else None),
        "body_macro_cer": statistics.fmean(body_macro_cer) if body_macro_cer else None,
        "body_micro_cer": (
            body_edit_total / body_character_total if body_character_total else None
        ),
        "raw_macro_cer": statistics.fmean(raw_macro_cer) if raw_macro_cer else None,
        "raw_micro_cer": raw_edit_total / raw_character_total if raw_character_total else None,
        "region_text_cer": (statistics.fmean(region_cer_values) if region_cer_values else None),
        "mean_bbox_iou": statistics.fmean(region_ious) if region_ious else None,
        "region_recall_at_iou_0_5": (
            recalled_regions / gold_region_count if gold_region_count else None
        ),
        "body_reading_order_kendall_tau": (
            statistics.fmean(reading_order_values) if reading_order_values else None
        ),
        "gold_body_region_count": gold_region_count,
        "gold_excluded_region_count": excluded_region_count,
        "predicted_excluded_region_count": predicted_excluded_region_count,
        "empty_page_count": sum(not result.regions for result in results),
        "warning_page_count": sum(result.status == "ready_with_warnings" for result in results),
        "failed_page_count": sum(result.status == "failed" for result in results),
        "low_confidence_page_count": sum(
            any(
                warning.code in {"OCR_LOW_CONFIDENCE", "OCR_LOW_REGION_CONFIDENCE"}
                for warning in result.warnings
            )
            for result in results
        ),
        "resource_limit_page_count": sum(
            any(warning.code == "OCR_RESOURCE_LIMIT" for warning in result.warnings)
            for result in results
        ),
        "provider_failure_page_count": sum(
            any(warning.code == "OCR_PAGE_FAILED" for warning in result.warnings)
            for result in results
        ),
        "p50_latency_ms": _percentile(latencies, 0.50),
        "p95_latency_ms": _percentile(latencies, 0.95),
        "peak_memory_bytes": max((result.peak_memory_bytes for result in results), default=0),
        "sample_count": len(results),
    }


def _prediction_belongs_to_excluded_region(
    predicted: tuple[int, int, int, int],
    excluded: tuple[float, float, float, float],
) -> bool:
    center_x = (predicted[0] + predicted[2]) / 2
    center_y = (predicted[1] + predicted[3]) / 2
    if excluded[0] <= center_x <= excluded[2] and excluded[1] <= center_y <= excluded[3]:
        return True
    intersection = max(0.0, min(predicted[2], excluded[2]) - max(predicted[0], excluded[0])) * max(
        0.0,
        min(predicted[3], excluded[3]) - max(predicted[1], excluded[1]),
    )
    area = (predicted[2] - predicted[0]) * (predicted[3] - predicted[1])
    return intersection / area >= 0.50 if area else False


def _normalize_gold(text: str, gold: OCRGold) -> str:
    value = unicodedata.normalize("NFKC", text) if gold.normalize_full_width else text
    if gold.ignore_line_break_difference:
        value = " ".join(value.split())
    if gold.remove_spaces_between_chinese:
        characters: list[str] = []
        for index, character in enumerate(value):
            if character == " " and index > 0 and index + 1 < len(value):
                if _is_cjk(value[index - 1]) and _is_cjk(value[index + 1]):
                    continue
            characters.append(character)
        value = "".join(characters)
    return value


def _is_cjk(character: str) -> bool:
    return "\u3400" <= character <= "\u9fff"


def _percentile(values: Sequence[int], quantile: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]
