import pytest

from courserag.evals.parsing_metrics import (
    HeadingObservation,
    SectionBoundary,
    bbox_iou,
    binary_detection_metrics,
    character_error_rate,
    exact_mapping_accuracy,
    heading_metrics,
    parsing_success_rate,
    reading_order_kendall_tau,
    section_boundary_accuracy,
    table_structure_metrics,
)


def test_heading_and_section_metrics_keep_frozen_denominators() -> None:
    headings = heading_metrics(
        [
            HeadingObservation("doc", 1, "1. Start", 1),
            HeadingObservation("doc", 2, "Extra", 2),
        ],
        [
            HeadingObservation("doc", 1, "1. Start", 2),
            HeadingObservation("doc", 3, "3. End", 1),
        ],
    )
    assert headings["heading_detection_precision"].value == 0.5
    assert headings["heading_detection_recall"].value == 0.5
    assert headings["heading_detection_f1"].value == 0.5
    assert headings["heading_level_accuracy"].value == 0

    boundary = section_boundary_accuracy(
        [SectionBoundary("section", 2, 11)],
        [SectionBoundary("section", 1, 10), SectionBoundary("missing", 20, 30)],
    )
    assert boundary.value == 0.5
    assert boundary.details["tolerance_blocks"] == 1


def test_page_route_noise_success_and_mapping_metrics() -> None:
    route = binary_detection_metrics({"page-1", "page-3"}, {"page-1", "page-2"}, prefix="ocr_route")
    assert route["ocr_route_precision"].value == 0.5
    assert route["ocr_route_recall"].value == 0.5
    assert parsing_success_rate([True, False, True]).value == pytest.approx(2 / 3)
    assert exact_mapping_accuracy(
        [1, None, 3], [1, 2, 3], name="docx_physical_page_accuracy"
    ).value == pytest.approx(2 / 3)


def test_cer_kendall_table_and_bbox_metrics() -> None:
    assert character_error_rate("abX", "abc").value == pytest.approx(1 / 3)
    assert reading_order_kendall_tau(["a", "c", "b"], ["a", "b", "c"]).value == pytest.approx(1 / 3)
    table = table_structure_metrics([["A", "B"], ["C", "wrong"]], [["A", "B"], ["C", "D"]])
    assert table["table_row_column_structure_accuracy"].value == 1
    assert table["table_cell_precision"].value == 0.75
    assert table["table_cell_recall"].value == 0.75
    assert bbox_iou((0, 0, 2, 2), (1, 1, 3, 3)).value == pytest.approx(1 / 7)


def test_empty_gold_is_not_reported_as_perfect() -> None:
    assert heading_metrics([], [])["heading_detection_recall"].value is None
    assert character_error_rate("prediction", "").value is None
    assert reading_order_kendall_tau(["only"], ["only"]).value is None
