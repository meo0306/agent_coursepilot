from __future__ import annotations

from pathlib import Path

import fitz
from sqlalchemy.orm import Session

from courserag.domain.document import sha256_bytes
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.parsing import (
    StructuredParseStage,
    StructuredParsingCoordinator,
    structured_parse_stage_config,
)
from courserag.jobs.stages import BuildStageRunner, StageContext
from courserag.persistence.models import (
    BlockRecord,
    BuildJobRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    PageRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


def _pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((40, 60), "1. Structured parsing")
    page.insert_text((40, 100), "This paragraph is projected into P03 facts.")
    content = document.tobytes()
    document.close()
    return content


def test_parse_stage_uses_cache_and_materializes_idempotently(
    p03_session: Session,
    tmp_path: Path,
) -> None:
    repository = CourseRAGRepository(p03_session)
    kb = KnowledgeBaseRecord(course_id="course-p04", name="P04")
    repository.add(kb)
    repository.flush()
    source = SourceDocumentRecord(
        knowledge_base_id=kb.id,
        filename="sample.pdf",
        document_type="pdf",
    )
    repository.add(source)
    repository.flush()
    content = _pdf()
    version = DocumentVersionRecord(
        source_document_id=source.id,
        version_number=1,
        content_sha256=sha256_bytes(content),
        object_uri=f"artifact-input://{sha256_bytes(content)}",
        mime_type="application/pdf",
        size_bytes=len(content),
    )
    repository.add(version)
    repository.flush()
    job = BuildJobRecord(
        knowledge_base_id=kb.id,
        request_hash="a" * 64,
        status="running",
    )
    repository.add(job)
    repository.flush()
    store = FileArtifactStore(tmp_path / "artifacts")
    coordinator = StructuredParsingCoordinator(
        repository,
        BuildStageRunner(repository, store),
        store,
    )
    stage = StructuredParseStage(
        content=content,
        document_id=source.id,
        document_version_id=version.id,
        source_format="pdf",
    )
    context = StageContext(
        build_job_id=job.id,
        knowledge_base_id=kb.id,
        input_hashes=(version.content_sha256,),
        input_identities=(version.id,),
        config=structured_parse_stage_config(
            parser_profile="structured_pdf_v1", pipeline_version="p04-v1"
        ),
    )
    first = coordinator.run(stage, context)
    second = coordinator.run(stage, context)
    assert second.id == first.id
    assert second.artifact_id == first.artifact_id
    assert p03_session.query(PageRecord).filter_by(parsed_document_id=first.id).count() == 1
    assert p03_session.query(BlockRecord).filter_by(parsed_document_id=first.id).count() >= 2
