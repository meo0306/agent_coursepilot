"""Approved-DS2-only B1/B2 Runner for Stable Evidence and Parent/Child Chunking."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from pydantic import JsonValue

from courserag.chunking.profile import load_chunk_profile
from courserag.chunking.splitter import ParentChildChunker
from courserag.chunking.tokenizer import LocalTokenizer
from courserag.domain.chunk import ChunkArtifact, ChunkProfile, ChunkRecord
from courserag.domain.document import ParsedDocumentIR, sha256_text
from courserag.domain.evidence import EvidenceArtifact, EvidenceRecord, normalize_evidence_text
from courserag.evals.p06_metrics import (
    EvidenceMatch,
    chunk_evidence_coverage,
    chunk_redundancy_rate,
    complete_semantic_unit_rate,
    cross_boundary_split_error_rate,
    evidence_resolving_rate,
    evidence_text_consistency,
    map_gold_to_system_evidence,
    ocr_provenance_preservation,
    page_bbox_consistency,
    parent_expansion_sufficiency,
    runtime_evidence_full_coverage,
)
from courserag.evals.schemas import (
    DS1ParsingDataset,
    DS2BatchApproval,
    DS2EvidenceDataset,
    OCRGold,
)
from courserag.evidence.builder import EvidenceBuilder, EvidenceBuilderProfile
from courserag.parsers.normalizer import merge_ocr_results
from courserag.parsers.ocr.types import OCRPageResult
from courserag.parsers.pagination import DocxPaginationRenderer, RendererProfile
from courserag.parsers.structure import enrich_document_structure
from evaluation.contracts import DatasetSplit, FallbackPolicy, HashedArtifact, RunIntent
from evaluation.io import atomic_write_json
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.p04_formal import PRIMARY_DOCX_ID, _parse_p04_docx
from evaluation.p04_pilot import (
    DATASET_ROOT,
    PRIMARY_PDF_RUNS,
    RENDERER_PROFILE,
    _git_state,
    _load_inputs,
    _parse_pdf,
)
from evaluation.runner import EvaluationRunner

APPROVED_DS2 = DATASET_ROOT / "approved/ds2/p06_evidence.json"
DS2_APPROVAL = DATASET_ROOT / "provenance/ds2_p06_approval.json"
APPROVED_P05 = DATASET_ROOT / "approved/ds1/p05_ocr.json"
DATASET_MANIFEST = DATASET_ROOT / "manifest.json"
PILOT_SPLIT = DATASET_ROOT / "splits/pilot_ids.txt"
P05_REPORT = Path("storage_eval/p05_ocr_pilot/rapidocr-default-v1-run-1/report.json")
CHUNK_PROFILE = Path("resources/chunk_profiles/parent_child_v1.json")
TOKENIZER_PATH = Path("deepseek_v3_tokenizer/deepseek_v3_tokenizer/tokenizer.json")
PDF_DOCUMENT_ID = "doc_ai_general_education_excerpt"


def run_p06_evaluation(
    *,
    repository_root: Path,
    output_dir: Path,
    run_id: str,
    resume: bool = False,
) -> Path:
    repository_root = repository_root.resolve()
    output_dir = output_dir.resolve()
    dataset_root = (repository_root / DATASET_ROOT).resolve()
    gold_path = repository_root / APPROVED_DS2
    approval_path = repository_root / DS2_APPROVAL
    approval = DS2BatchApproval.model_validate_json(approval_path.read_text(encoding="utf-8"))
    if approval.approved_file_sha256 != sha256_file(gold_path):
        raise ValueError("Approved DS2 file differs from exact owner approval")
    gold_dataset = DS2EvidenceDataset.model_validate_json(gold_path.read_text(encoding="utf-8"))
    if len(gold_dataset.evidence) != 120 or any(
        record.review_status.value != "approved" for record in gold_dataset.evidence
    ):
        raise ValueError("P06 Runner requires all 120 Approved DS2 records")
    profile = load_chunk_profile(repository_root / CHUNK_PROFILE)
    tokenizer = LocalTokenizer(
        repository_root / TOKENIZER_PATH,
        tokenizer_id=profile.tokenizer_id,
        expected_sha256=profile.tokenizer_sha256,
    )
    work_package, _, paths = _load_inputs(repository_root)
    bindings = {identity.document_id: identity for identity in work_package.identities}
    commit, dirty = _git_state(repository_root)
    input_paths = [
        gold_path,
        approval_path,
        repository_root / APPROVED_P05,
        repository_root / P05_REPORT,
        repository_root / CHUNK_PROFILE,
        repository_root / TOKENIZER_PATH,
        paths[PRIMARY_DOCX_ID],
        paths[PDF_DOCUMENT_ID],
        *(repository_root / path for path in PRIMARY_PDF_RUNS),
    ]
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(UTC),
        dataset=RunDatasetRef(
            dataset_id=gold_dataset.dataset_id,
            dataset_version=gold_dataset.dataset_version,
            split=DatasetSplit.PILOT,
            manifest_sha256=sha256_file(dataset_root / "manifest.json"),
            split_sha256=sha256_file(dataset_root / "splits/pilot_ids.txt"),
        ),
        intent=RunIntent.EVALUATION,
        tuning_enabled=False,
        git_commit=commit,
        git_dirty=dirty,
        input_artifacts=[_artifact(repository_root, path) for path in input_paths],
        component_versions={
            "evidence_builder": "semantic_units_v1",
            "parent_child_chunker": "1.0",
            "b1_flat_window": "1000_chars_150_overlap",
        },
        configuration={
            "chunk_profile_sha256": profile.profile_sha256,
            "tokenizer_sha256": profile.tokenizer_sha256,
            "gold_mapping": "post_output_source_unit_and_content_overlap",
            "automatic_tuning": False,
        },
        fallback_policy=FallbackPolicy.FAIL_RUN,
        random_seed=0,
        llm_as_judge=False,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(output_dir / "run_manifest.json", manifest.model_dump(mode="json"))
    runner = EvaluationRunner(
        manifest=manifest,
        checkpoint_path=output_dir / "checkpoint.json",
        partial_report_path=output_dir / "partial_report.json",
        final_report_path=output_dir / "report.json",
        dataset_root=dataset_root,
        resume=resume,
    )

    docx_binding = bindings[PRIMARY_DOCX_ID]
    pdf_binding = bindings[PDF_DOCUMENT_ID]
    renderer_profile = RendererProfile.load(repository_root / RENDERER_PROFILE)
    renderer = DocxPaginationRenderer(renderer_profile, font_resolver=lambda font: None)

    def docx_case() -> JsonValue:
        document, repeat_match = _parse_p04_docx(
            path=paths[PRIMARY_DOCX_ID],
            document_id=docx_binding.source_document_id,
            document_version_id=docx_binding.document_version_id,
            document_sha256=docx_binding.document_sha256,
            pdf_runs=PRIMARY_PDF_RUNS,
            repository_root=repository_root,
            renderer=renderer,
            low_confidence_threshold=renderer_profile.low_alignment_confidence,
        )
        if not repeat_match:
            raise ValueError("DOCX renderer snapshots differ for the P06 input")
        return _system_case(document, profile, tokenizer)

    def native_pdf_case() -> JsonValue:
        document = _parse_pdf(
            paths[PDF_DOCUMENT_ID],
            pdf_binding.source_document_id,
            pdf_binding.document_version_id,
        )
        return _system_case(document, profile, tokenizer)

    def ocr_pdf_case() -> JsonValue:
        document = _parse_pdf(
            paths[PDF_DOCUMENT_ID],
            pdf_binding.source_document_id,
            pdf_binding.document_version_id,
        )
        document = _apply_approved_p05_runtime_outputs(repository_root, document)
        return _system_case(document, profile, tokenizer)

    case_results = [
        runner.run_case(
            "p06-docx-b1-b2",
            docx_binding.document_sha256,
            docx_case,
        ),
        runner.run_case(
            "p06-pdf-native-b1-b2",
            pdf_binding.document_sha256,
            native_pdf_case,
        ),
        runner.run_case(
            "p06-pdf-ocr-b1-b2",
            sha256_file(repository_root / P05_REPORT),
            ocr_pdf_case,
        ),
    ]
    variants = [_decode_case(result) for result in case_results]
    system_evidence = [record for evidence, _, _ in variants for record in evidence.records]
    system_chunks = [chunk for _, chunks, _ in variants for chunk in chunks.chunks]
    b1_chunks = [text for _, _, baseline in variants for text in baseline]
    document_aliases = {
        binding.source_document_id: binding.document_id for binding in bindings.values()
    }
    matches = map_gold_to_system_evidence(
        gold_dataset.evidence,
        system_evidence,
        document_aliases=document_aliases,
    )
    metrics = _metrics(
        gold_dataset,
        variants,
        system_evidence,
        system_chunks,
        b1_chunks,
        matches,
        tokenizer,
    )
    system_payload: dict[str, JsonValue] = {
        "schema_version": "courserag.p06-system-output.v1",
        "variants": cast(
            list[JsonValue],
            [
                {
                    "evidence": evidence.model_dump(mode="json"),
                    "chunks": chunks.model_dump(mode="json"),
                    "b1_chunks": baseline,
                }
                for evidence, chunks, baseline in variants
            ],
        ),
    }
    atomic_write_json(output_dir / "system_outputs.json", system_payload)
    report: dict[str, JsonValue] = {
        "evaluation_scope": "approved_ds2_pilot_b1_b2",
        "approved_ds2_sha256": sha256_file(gold_path),
        "approved_record_count": len(gold_dataset.evidence),
        "matched_gold_count": len(matches),
        "document_identity_adapter": cast(dict[str, JsonValue], document_aliases),
        "b1_chunk_count": len(b1_chunks),
        "b2_evidence_count": len(system_evidence),
        "b2_parent_count": sum(chunk.kind == "parent" for chunk in system_chunks),
        "b2_child_count": sum(chunk.kind == "child" for chunk in system_chunks),
        "metrics": cast(dict[str, JsonValue], metrics),
        "fallback_used": False,
        "llm_as_judge_used": False,
        "gold_generated_from_system_output": False,
        "automatic_tuning": False,
    }
    runner.complete(report)
    return output_dir / "report.json"


def _system_case(
    document: ParsedDocumentIR,
    profile: ChunkProfile,
    tokenizer: LocalTokenizer,
) -> dict[str, JsonValue]:
    evidence = EvidenceBuilder(EvidenceBuilderProfile()).build(document)
    chunks = ParentChildChunker(profile, tokenizer).build(evidence)
    return {
        "evidence": evidence.model_dump(mode="json"),
        "chunks": chunks.model_dump(mode="json"),
        "b1_chunks": cast(list[JsonValue], _flat_windows(document)),
    }


def _decode_case(result: JsonValue) -> tuple[EvidenceArtifact, ChunkArtifact, list[str]]:
    if not isinstance(result, dict):
        raise ValueError("P06 case result is not an object")
    evidence = EvidenceArtifact.model_validate(result["evidence"])
    chunks = ChunkArtifact.model_validate(result["chunks"])
    baseline = result["b1_chunks"]
    if not isinstance(baseline, list) or not all(isinstance(text, str) for text in baseline):
        raise ValueError("P06 B1 result has invalid flat chunks")
    return evidence, chunks, [cast(str, text) for text in baseline]


def _flat_windows(document: ParsedDocumentIR) -> list[str]:
    text = "\n\n".join(
        block.text.strip()
        for page in document.pages
        for block in sorted(page.blocks, key=lambda item: item.order_index)
        if block.text.strip()
        and block.block_type
        not in {"header", "footer", "page_number", "page_break", "section_break", "figure"}
        and not block.noise_labels
    )
    if not text:
        return []
    size = 1000
    step = 850
    return [text[start : start + size] for start in range(0, len(text), step)]


def _apply_approved_p05_runtime_outputs(
    repository_root: Path, document: ParsedDocumentIR
) -> ParsedDocumentIR:
    p05 = DS1ParsingDataset.model_validate_json(
        (repository_root / APPROVED_P05).read_text(encoding="utf-8")
    )
    page_by_case = {
        record.record_id: record.source_span.page_start
        for record in p05.records
        if isinstance(record, OCRGold)
    }
    report = json.loads((repository_root / P05_REPORT).read_text(encoding="utf-8"))
    pages_by_number = {page.physical_page_index: page for page in document.pages}
    results: list[OCRPageResult] = []
    routed_pages = set(page_by_case.values())
    updated_pages = []
    for page in document.pages:
        if page.physical_page_index in routed_pages:
            updated_pages.append(
                page.model_copy(
                    update={
                        "source_mode": "ocr_pending",
                        "blocks": (),
                        "content_sha256": sha256_text(""),
                    }
                )
            )
        else:
            updated_pages.append(page)
    for case_id, page_number in page_by_case.items():
        target_page = pages_by_number.get(page_number)
        if target_page is None:
            raise ValueError(f"P05 OCR source page is absent from P04 IR: {page_number}")
        state = report["cases"].get(case_id)
        if not isinstance(state, dict) or state.get("status") != "succeeded":
            raise ValueError(f"P05 runtime output is not successful: {case_id}")
        result = OCRPageResult.model_validate(state["result"])
        results.append(result.model_copy(update={"page_id": target_page.page_id}))
    routed = document.model_copy(update={"pages": tuple(updated_pages)})
    return enrich_document_structure(merge_ocr_results(routed, tuple(results)))


def _metrics(
    gold_dataset: DS2EvidenceDataset,
    variants: list[tuple[EvidenceArtifact, ChunkArtifact, list[str]]],
    evidence: list[EvidenceRecord],
    chunks: list[ChunkRecord],
    b1_chunks: list[str],
    matches: Sequence[EvidenceMatch],
    tokenizer: LocalTokenizer,
) -> dict[str, JsonValue]:
    resolving = [evidence_resolving_rate(ev, ch) for ev, ch, _ in variants]
    resolving_numerator = sum(metric.numerator for metric in resolving)
    resolving_denominator = sum(metric.denominator for metric in resolving)
    b1_complete = _text_containment_count(gold_dataset, b1_chunks)
    b1_redundancy_numerator, b1_redundancy_denominator = _text_redundancy(b1_chunks, tokenizer)
    metric_values = {
        "b1_complete_semantic_unit_rate": _ratio(b1_complete, len(gold_dataset.evidence)),
        "b1_cross_boundary_split_error_rate": _ratio(
            len(gold_dataset.evidence) - b1_complete, len(gold_dataset.evidence)
        ),
        "b1_chunk_redundancy_rate": _ratio(b1_redundancy_numerator, b1_redundancy_denominator),
        "b2_evidence_resolving_rate": _ratio(resolving_numerator, resolving_denominator),
    }
    for metric in (
        evidence_text_consistency(gold_dataset.evidence, evidence, matches),
        chunk_evidence_coverage(gold_dataset.evidence, chunks),
        runtime_evidence_full_coverage(evidence, chunks),
        complete_semantic_unit_rate(gold_dataset.evidence, chunks),
        cross_boundary_split_error_rate(gold_dataset.evidence, chunks),
        chunk_redundancy_rate(chunks, tokenizer.token_ids),
        parent_expansion_sufficiency(gold_dataset.evidence, chunks),
        page_bbox_consistency(gold_dataset.evidence, evidence, matches),
        ocr_provenance_preservation(gold_dataset.evidence, evidence, matches),
    ):
        metric_values[f"b2_{metric.name}"] = metric.model_dump(mode="json")
    return cast(dict[str, JsonValue], metric_values)


def _text_containment_count(dataset: DS2EvidenceDataset, chunks: Sequence[str]) -> int:
    return sum(
        any(
            normalize_evidence_text(record.gold_text) in normalize_evidence_text(chunk)
            for chunk in chunks
        )
        for record in dataset.evidence
    )


def _text_redundancy(chunks: Sequence[str], tokenizer: LocalTokenizer) -> tuple[int, int]:
    tokens = [list(tokenizer.token_ids(text)) for text in chunks]
    total = sum(len(item) for item in tokens)
    duplicate = 0
    for first, second in zip(tokens, tokens[1:]):
        for size in range(min(len(first), len(second)), 0, -1):
            if first[-size:] == second[:size]:
                duplicate += size
                break
    return duplicate, total


def _ratio(numerator: float, denominator: float) -> dict[str, JsonValue]:
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
        "applicable": denominator > 0,
    }


def _artifact(repository_root: Path, path: Path) -> HashedArtifact:
    resolved = path.resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root):
        raise ValueError(f"P06 input is missing or outside repository: {resolved}")
    return HashedArtifact(
        path=resolved.relative_to(repository_root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type="application/octet-stream",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    report = run_p06_evaluation(
        repository_root=args.repository_root,
        output_dir=args.output_dir,
        run_id=args.run_id,
        resume=args.resume,
    )
    print(report)


if __name__ == "__main__":
    main()
