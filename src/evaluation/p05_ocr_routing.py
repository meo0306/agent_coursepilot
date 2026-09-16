"""Source-grounded P05 routing evaluation on approved P04 selections and Native negatives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pydantic import JsonValue, TypeAdapter

from courserag.domain.document import ParsedDocumentIR
from courserag.evals.ocr_metrics import routing_metrics
from courserag.evals.schemas import (
    CorpusDocument,
    DS0CorpusDataset,
    DS1ParsingDataset,
    P04InputWorkPackage,
    PageGold,
)
from courserag.parsers.page_classifier import PageClassifierProfile
from courserag.parsers.pdf import StructuredPDFParser
from evaluation.contracts import MetricResult
from evaluation.corpus_fixtures import PDF_PRIMARY, sha256_file
from evaluation.io import atomic_write_json

_JSON_VALUE: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


def evaluate_p05_routing(
    *,
    repository_root: Path,
    dataset_root: Path,
    output_path: Path | None = None,
) -> dict[str, JsonValue]:
    repository_root = repository_root.resolve()
    dataset_root = dataset_root.resolve()
    ds0_path = dataset_root / "approved/ds0/pilot.json"
    p04_gold_path = dataset_root / "approved/ds1/p04_native_docx.json"
    work_package_path = dataset_root / "approved/work_packages/p04_input.json"
    ds0 = DS0CorpusDataset.model_validate_json(ds0_path.read_text(encoding="utf-8"))
    p04_gold = DS1ParsingDataset.model_validate_json(p04_gold_path.read_text(encoding="utf-8"))
    work_package = P04InputWorkPackage.model_validate_json(
        work_package_path.read_text(encoding="utf-8")
    )
    documents = {document.document_id: document for document in ds0.documents}
    required_ids = {PDF_PRIMARY} | {
        selection.document_id for selection in work_package.ocr_route_only_pages
    }
    parsed = {
        document_id: _parse(repository_root, documents[document_id])
        for document_id in sorted(required_ids)
    }
    predicted: dict[str, str] = {}
    gold: dict[str, str] = {}
    for selection in work_package.ocr_route_only_pages:
        page = parsed[selection.document_id].pages[selection.document_page_number - 1]
        if page.parse_decision is None:
            raise ValueError("P05 routing page has no PageParseDecision")
        predicted[selection.selection_id] = page.parse_decision.mode
        gold[selection.selection_id] = "ocr"
    native_pages = [record for record in p04_gold.records if isinstance(record, PageGold)]
    if len(native_pages) != 15 or any(record.document_id != PDF_PRIMARY for record in native_pages):
        raise ValueError("P05 routing negatives require the 15 Approved P04 Native PDF pages")
    for record in native_pages:
        page = parsed[PDF_PRIMARY].pages[record.page_number - 1]
        if page.parse_decision is None:
            raise ValueError("P05 Native routing page has no PageParseDecision")
        predicted[record.record_id] = page.parse_decision.mode
        gold[record.record_id] = "native"
    metrics = routing_metrics(predicted, gold)
    profile = PageClassifierProfile()
    serialized_metrics: dict[str, JsonValue] = {
        name: _JSON_VALUE.validate_python(
            value.model_dump(mode="json") if isinstance(value, MetricResult) else value
        )
        for name, value in metrics.items()
    }
    report: dict[str, JsonValue] = {
        "schema_version": "courserag.p05-routing-report.v1",
        "classifier_profile_sha256": profile.sha256,
        "inputs": {
            "approved_ds0_sha256": sha256_file(ds0_path),
            "approved_p04_ds1_sha256": sha256_file(p04_gold_path),
            "approved_p04_work_package_sha256": sha256_file(work_package_path),
        },
        "page_count": len(gold),
        "predictions": _JSON_VALUE.validate_python(predicted),
        "gold": _JSON_VALUE.validate_python(gold),
        "metrics": serialized_metrics,
    }
    if output_path is not None:
        atomic_write_json(output_path, report)
    return report


def _parse(repository_root: Path, document: CorpusDocument) -> ParsedDocumentIR:
    if document.repository_relative_path is None:
        raise ValueError("P05 routing document has no repository path")
    path = (repository_root / document.repository_relative_path).resolve()
    if not path.is_relative_to(repository_root) or sha256_file(path) != document.sha256:
        raise ValueError("P05 routing document differs from Approved DS0")
    return (
        StructuredPDFParser()
        .parse(
            path.read_bytes(),
            document_id=document.document_id,
            document_version_id=document.document_version,
            document_sha256=document.sha256,
        )
        .document
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate P05 OCR page routing.")
    parser.add_argument("--repository-root", type=Path, default=Path("."))
    parser.add_argument("--dataset-root", type=Path, default=Path("datasets/courserag_eval/v1"))
    parser.add_argument("--output", type=Path, default=Path("storage_eval/p05_routing/report.json"))
    args = parser.parse_args()
    result = evaluate_p05_routing(
        repository_root=args.repository_root,
        dataset_root=args.dataset_root,
        output_path=args.output,
    )
    print(json.dumps(result["metrics"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
