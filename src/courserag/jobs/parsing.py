"""P04 structured parsing stage; the P03 runner owns artifact persistence and retry."""

from __future__ import annotations

from dataclasses import dataclass

from courserag.domain.document import ParsedDocumentIR, sha256_bytes
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.stages import BuildStageRunner, StageContext, StageOutput
from courserag.parsers.artifact_bundle import build_parsed_artifact_bundle, read_bundle_json
from courserag.parsers.docx import StructuredDOCXParser
from courserag.parsers.pagination import (
    DocxPaginationRenderer,
    align_docx_blocks,
)
from courserag.parsers.pdf import StructuredPDFParser
from courserag.parsers.quality import build_parse_preview, build_quality_report
from courserag.parsers.structure import enrich_document_structure
from courserag.persistence.materialize import materialize_parsed_document
from courserag.persistence.models import ParsedDocumentRecord
from courserag.persistence.repositories import CourseRAGRepository


@dataclass(frozen=True)
class StructuredParseStage:
    content: bytes
    document_id: str
    document_version_id: str
    source_format: str
    docx_renderer: DocxPaginationRenderer | None = None
    name: str = "structured_parse"
    version: str = "1.2"

    def execute(self, context: StageContext) -> StageOutput:
        digest = sha256_bytes(self.content)
        if context.input_hashes != (digest,):
            raise ValueError("structured parse Stage input hash does not match document bytes")
        if context.input_identities != (self.document_version_id,):
            raise ValueError("structured parse Stage identity does not match document version")
        assets: dict[str, bytes]
        if self.source_format == "pdf":
            result = StructuredPDFParser().parse(
                self.content,
                document_id=self.document_id,
                document_version_id=self.document_version_id,
                document_sha256=digest,
            )
            document = result.document
            assets = dict(result.binary_assets)
        elif self.source_format == "docx":
            if self.docx_renderer is None:
                raise ValueError("DOCX structured parsing requires an explicit frozen renderer")
            result = StructuredDOCXParser().parse(
                self.content,
                document_id=self.document_id,
                document_version_id=self.document_version_id,
                document_sha256=digest,
            )
            requested_fonts = result.document.metadata.get("requested_fonts", [])
            if not isinstance(requested_fonts, list) or not all(
                isinstance(font, str) for font in requested_fonts
            ):
                raise ValueError("DOCX parser emitted an invalid requested-font manifest")
            font_names = [font for font in requested_fonts if isinstance(font, str)]
            snapshot = self.docx_renderer.render(self.content, requested_fonts=font_names)
            document = align_docx_blocks(
                result.document,
                snapshot,
                low_confidence_threshold=self.docx_renderer.profile.low_alignment_confidence,
            )
            assets = dict(result.binary_assets)
            assets.update(
                {
                    "renderer/raw.pdf": snapshot.raw_pdf,
                    "renderer/canonical.pdf": snapshot.canonical_pdf,
                }
            )
        else:
            raise ValueError("structured parse Stage supports only PDF and DOCX")
        document = enrich_document_structure(document)
        quality = build_quality_report(document)
        preview = build_parse_preview(document)
        bundle = build_parsed_artifact_bundle(document, quality, preview, binary_assets=assets)
        return StageOutput(
            content=bundle.content,
            media_type="application/vnd.courserag.parsed-document+zip",
            counts={
                "pages": quality.page_count,
                "sections": len(document.sections),
                "blocks": sum(len(page.blocks) for page in document.pages),
                "tables": len(document.tables),
                "warnings": len(document.warnings),
            },
            warnings=quality.warning_codes,
        )


def structured_parse_stage_config(
    *,
    parser_profile: str,
    pipeline_version: str,
) -> dict[str, object]:
    return {
        "parser_profile": parser_profile,
        "pipeline_version": pipeline_version,
    }


class StructuredParsingCoordinator:
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
        stage: StructuredParseStage,
        context: StageContext,
        *,
        force: bool = False,
    ) -> ParsedDocumentRecord:
        stage_run = self.stage_runner.run(stage, context, force=force)
        if stage_run.artifact_id is None:
            raise RuntimeError("structured parse Stage completed without an artifact")
        artifact = self.repository.get_artifact(stage_run.artifact_id)
        if artifact is None:
            raise RuntimeError("structured parse Stage artifact record disappeared")
        content = self.artifact_store.read(artifact.uri, expected_sha256=artifact.sha256)
        document = ParsedDocumentIR.model_validate_json(
            read_bundle_json(content, "document_ir.json")
        )
        return materialize_parsed_document(
            self.repository,
            document=document,
            artifact=artifact,
        )
