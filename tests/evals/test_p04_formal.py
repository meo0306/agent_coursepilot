import json
from pathlib import Path

from courserag.evals.schemas import DocxPaginationGold
from evaluation.contracts import MetricResult, ReviewStatus
from evaluation.p04_formal import (
    PRIMARY_DOCX_ID,
    STRESS_DOCX_ID,
    _docx_source_unit_references,
    _load_approved_gold,
    _strict_gate,
)
from evaluation.p04_pilot import _load_inputs


def _metric(name: str, value: float | None) -> MetricResult:
    return MetricResult(
        name=name,
        value=value,
        numerator=value or 0,
        denominator=1 if value is not None else 0,
        applicable=value is not None,
    )


def test_formal_input_is_exact_approved_ds1_and_does_not_unlock_test() -> None:
    approved, approval = _load_approved_gold(Path.cwd())

    assert len(approved.records) == 55
    assert all(record.review_status is ReviewStatus.APPROVED for record in approved.records)
    assert approval.candidate_file_sha256 == (
        "7179ce9a48be77118ad68bfa7376bbe69e030f0e69ad0faba8435b0e0ee3c3aa"
    )
    assert approval.approved_file_sha256 == (
        "7e12edb2b66912d915b1d1ca3b7df873edb910cb7dcaf57d07872c83d84964ea"
    )
    dataset_root = Path("datasets/courserag_eval/v1")
    manifest = json.loads((dataset_root / "manifest.json").read_text(encoding="utf-8"))
    dev_ids = (dataset_root / "splits/dev_ids.txt").read_text(encoding="utf-8").split()
    test_ids = (dataset_root / "splits/test_ids.txt").read_text(encoding="utf-8").split()
    if manifest["gold_components"].get("ds5_retrieval") == "approved":
        assert len(dev_ids) == 60 and len(test_ids) == 40
    else:
        assert not dev_ids and not test_ids


def test_approved_docx_source_units_resolve_to_exact_ooxml_paragraphs() -> None:
    repository_root = Path.cwd()
    approved, _ = _load_approved_gold(repository_root)
    _, _, paths = _load_inputs(repository_root)
    references = {
        document_id: _docx_source_unit_references(paths[document_id].read_bytes())
        for document_id in (PRIMARY_DOCX_ID, STRESS_DOCX_ID)
    }

    for record in approved.records:
        if not isinstance(record, DocxPaginationGold):
            continue
        assert record.source_unit_id is not None
        reference = references[record.document_id][record.source_unit_id]
        assert reference.content_sha256 == record.source_text_sha256
        if record.document_id == PRIMARY_DOCX_ID:
            assert reference.paragraph_index == record.paragraph_index

    stress_references = references[STRESS_DOCX_ID]
    assert {
        source_index: stress_references[f"bookmark:src_p_{source_index:06d}"].paragraph_index
        for source_index in (19, 144, 1034, 1614, 3782)
    } == {19: 19, 144: 144, 1034: 1035, 1614: 1615, 3782: 3785}


def test_strict_gate_requires_all_absolute_checks_and_two_improvements() -> None:
    names = {
        "document_parse_success_rate": 1.0,
        "pdf_page_mapping_accuracy": 1.0,
        "docx_physical_page_accuracy": 1.0,
        "docx_display_page_label_accuracy": 1.0,
        "docx_section_page_accuracy": 1.0,
        "normalized_sample_text_recall": 0.99,
        "heading_detection_f1": 0.8,
        "section_boundary_accuracy": 0.7,
        "noise_detection_f1": 0.0,
        "table_cell_f1": 0.0,
    }
    p04 = {name: _metric(name, value) for name, value in names.items()}
    p04["pdf_page_mapping_accuracy"] = p04["pdf_page_mapping_accuracy"].model_copy(
        update={"numerator": 15, "denominator": 15}
    )
    p04["docx_physical_page_accuracy"] = p04["docx_physical_page_accuracy"].model_copy(
        update={"numerator": 10, "denominator": 10}
    )
    b0 = {name: _metric(name, 0.0) for name in names}
    b0["document_parse_success_rate"] = _metric("document_parse_success_rate", 1.0)
    b0["pdf_page_mapping_accuracy"] = _metric("pdf_page_mapping_accuracy", 1.0)
    gate = _strict_gate(
        p04,
        b0,
        renderer_repeat_match={PRIMARY_DOCX_ID: True, STRESS_DOCX_ID: True},
    )

    assert gate["passed"] is True
    assert gate["strictly_improved_core_metrics"] == [
        "heading_detection_f1",
        "section_boundary_accuracy",
    ]

    p04["normalized_sample_text_recall"] = _metric("normalized_sample_text_recall", 0.989)
    failed = _strict_gate(
        p04,
        b0,
        renderer_repeat_match={PRIMARY_DOCX_ID: True, STRESS_DOCX_ID: True},
    )
    assert failed["passed"] is False
    assert failed["checks"]["normalized_sample_text_recall_at_least_99_percent"] is False
