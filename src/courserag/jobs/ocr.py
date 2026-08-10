"""P05 page OCR Stage and final parsed-document projection."""

from __future__ import annotations

from dataclasses import dataclass

import fitz
from pydantic import TypeAdapter

from courserag.domain.document import (
    ParsedDocumentIR,
    sha256_bytes,
)
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput
from courserag.parsers.artifact_bundle import build_parsed_artifact_bundle, read_bundle_json
from courserag.parsers.normalizer import merge_ocr_results
from courserag.parsers.ocr.resource import (
    OCRIdentityError,
    OCRProviderError,
    OCRProviderUnavailable,
    OCRResourceLimitError,
)
from courserag.parsers.ocr.types import (
    OCRImageInput,
    OCRPageResult,
    OCRProvider,
    OCRProviderProfile,
    OCRWarning,
)
from courserag.parsers.quality import build_parse_preview, build_quality_report
from courserag.parsers.structure import enrich_document_structure
from courserag.persistence.materialize import (
    materialize_ocr_page_results,
    materialize_parsed_document,
)
from courserag.persistence.models import ParsedDocumentRecord
from courserag.persistence.repositories import CourseRAGRepository

_OCR_RESULTS = TypeAdapter(tuple[OCRPageResult, ...])


@dataclass(frozen=True)
class OCRPagesStage:
    parsed_artifact: bytes
    source_pdf: bytes
    document_version_id: str
    provider: OCRProvider
    profile: OCRProviderProfile
    name: str = "ocr_pages"
    version: str = "1.1"

    def execute(self, context: StageContext) -> StageOutput:
        parsed_hash = sha256_bytes(self.parsed_artifact)
        source_hash = sha256_bytes(self.source_pdf)
        if context.input_hashes != (parsed_hash, source_hash):
            raise ValueError("OCR Stage input hashes do not match P04 Artifact and source PDF")
        if context.input_identities != (
            f"{self.document_version_id}:structured_parse",
            f"{self.document_version_id}:source_pdf",
        ):
            raise ValueError("OCR Stage input identities do not match document version")
        expected_config = {
            "ocr_provider": self.profile.provider,
            "ocr_profile_sha256": self.profile.sha256,
            "ocr_model_manifest_sha256": self.profile.model_manifest_sha256,
            "ocr_dpi": self.profile.dpi,
            "ocr_max_pixels": self.profile.max_pixels,
            "ocr_timeout_seconds": self.profile.timeout_seconds,
            "ocr_max_memory_bytes": self.profile.max_memory_bytes,
            "ocr_max_workers": self.profile.max_workers,
        }
        if context.config != expected_config:
            raise ValueError("OCR Stage config differs from the frozen provider profile")
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(self.parsed_artifact, "document_ir.json")
        )
        if document.document_version_id != self.document_version_id:
            raise ValueError("P04 Artifact document version differs from OCR Stage")
        if document.document_sha256 != source_hash:
            raise ValueError("source PDF differs from the document Hash in P04 Artifact")
        if document.source_format != "pdf":
            raise ValueError("P05 OCR Stage currently accepts rendered or native PDF input only")
        self.provider.validate_environment()
        results: list[OCRPageResult] = []
        with fitz.open(stream=self.source_pdf, filetype="pdf") as source:
            for page in document.pages:
                if page.source_mode not in {"ocr_pending", "hybrid_pending"}:
                    continue
                if page.physical_page_index is None:
                    raise ValueError("OCR-routed page has no physical page index")
                image = _render_page(
                    source[page.physical_page_index - 1],
                    page_id=page.page_id,
                    profile=self.profile,
                )
                try:
                    result = self.provider.recognize(image)
                except (OCRIdentityError, OCRProviderUnavailable):
                    raise
                except OCRResourceLimitError as exc:
                    result = _failed_page_result(
                        image,
                        self.profile,
                        code="OCR_RESOURCE_LIMIT",
                        message=str(exc),
                        duration_ms=exc.duration_ms,
                        peak_memory_bytes=exc.peak_memory_bytes,
                    )
                except OCRProviderError as exc:
                    result = _failed_page_result(
                        image,
                        self.profile,
                        code="OCR_PAGE_FAILED",
                        message="OCR page failed; inspect protected service logs",
                        duration_ms=exc.duration_ms,
                        peak_memory_bytes=exc.peak_memory_bytes,
                    )
                results.append(result)
        result_tuple = tuple(results)
        merged = enrich_document_structure(merge_ocr_results(document, result_tuple))
        quality = build_quality_report(merged)
        preview = build_parse_preview(merged)
        bundle = build_parsed_artifact_bundle(
            merged,
            quality,
            preview,
            ocr_results=result_tuple,
        )
        return StageOutput(
            content=bundle.content,
            media_type="application/vnd.courserag.parsed-document+zip",
            counts={
                "pages_routed": len(results),
                "pages_ready": sum(result.status == "ready" for result in results),
                "pages_with_warnings": sum(
                    result.status == "ready_with_warnings" for result in results
                ),
                "ocr_regions": sum(len(result.regions) for result in results),
                "warnings": len(merged.warnings),
            },
            warnings=quality.warning_codes,
        )


def ocr_stage_config(profile: OCRProviderProfile) -> dict[str, object]:
    return {
        "ocr_provider": profile.provider,
        "ocr_profile_sha256": profile.sha256,
        "ocr_model_manifest_sha256": profile.model_manifest_sha256,
        "ocr_dpi": profile.dpi,
        "ocr_max_pixels": profile.max_pixels,
        "ocr_timeout_seconds": profile.timeout_seconds,
        "ocr_max_memory_bytes": profile.max_memory_bytes,
        "ocr_max_workers": profile.max_workers,
    }


class OCRParsingCoordinator:
    def __init__(
        self,
        repository: CourseRAGRepository,
        stage_runner: BuildStageRunner,
        artifact_store: FileArtifactStore,
    ) -> None:
        self.repository = repository
        self.stage_runner = stage_runner
        self.artifact_store = artifact_store

    def run(
        self,
        stage: OCRPagesStage,
        context: StageContext,
        *,
        force: bool = False,
    ) -> ParsedDocumentRecord:
        stage_run = self.stage_runner.run(stage, context, force=force)
        if stage_run.artifact_id is None:
            raise RuntimeError("OCR Stage completed without an artifact")
        artifact = self.repository.get_artifact(stage_run.artifact_id)
        if artifact is None:
            raise RuntimeError("OCR Stage artifact record disappeared")
        content = self.artifact_store.read(artifact.uri, expected_sha256=artifact.sha256)
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(content, "document_ir.json")
        )
        results = _OCR_RESULTS.validate_json(read_bundle_json(content, "ocr_results.json"))
        parsed = materialize_parsed_document(
            self.repository,
            document=document,
            artifact=artifact,
        )
        materialize_ocr_page_results(
            self.repository,
            results=results,
            artifact=artifact,
        )
        return parsed


def _render_page(
    page: fitz.Page,
    *,
    page_id: str,
    profile: OCRProviderProfile,
) -> OCRImageInput:
    scale = profile.dpi / 72.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    content = pixmap.tobytes("png")
    return OCRImageInput(
        page_id=page_id,
        png_bytes=content,
        dpi=profile.dpi,
        image_width=pixmap.width,
        image_height=pixmap.height,
        pdf_width_points=float(page.rect.width),
        pdf_height_points=float(page.rect.height),
        image_sha256=sha256_bytes(content),
    )


def _failed_page_result(
    image: OCRImageInput,
    profile: OCRProviderProfile,
    *,
    code: str,
    message: str,
    duration_ms: int = 0,
    peak_memory_bytes: int = 0,
) -> OCRPageResult:
    return OCRPageResult(
        page_id=image.page_id,
        status="ready_with_warnings",
        engine=profile.provider,
        engine_version="not_completed",
        model_name=profile.model_name,
        model_manifest_sha256=profile.model_manifest_sha256,
        profile_sha256=profile.sha256,
        dpi=image.dpi,
        image_sha256=image.image_sha256,
        image_width=image.image_width,
        image_height=image.image_height,
        text="",
        duration_ms=duration_ms,
        peak_memory_bytes=peak_memory_bytes,
        warnings=(OCRWarning(code=code, message=message),),
    )
