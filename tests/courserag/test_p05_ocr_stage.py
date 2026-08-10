from __future__ import annotations

from pathlib import Path

import fitz
from sqlalchemy.orm import Session

from courserag.domain.document import (
    PageIR,
    PageParseDecision,
    ParsedDocumentIR,
    ParseWarning,
    sha256_bytes,
    sha256_text,
)
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.ocr import (
    OCRPagesStage,
    OCRParsingCoordinator,
    ocr_stage_config,
)
from courserag.jobs.stages import BuildStageRunner, StageContext
from courserag.parsers.artifact_bundle import build_parsed_artifact_bundle, read_bundle_json
from courserag.parsers.ocr import (
    OCRImageInput,
    OCRPageResult,
    OCRProviderProfile,
    OCRRegionResult,
)
from courserag.parsers.ocr.resource import OCRResourceLimitError
from courserag.parsers.quality import build_parse_preview, build_quality_report
from courserag.persistence.models import (
    BuildJobRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    OCRPageResultRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class FakeProvider:
    name = "rapidocr"

    def __init__(self, profile: OCRProviderProfile, *, fail: bool = False) -> None:
        self.profile = profile
        self.fail = fail
        self.validated = False

    def validate_environment(self) -> None:
        self.validated = True

    def recognize(self, image: OCRImageInput) -> OCRPageResult:
        if self.fail:
            raise OCRResourceLimitError("OCR page exceeded the configured timeout")
        region = OCRRegionResult(
            region_id="region-1",
            text="识别文本",
            pixel_bbox=(10, 10, 80, 40),
            pixel_polygon=((10, 10), (80, 10), (80, 40), (10, 40)),
            page_bbox=(3.6, 3.6, 28.8, 14.4),
            confidence=0.9,
            raw_confidence=0.9,
        )
        return OCRPageResult(
            page_id=image.page_id,
            status="ready",
            engine="rapidocr",
            engine_version="fake-1",
            model_name=self.profile.model_name,
            model_manifest_sha256=self.profile.model_manifest_sha256,
            profile_sha256=self.profile.sha256,
            dpi=image.dpi,
            image_sha256=image.image_sha256,
            image_width=image.image_width,
            image_height=image.image_height,
            text=region.text,
            regions=(region,),
            confidence=0.9,
            duration_ms=10,
            peak_memory_bytes=100,
        )


def _source_pdf() -> bytes:
    document = fitz.open()
    document.new_page(width=100, height=100)
    content = document.tobytes()
    document.close()
    return content


def _profile() -> OCRProviderProfile:
    return OCRProviderProfile(
        name="rapidocr_candidate_v1",
        provider="rapidocr",
        model_name="rapidocr-bundled",
        model_manifest_sha256="a" * 64,
        model_manifest_path="fake-model-manifest.json",
    )


def _p04_artifact(source: bytes, version_id: str) -> bytes:
    document = ParsedDocumentIR(
        document_id="source-1",
        document_version_id=version_id,
        document_sha256=sha256_bytes(source),
        source_format="pdf",
        parser_profile="structured_pdf_v1",
        parser_version="1.0",
        pages=(
            PageIR(
                page_id="page-1",
                physical_page_index=1,
                width=100,
                height=100,
                source_mode="ocr_pending",
                parse_decision=PageParseDecision(mode="ocr"),
                content_sha256=sha256_text(""),
            ),
        ),
        sections=(),
        warnings=(
            ParseWarning(
                code="OCR_REQUIRED",
                message="P04 deferred image text to P05",
                page_index=1,
            ),
        ),
    )
    return build_parsed_artifact_bundle(
        document,
        build_quality_report(document),
        build_parse_preview(document),
    ).content


def _context(
    *,
    job_id: str,
    kb_id: str,
    version_id: str,
    artifact: bytes,
    source: bytes,
    profile: OCRProviderProfile,
) -> StageContext:
    return StageContext(
        build_job_id=job_id,
        knowledge_base_id=kb_id,
        input_hashes=(sha256_bytes(artifact), sha256_bytes(source)),
        input_identities=(f"{version_id}:structured_parse", f"{version_id}:source_pdf"),
        config=ocr_stage_config(profile),
        provider_metadata={
            "provider": profile.provider,
            "model": profile.model_name,
            "model_version": profile.model_manifest_sha256,
        },
    )


def test_ocr_stage_merges_result_and_embeds_deterministic_audit_entry() -> None:
    source = _source_pdf()
    profile = _profile()
    artifact = _p04_artifact(source, "version-1")
    provider = FakeProvider(profile)
    stage = OCRPagesStage(
        parsed_artifact=artifact,
        source_pdf=source,
        document_version_id="version-1",
        provider=provider,
        profile=profile,
    )
    context = _context(
        job_id="job-1",
        kb_id="kb-1",
        version_id="version-1",
        artifact=artifact,
        source=source,
        profile=profile,
    )

    first = stage.execute(context)
    second = stage.execute(context)
    document = ParsedDocumentIR.model_validate_json(
        read_bundle_json(first.content, "document_ir.json")
    )

    assert provider.validated
    assert first.content == second.content
    assert first.counts["pages_ready"] == 1
    assert document.pages[0].source_mode == "ocr"
    assert document.pages[0].blocks[0].text == "识别文本"
    assert not document.warnings
    assert read_bundle_json(first.content, "ocr_results.json")


def test_resource_failure_remains_pending_and_ready_with_warnings() -> None:
    source = _source_pdf()
    profile = _profile()
    artifact = _p04_artifact(source, "version-1")
    stage = OCRPagesStage(
        parsed_artifact=artifact,
        source_pdf=source,
        document_version_id="version-1",
        provider=FakeProvider(profile, fail=True),
        profile=profile,
    )
    output = stage.execute(
        _context(
            job_id="job-1",
            kb_id="kb-1",
            version_id="version-1",
            artifact=artifact,
            source=source,
            profile=profile,
        )
    )
    document = ParsedDocumentIR.model_validate_json(
        read_bundle_json(output.content, "document_ir.json")
    )

    assert output.counts["pages_with_warnings"] == 1
    assert document.pages[0].source_mode == "ocr_pending"
    assert {warning.code for warning in document.warnings} == {
        "OCR_REQUIRED",
        "OCR_RESOURCE_LIMIT",
    }


def test_ocr_coordinator_caches_and_materializes_result_idempotently(
    p03_session: Session,
    tmp_path: Path,
) -> None:
    repository = CourseRAGRepository(p03_session)
    kb = KnowledgeBaseRecord(course_id="course-p05", name="P05")
    repository.add(kb)
    repository.flush()
    source_record = SourceDocumentRecord(
        knowledge_base_id=kb.id,
        filename="scan.pdf",
        document_type="pdf",
    )
    repository.add(source_record)
    repository.flush()
    source = _source_pdf()
    version = DocumentVersionRecord(
        source_document_id=source_record.id,
        version_number=1,
        content_sha256=sha256_bytes(source),
        object_uri=f"artifact-input://{sha256_bytes(source)}",
        mime_type="application/pdf",
        size_bytes=len(source),
    )
    repository.add(version)
    job = BuildJobRecord(knowledge_base_id=kb.id, request_hash="b" * 64, status="running")
    repository.add(job)
    repository.flush()
    profile = _profile()
    artifact = _p04_artifact(source, version.id)
    stage = OCRPagesStage(
        parsed_artifact=artifact,
        source_pdf=source,
        document_version_id=version.id,
        provider=FakeProvider(profile),
        profile=profile,
    )
    context = _context(
        job_id=job.id,
        kb_id=kb.id,
        version_id=version.id,
        artifact=artifact,
        source=source,
        profile=profile,
    )
    store = FileArtifactStore(tmp_path / "artifacts")
    coordinator = OCRParsingCoordinator(
        repository,
        BuildStageRunner(repository, store),
        store,
    )

    first = coordinator.run(stage, context)
    second = coordinator.run(stage, context)

    assert second.id == first.id
    record = p03_session.query(OCRPageResultRecord).one()
    assert record.status == "ready"
    assert record.model_name == profile.model_name
    assert record.result_sha256 is not None
