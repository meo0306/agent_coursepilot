"""Source-grounded P04 Pilot diagnostics; never promotes Parser output to DS1 Gold."""

from __future__ import annotations

import argparse
import subprocess
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from pydantic import JsonValue

from courserag.domain.document import ParsedDocumentIR
from courserag.evals.schemas import CorpusFixtureManifest, P04InputWorkPackage
from courserag.parsers.docx import StructuredDOCXParser
from courserag.parsers.pagination import (
    DocxPaginationRenderer,
    RendererProfile,
    align_docx_blocks,
)
from courserag.parsers.pdf import StructuredPDFParser
from courserag.parsers.quality import build_quality_report
from courserag.parsers.structure import enrich_document_structure
from evaluation.contracts import (
    DatasetSplit,
    FallbackPolicy,
    HashedArtifact,
    ReviewStatus,
    RunIntent,
)
from evaluation.io import atomic_write_json
from evaluation.manifest import RunDatasetRef, RunManifest, sha256_file
from evaluation.runner import EvaluationRunner

DATASET_ROOT = Path("datasets/courserag_eval/v1")
WORK_PACKAGE = DATASET_ROOT / "approved/work_packages/p04_input.json"
FIXTURE_MANIFEST = DATASET_ROOT / "provenance/corpus_fixture_manifest.json"
RENDERER_PROFILE = Path("resources/renderers/libreoffice_headless_v1/profile.json")
RENDERER_FONT_LOCK = Path("resources/renderers/libreoffice_headless_v1/fonts.lock.json")
STRESS_PDF_RUNS = (
    Path(
        "storage_eval/courserag_corpus/v1/docx_qa_render_r3/"
        "doc_ai_algorithms_systems_structure_stress.pdf"
    ),
    Path(
        "storage_eval/courserag_corpus/v1/docx_qa_render_r4/"
        "doc_ai_algorithms_systems_structure_stress.pdf"
    ),
)
PRIMARY_PDF_RUNS = (
    Path("storage_eval/p04_primary_render/run1/教材-人工智能：从算法到系统.pdf"),
    Path("storage_eval/p04_primary_render/run2/教材-人工智能：从算法到系统.pdf"),
)


def _artifact(repository_root: Path, path: Path, media_type: str) -> HashedArtifact:
    resolved = (repository_root / path).resolve()
    if not resolved.is_file() or not resolved.is_relative_to(repository_root):
        raise ValueError(f"P04 Pilot input is outside the repository: {path}")
    return HashedArtifact(
        path=path.as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
        media_type=media_type,
    )


def _git_state(repository_root: Path) -> tuple[str, bool]:
    commit = subprocess.run(
        ("git", "rev-parse", "HEAD"),
        cwd=repository_root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    dirty = bool(
        subprocess.run(
            ("git", "status", "--porcelain"),
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    return commit, dirty


def _load_inputs(
    repository_root: Path,
) -> tuple[P04InputWorkPackage, CorpusFixtureManifest, dict[str, Path]]:
    work_package = P04InputWorkPackage.model_validate_json(
        (repository_root / WORK_PACKAGE).read_text(encoding="utf-8")
    )
    if (
        work_package.review_status is not ReviewStatus.APPROVED
        or work_package.approval_scope != "p04_input_selection_only"
        or work_package.gold_status != "no_ds1_gold"
    ):
        raise ValueError("P04 Pilot requires the exact approved non-Gold input work package")
    fixtures = CorpusFixtureManifest.model_validate_json(
        (repository_root / FIXTURE_MANIFEST).read_text(encoding="utf-8")
    )
    paths: dict[str, Path] = {}
    for artifact in fixtures.artifacts:
        path = (repository_root / artifact.repository_relative_path).resolve()
        if not path.is_file() or not path.is_relative_to(repository_root):
            raise ValueError(
                f"P04 fixture is missing or outside the repository: {artifact.document_id}"
            )
        if sha256_file(path) != artifact.sha256:
            raise ValueError(f"P04 fixture hash changed: {artifact.document_id}")
        paths[artifact.document_id] = path
    return work_package, fixtures, paths


def _parse_pdf(path: Path, document_id: str, document_version_id: str) -> ParsedDocumentIR:
    content = path.read_bytes()
    document = (
        StructuredPDFParser()
        .parse(
            content,
            document_id=document_id,
            document_version_id=document_version_id,
            document_sha256=sha256_file(path),
        )
        .document
    )
    return enrich_document_structure(document)


def _requested_fonts(document: ParsedDocumentIR) -> list[str]:
    value = document.metadata.get("requested_fonts", [])
    if not isinstance(value, list) or not all(isinstance(font, str) for font in value):
        raise ValueError("DOCX parser emitted an invalid requested-font manifest")
    return [font for font in value if isinstance(font, str)]


def run_p04_pilot(
    *,
    repository_root: Path,
    output_dir: Path,
    run_id: str,
    resume: bool = False,
) -> Path:
    repository_root = repository_root.resolve()
    output_dir = output_dir.resolve()
    if not output_dir.is_relative_to((repository_root / "storage_eval").resolve()):
        raise ValueError("P04 system output must stay under storage_eval")
    work_package, _, paths = _load_inputs(repository_root)
    profile = RendererProfile.load(repository_root / RENDERER_PROFILE)
    # The PDFs were created in the exact recorded Linux image. Host-side fontconfig
    # is not that environment, so pre-rendered evidence conservatively marks every
    # requested family for review instead of claiming a false mapping.
    renderer = DocxPaginationRenderer(profile, font_resolver=lambda font: None)
    git_commit, git_dirty = _git_state(repository_root)
    dataset_root = (repository_root / DATASET_ROOT).resolve()
    dataset_manifest = dataset_root / "manifest.json"
    split = dataset_root / "splits/pilot_ids.txt"
    input_paths = (
        WORK_PACKAGE,
        FIXTURE_MANIFEST,
        RENDERER_PROFILE,
        RENDERER_FONT_LOCK,
        *STRESS_PDF_RUNS,
        *PRIMARY_PDF_RUNS,
    )
    manifest = RunManifest(
        run_id=run_id,
        created_at=datetime.now(UTC),
        dataset=RunDatasetRef(
            dataset_id="courserag-eval",
            dataset_version="v1",
            split=DatasetSplit.PILOT,
            manifest_sha256=sha256_file(dataset_manifest),
            split_sha256=sha256_file(split),
        ),
        intent=RunIntent.EVALUATION,
        tuning_enabled=False,
        git_commit=git_commit,
        git_dirty=git_dirty,
        input_artifacts=[
            _artifact(
                repository_root,
                path,
                "application/pdf" if path.suffix == ".pdf" else "application/json",
            )
            for path in input_paths
        ],
        component_versions={
            "p04_parser": "1.0",
            "pymupdf": version("pymupdf"),
            "python_docx": version("python-docx"),
            "renderer_provider": profile.provider,
            "renderer_version": profile.renderer_version,
            "renderer_profile_sha256": profile.profile_sha256,
            "renderer_image_id": (
                "sha256:7051ac5e31cb11fddf994960135a460e8de6486c39c61366962fdceeacb00643"
            ),
        },
        configuration={
            "pilot_native_pdf_pages": [5, 10, 12, 20, 32],
            "docx_alignment_threshold": profile.low_alignment_confidence,
            "section_boundary_tolerance_blocks": 1,
            "gold_status": "no_ds1_gold",
            "output_policy": "storage_eval_only",
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

    primary_pdf_binding = next(
        identity
        for identity in work_package.identities
        if identity.document_id == "doc_ai_general_education_excerpt"
    )

    def native_pdf_case() -> JsonValue:
        document = _parse_pdf(
            paths[primary_pdf_binding.document_id],
            primary_pdf_binding.source_document_id,
            primary_pdf_binding.document_version_id,
        )
        pilot_pages = {
            candidate.page_number for candidate in work_package.native_pdf_pages if candidate.pilot
        }
        selected = [page for page in document.pages if page.physical_page_index in pilot_pages]
        warning_codes: list[JsonValue] = []
        warning_codes.extend(sorted({warning.code for warning in document.warnings}))
        return {
            "status": "diagnostic_only_no_gold",
            "selected_page_count": len(selected),
            "selected_pages": [page.physical_page_index for page in selected],
            "block_count": sum(len(page.blocks) for page in selected),
            "bbox_block_count": sum(
                block.bbox is not None for page in selected for block in page.blocks
            ),
            "span_count": sum(
                len(line.spans)
                for page in selected
                for block in page.blocks
                for line in block.lines
            ),
            "heading_count": sum(
                block.block_type == "heading" for page in selected for block in page.blocks
            ),
            "table_count": sum(
                table.source_span.page_start in pilot_pages for table in document.tables
            ),
            "warning_codes": warning_codes,
        }

    runner.run_case("p04-native-pdf-pilot", primary_pdf_binding.document_sha256, native_pdf_case)

    primary_docx_binding = next(
        identity
        for identity in work_package.identities
        if identity.document_id == "doc_ai_algorithms_systems"
    )

    def primary_docx_case() -> JsonValue:
        path = paths[primary_docx_binding.document_id]
        content = path.read_bytes()
        parsed = (
            StructuredDOCXParser()
            .parse(
                content,
                document_id=primary_docx_binding.source_document_id,
                document_version_id=primary_docx_binding.document_version_id,
                document_sha256=primary_docx_binding.document_sha256,
            )
            .document
        )
        snapshots = [
            renderer.build_snapshot(
                (repository_root / pdf_path).read_bytes(),
                requested_fonts=_requested_fonts(parsed),
            )
            for pdf_path in PRIMARY_PDF_RUNS
        ]
        aligned = [
            enrich_document_structure(
                align_docx_blocks(
                    parsed,
                    snapshot,
                    low_confidence_threshold=profile.low_alignment_confidence,
                )
            )
            for snapshot in snapshots
        ]
        expected = {
            anchor.source_text_sha256
            for anchor in work_package.docx_pagination_anchors
            if anchor.document_id == primary_docx_binding.document_id
        }
        anchor_maps = [
            {
                block.content_sha256: (
                    block.page_anchor.physical_page_index,
                    block.page_anchor.display_page_label,
                    block.page_anchor.section_page_index,
                    block.page_anchor.alignment_confidence,
                )
                for page in document.pages
                for block in page.blocks
                if block.content_sha256 in expected and block.page_anchor is not None
            }
            for document in aligned
        ]
        quality = build_quality_report(aligned[0])
        selected_anchors = list(anchor_maps[0].values())
        return {
            "status": "candidate_output_requires_human_gold_review",
            "raw_pdf_hashes_differ": (
                snapshots[0].manifest.raw_pdf_sha256 != snapshots[1].manifest.raw_pdf_sha256
            ),
            "canonical_pdf_hash_repeat_match": (
                snapshots[0].manifest.canonical_pdf_sha256
                == snapshots[1].manifest.canonical_pdf_sha256
            ),
            "page_manifest_repeat_match": (
                snapshots[0].manifest.page_manifest_sha256
                == snapshots[1].manifest.page_manifest_sha256
            ),
            "page_count": snapshots[0].manifest.page_count,
            "font_substitution_count": len(snapshots[0].manifest.font_substitutions),
            "approved_input_anchor_count": len(expected),
            "resolved_anchor_count": len(anchor_maps[0]),
            "assigned_anchor_count": sum(anchor[0] is not None for anchor in selected_anchors),
            "display_label_anchor_count": sum(anchor[1] is not None for anchor in selected_anchors),
            "minimum_selected_anchor_confidence": min(
                (anchor[3] for anchor in selected_anchors),
                default=0.0,
            ),
            "anchor_repeat_match": anchor_maps[0] == anchor_maps[1],
            "docx_page_assignment_coverage": quality.metrics["docx_page_assignment_coverage"],
            "low_confidence_alignment_count": quality.low_confidence_alignment_count,
            "unresolved_block_count": quality.unresolved_block_count,
            "canonical_pdf_sha256": snapshots[0].manifest.canonical_pdf_sha256,
            "section_count": len(aligned[0].sections),
            "table_count": len(aligned[0].tables),
            "run_count": sum(
                len(line.spans)
                for page in aligned[0].pages
                for block in page.blocks
                for line in block.lines
            ),
        }

    runner.run_case(
        "p04-primary-docx-structure", primary_docx_binding.document_sha256, primary_docx_case
    )

    stress_binding = next(
        identity
        for identity in work_package.identities
        if identity.document_id == "doc_ai_algorithms_systems_structure_stress"
    )

    def layout_stress_case() -> JsonValue:
        path = paths[stress_binding.document_id]
        content = path.read_bytes()
        parsed = (
            StructuredDOCXParser()
            .parse(
                content,
                document_id=stress_binding.source_document_id,
                document_version_id=stress_binding.document_version_id,
                document_sha256=stress_binding.document_sha256,
            )
            .document
        )
        snapshots = [
            renderer.build_snapshot(
                (repository_root / pdf_path).read_bytes(),
                requested_fonts=_requested_fonts(parsed),
            )
            for pdf_path in STRESS_PDF_RUNS
        ]
        aligned = [
            align_docx_blocks(
                parsed,
                snapshot,
                low_confidence_threshold=profile.low_alignment_confidence,
            )
            for snapshot in snapshots
        ]
        expected = {
            anchor.source_text_sha256
            for anchor in work_package.docx_pagination_anchors
            if anchor.document_id == stress_binding.document_id
        }
        anchor_maps = []
        for document in aligned:
            anchor_maps.append(
                {
                    block.content_sha256: (
                        block.page_anchor.physical_page_index,
                        block.page_anchor.display_page_label,
                        block.page_anchor.section_page_index,
                        block.page_anchor.alignment_confidence,
                    )
                    for page in document.pages
                    for block in page.blocks
                    if block.content_sha256 in expected and block.page_anchor is not None
                }
            )
        quality = build_quality_report(aligned[0])
        selected_anchors = list(anchor_maps[0].values())
        return {
            "status": "candidate_output_requires_human_gold_review",
            "raw_pdf_hashes_differ": (
                snapshots[0].manifest.raw_pdf_sha256 != snapshots[1].manifest.raw_pdf_sha256
            ),
            "canonical_pdf_hash_repeat_match": (
                snapshots[0].manifest.canonical_pdf_sha256
                == snapshots[1].manifest.canonical_pdf_sha256
            ),
            "page_manifest_repeat_match": (
                snapshots[0].manifest.page_manifest_sha256
                == snapshots[1].manifest.page_manifest_sha256
            ),
            "page_count": snapshots[0].manifest.page_count,
            "font_substitution_count": len(snapshots[0].manifest.font_substitutions),
            "approved_input_anchor_count": len(expected),
            "resolved_anchor_count": len(anchor_maps[0]),
            "assigned_anchor_count": sum(anchor[0] is not None for anchor in selected_anchors),
            "display_label_anchor_count": sum(anchor[1] is not None for anchor in selected_anchors),
            "minimum_selected_anchor_confidence": min(
                (anchor[3] for anchor in selected_anchors),
                default=0.0,
            ),
            "anchor_repeat_match": anchor_maps[0] == anchor_maps[1],
            "low_confidence_alignment_count": quality.low_confidence_alignment_count,
            "unresolved_block_count": quality.unresolved_block_count,
            "docx_page_assignment_coverage": quality.metrics["docx_page_assignment_coverage"],
            "canonical_pdf_sha256": snapshots[0].manifest.canonical_pdf_sha256,
            "profile_sha256": profile.profile_sha256,
            "font_manifest_sha256": profile.font_manifest_sha256,
        }

    runner.run_case("p04-docx-layout-stress", stress_binding.document_sha256, layout_stress_case)

    scan_binding = next(
        identity
        for identity in work_package.identities
        if identity.document_id == "doc_ai_general_education_scan_clean"
    )

    def ocr_route_case() -> JsonValue:
        document = _parse_pdf(
            paths[scan_binding.document_id],
            scan_binding.source_document_id,
            scan_binding.document_version_id,
        )
        decisions = [
            page.parse_decision.mode for page in document.pages if page.parse_decision is not None
        ]
        return {
            "status": "route_only_ocr_body_deferred_to_p05",
            "page_count": len(document.pages),
            "ocr_pending_count": sum(decision == "ocr" for decision in decisions),
            "hybrid_pending_count": sum(decision == "hybrid" for decision in decisions),
        }

    runner.run_case("p04-ocr-route-only", scan_binding.document_sha256, ocr_route_case)
    runner.complete(
        {
            "formal_metric_status": "not_applicable_no_approved_ds1_gold",
            "gold_was_generated_from_system_output": False,
            "llm_as_judge_used": False,
            "b0_runtime_modified": False,
            "human_checkpoint_required": True,
            "exit_gate_quality_comparison": "pending_approved_ds1_gold",
        }
    )
    return output_dir / "report.json"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P04 source-grounded Pilot diagnostics.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--output-dir", type=Path, default=Path("storage_eval/p04_pilot"))
    parser.add_argument("--run-id", default="p04-pilot-v1")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    report = run_p04_pilot(
        repository_root=args.repository_root,
        output_dir=args.output_dir,
        run_id=args.run_id,
        resume=args.resume,
    )
    print(report)


if __name__ == "__main__":
    main()
