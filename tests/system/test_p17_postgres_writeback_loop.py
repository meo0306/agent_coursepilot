from __future__ import annotations

import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from courserag.application.enrichment_service import EnrichmentService
from courserag.application.writeback_service import VerifiedWritebackService
from courserag.contracts import (
    RequestContext,
    StartEnrichmentBatchRequest,
    VerifiedContentType,
    VerifiedContentWriteRequest,
)
from courserag.indexing.verified_overlay import VerifiedOverlayPublisher
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.enrichment_worker import run_enrichment_batch
from courserag.persistence.models import (
    DocumentVersionRecord,
    EvidenceRecord,
    KnowledgeBaseRecord,
    ParsedDocumentRecord,
    SourceDocumentRecord,
)
from courserag.persistence.writeback_repository import WritebackRepository
from courserag.security import PrincipalRole, TrustedPrincipal


class _Embedding:
    identity = "p17-postgres-fake-embedding-v1"

    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


@pytest.mark.skipif(
    os.getenv("COURSEPILOT_RUN_P17_POSTGRES") != "1",
    reason="P17 PostgreSQL integration is explicitly gated",
)
def test_postgres_writeback_enrichment_overlay_loop_is_atomic(tmp_path: Path) -> None:
    database_url = os.environ["COURSEPILOT_DATABASE_URL"]
    engine = create_engine(database_url)
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            session = Session(bind=connection, expire_on_commit=False)
            suffix = uuid4().hex
            course_id = f"p17-integration-{suffix}"
            kb = KnowledgeBaseRecord(course_id=course_id, name="P17 integration")
            session.add(kb)
            session.flush()
            source = SourceDocumentRecord(
                knowledge_base_id=kb.id,
                filename="p17.pdf",
                document_type="pdf",
                status="ready",
            )
            session.add(source)
            session.flush()
            version = DocumentVersionRecord(
                source_document_id=source.id,
                version_number=1,
                content_sha256="a" * 64,
                object_uri="artifact://p17-source",
                mime_type="application/pdf",
                size_bytes=10,
                status="ready",
            )
            session.add(version)
            session.flush()
            parsed = ParsedDocumentRecord(
                document_version_id=version.id,
                parser_profile="p17",
                parser_version="1",
                status="ready",
            )
            session.add(parsed)
            session.flush()
            evidence = EvidenceRecord(
                parsed_document_id=parsed.id,
                stable_key=f"p17-evidence-{suffix}",
                evidence_type="paragraph",
                text="P17 verified integration evidence",
                content_sha256="b" * 64,
            )
            session.add(evidence)
            session.flush()

            repository = WritebackRepository(session)
            publisher = VerifiedOverlayPublisher(
                repository,
                FileArtifactStore(tmp_path / "overlay"),
                _Embedding(),
            )
            principal = TrustedPrincipal(
                principal_id="p17-owner",
                course_id=course_id,
                roles={PrincipalRole.OWNER},
            )
            writeback = VerifiedWritebackService(repository, publisher)
            request = VerifiedContentWriteRequest(
                context=RequestContext(
                    request_id=f"request-{suffix}",
                    trace_id=f"trace-{suffix}",
                    idempotency_key=f"write-{suffix}",
                ),
                course_id=course_id,
                content_type=VerifiedContentType.VERIFIED_LESSON_FRAGMENT,
                content={"title": "P17 fragment", "body": "Verified explanation"},
                evidence_ids=[evidence.id],
                approved_by="p17-owner",
                task_id=f"task-{suffix}",
                approval_record_id=f"approval-{suffix}",
            )
            created = writeback.write(request, principal=principal)
            replay = writeback.write(request, principal=principal)
            assert created.created and not replay.created
            assert replay.verified_content_id == created.verified_content_id

            batch = EnrichmentService(repository, profile_sha256="c" * 64).start(
                StartEnrichmentBatchRequest(
                    course_id=course_id,
                    actor_id="p17-owner",
                    manual=True,
                ),
                principal=principal,
            )
            assert batch.batch_id is not None
            assert run_enrichment_batch(
                repository,
                batch.batch_id,
                overlay_publisher=publisher,
            )
            assert not run_enrichment_batch(
                repository,
                batch.batch_id,
                overlay_publisher=publisher,
            )
            record = repository.get_content(created.verified_content_id)
            assert record is not None and record.status == "enriched"
            assert record.current_overlay_version_id is not None
            manifest_uri = repository.overlay_manifest_uri(record.current_overlay_version_id)
            assert manifest_uri is not None
            hits = publisher.search(manifest_uri, "Verified explanation", top_k=5)
            assert [hit.verified_content_id for hit in hits] == [record.id]
            assert hits[0].evidence_ids == (evidence.id,)
            assert kb.active_index_version_id is None
        finally:
            transaction.rollback()
