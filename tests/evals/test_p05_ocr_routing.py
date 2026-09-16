from pathlib import Path

from evaluation.p05_ocr_routing import evaluate_p05_routing


def test_p05_routing_uses_15_approved_positive_and_15_native_negative_pages(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    report = evaluate_p05_routing(
        repository_root=repository_root,
        dataset_root=repository_root / "datasets/courserag_eval/v1",
        output_path=tmp_path / "routing.json",
    )
    metrics = report["metrics"]

    assert report["page_count"] == 30
    assert metrics["ocr_routing_recall"]["denominator"] == 15
    assert metrics["ocr_routing_precision"]["denominator"] >= 15
    assert (tmp_path / "routing.json").is_file()
