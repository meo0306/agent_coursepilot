"""DS1 parsing metrics with frozen denominators and explicit non-applicable results."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from evaluation.contracts import MetricResult


@dataclass(frozen=True)
class HeadingObservation:
    document_id: str
    page_number: int | None
    title: str
    level: int


@dataclass(frozen=True)
class SectionBoundary:
    section_id: str
    start_block_index: int
    end_block_index: int


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def binary_detection_metrics(
    predicted: set[str],
    gold: set[str],
    *,
    prefix: str,
) -> dict[str, MetricResult]:
    true_positive = len(predicted & gold)
    precision = MetricResult.ratio(f"{prefix}_precision", true_positive, len(predicted))
    recall = MetricResult.ratio(f"{prefix}_recall", true_positive, len(gold))
    f1_denominator = 2 * true_positive + len(predicted - gold) + len(gold - predicted)
    f1 = MetricResult.ratio(f"{prefix}_f1", 2 * true_positive, f1_denominator)
    return {precision.name: precision, recall.name: recall, f1.name: f1}


def heading_metrics(
    predicted: list[HeadingObservation],
    gold: list[HeadingObservation],
) -> dict[str, MetricResult]:
    def identity(item: HeadingObservation) -> tuple[str, int | None, str]:
        return item.document_id, item.page_number, _normalize(item.title)

    predicted_by_id = {identity(item): item for item in predicted}
    gold_by_id = {identity(item): item for item in gold}
    result = binary_detection_metrics(
        {repr(item) for item in predicted_by_id},
        {repr(item) for item in gold_by_id},
        prefix="heading_detection",
    )
    matches = predicted_by_id.keys() & gold_by_id.keys()
    result["heading_level_accuracy"] = MetricResult.ratio(
        "heading_level_accuracy",
        sum(predicted_by_id[key].level == gold_by_id[key].level for key in matches),
        len(matches),
    )
    return result


def section_boundary_accuracy(
    predicted: list[SectionBoundary],
    gold: list[SectionBoundary],
    *,
    tolerance_blocks: int = 1,
) -> MetricResult:
    if tolerance_blocks < 0:
        raise ValueError("section boundary tolerance cannot be negative")
    predicted_by_id = {item.section_id: item for item in predicted}
    correct = 0
    for expected in gold:
        actual = predicted_by_id.get(expected.section_id)
        if actual is not None and (
            abs(actual.start_block_index - expected.start_block_index) <= tolerance_blocks
            and abs(actual.end_block_index - expected.end_block_index) <= tolerance_blocks
        ):
            correct += 1
    return MetricResult.ratio(
        "section_boundary_accuracy",
        correct,
        len(gold),
        details={"tolerance_blocks": tolerance_blocks},
    )


def exact_mapping_accuracy(
    predicted: list[object | None],
    gold: list[object],
    *,
    name: str,
) -> MetricResult:
    if len(predicted) != len(gold):
        raise ValueError("predicted and Gold mappings must have equal cardinality")
    return MetricResult.ratio(
        name,
        sum(actual == expected for actual, expected in zip(predicted, gold, strict=True)),
        len(gold),
    )


def parsing_success_rate(successes: list[bool]) -> MetricResult:
    return MetricResult.ratio("document_parse_success_rate", sum(successes), len(successes))


def character_error_rate(predicted: str, gold: str) -> MetricResult:
    expected = unicodedata.normalize("NFKC", gold)
    actual = unicodedata.normalize("NFKC", predicted)
    distance = _levenshtein(actual, expected)
    return MetricResult.ratio("ocr_character_error_rate", distance, len(expected))


def _levenshtein(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def reading_order_kendall_tau(predicted: list[str], gold: list[str]) -> MetricResult:
    gold_position = {item: index for index, item in enumerate(gold)}
    common = [item for item in predicted if item in gold_position]
    concordant = 0
    discordant = 0
    for left_index, left in enumerate(common):
        for right in common[left_index + 1 :]:
            if gold_position[left] < gold_position[right]:
                concordant += 1
            else:
                discordant += 1
    pairs = concordant + discordant
    applicable = pairs > 0
    return MetricResult(
        name="reading_order_kendall_tau",
        value=(concordant - discordant) / pairs if applicable else None,
        numerator=concordant - discordant,
        denominator=pairs,
        applicable=applicable,
        details={"common_item_count": len(common)},
    )


def table_structure_metrics(
    predicted: list[list[str]],
    gold: list[list[str]],
) -> dict[str, MetricResult]:
    predicted_columns = max((len(row) for row in predicted), default=0)
    gold_columns = max((len(row) for row in gold), default=0)
    structure = MetricResult.ratio(
        "table_row_column_structure_accuracy",
        int(len(predicted) == len(gold) and predicted_columns == gold_columns),
        1,
    )
    predicted_cells = {
        (row_index, column_index, _normalize(value))
        for row_index, row in enumerate(predicted)
        for column_index, value in enumerate(row)
    }
    gold_cells = {
        (row_index, column_index, _normalize(value))
        for row_index, row in enumerate(gold)
        for column_index, value in enumerate(row)
    }
    cell_metrics = binary_detection_metrics(
        {repr(cell) for cell in predicted_cells},
        {repr(cell) for cell in gold_cells},
        prefix="table_cell",
    )
    return {structure.name: structure, **cell_metrics}


def bbox_iou(
    predicted: tuple[float, float, float, float],
    gold: tuple[float, float, float, float],
) -> MetricResult:
    intersection_width = max(0.0, min(predicted[2], gold[2]) - max(predicted[0], gold[0]))
    intersection_height = max(0.0, min(predicted[3], gold[3]) - max(predicted[1], gold[1]))
    intersection = intersection_width * intersection_height
    predicted_area = max(0.0, predicted[2] - predicted[0]) * max(0.0, predicted[3] - predicted[1])
    gold_area = max(0.0, gold[2] - gold[0]) * max(0.0, gold[3] - gold[1])
    union = predicted_area + gold_area - intersection
    return MetricResult.ratio("bounding_box_iou", intersection, union)
