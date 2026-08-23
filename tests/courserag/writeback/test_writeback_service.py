from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from courserag.application.enrichment_service import EnrichmentService
from courserag.application.writeback_service import VerifiedWritebackService
from courserag.contracts import (
    CourseRAGError,
    ErrorCode,
    RequestContext,
    RevokeVerifiedContentRequest,
    StartEnrichmentBatchRequest,
    VerifiedContentStatus,
    VerifiedContentType,
    VerifiedContentWriteRequest,
)
from courserag.indexing.verified_overlay import VerifiedOverlayPublisher
from courserag.jobs.artifacts import FileArtifactStore
from courserag.jobs.enrichment_worker import run_enrichment_batch
from courserag.persistence.base import CourseRAGBase
from courserag.persistence.models import (
    DocumentVersionRecord,
    EvidenceRecord,
    KnowledgeBaseRecord,
    ParsedDocumentRecord,
    SourceDocumentRecord,
    VerifiedContentRecord,
)
from courserag.persistence.writeback_repository import WritebackRepository
from courserag.security import PrincipalRole, TrustedPrincipal


class FakeEmbedding:
    identity = "fake-embedding-v1"

    def embed_documents(self, texts):
        return [[float(len(text)), 1.0] for text in texts]

    def embed_query(self, text):
        return [float(len(text)), 1.0]


def _setup(tmp_path: Path) -> tuple[Session, VerifiedWritebackService, str]:
    engine = create_engine("sqlite://")
    CourseRAGBase.metadata.create_all(engine)
    session = Session(engine)
    kb = KnowledgeBaseRecord(course_id="course-1", name="Course")
    session.add(kb)
    session.flush()
    source = SourceDocumentRecord(
        knowledge_base_id=kb.id,
        filename="book.pdf",
        document_type="pdf",
        status="ready",
    )
    session.add(source)
    session.flush()
    version = DocumentVersionRecord(
        source_document_id=source.id,
        version_number=1,
        content_sha256="a" * 64,
        object_uri="artifact://source",
        mime_type="application/pdf",
        size_bytes=10,
        status="ready",
    )
    session.add(version)
    session.flush()
    parsed = ParsedDocumentRecord(
        document_version_id=version.id,
        parser_profile="p",
        parser_version="1",
        status="ready",
    )
    session.add(parsed)
    session.flush()
    evidence = EvidenceRecord(
        parsed_document_id=parsed.id,
        stable_key="ev-1",
        evidence_type="paragraph",
        text="verified source",
        content_sha256="b" * 64,
    )
    session.add(evidence)
    session.commit()
    repository = WritebackRepository(session)
    publisher = VerifiedOverlayPublisher(
        repository,
        FileArtifactStore(tmp_path / "artifacts"),
        FakeEmbedding(),
    )
    return session, VerifiedWritebackService(repository, publisher), evidence.id


def _principal(role: PrincipalRole = PrincipalRole.OWNER) -> TrustedPrincipal:
    return TrustedPrincipal(principal_id="teacher-1", course_id="course-1", roles={role})


def _request(evidence_id: str, *, key: str = "write-1") -> VerifiedContentWriteRequest:
    return VerifiedContentWriteRequest(
        context=RequestContext(idempotency_key=key),
        course_id="course-1",
        content_type=VerifiedContentType.VERIFIED_QUESTION,
        content={"question": "What?", "answer": "This."},
        evidence_ids=[evidence_id],
        approved_by="teacher-1",
        task_id="task-1",
        approval_record_id="approval-1",
    )


def test_write_replay_revoke_and_primary_pointer_is_untouched(tmp_path: Path) -> None:
    session, service, evidence_id = _setup(tmp_path)
    request = _request(evidence_id)
    created = service.write(request, principal=_principal())
    replay = service.write(request, principal=_principal())
    assert created.created is True
    assert created.status == VerifiedContentStatus.PENDING_ENRICHMENT
    assert replay.created is False
    assert replay.verified_content_id == created.verified_content_id
    kb = session.scalar(select(KnowledgeBaseRecord))
    assert kb is not None and kb.active_index_version_id is None
    revoke = RevokeVerifiedContentRequest(
        context=RequestContext(idempotency_key="revoke-1"),
        course_id="course-1",
        verified_content_id=created.verified_content_id,
        revoked_by="owner-1",
        reason="obsolete",
    )
    result = service.revoke(revoke, principal=_principal())
    replay_revoke = service.revoke(revoke, principal=_principal())
    assert result.revoked is True
    assert replay_revoke.revoked is False
    assert result.overlay_index_version != created.overlay_index_version


def test_write_rejects_cross_course_and_idempotency_conflict(tmp_path: Path) -> None:
    _, service, evidence_id = _setup(tmp_path)
    request = _request(evidence_id)
    service.write(request, principal=_principal())
    changed = _request(evidence_id)
    changed.content["answer"] = "Different"
    with pytest.raises(CourseRAGError) as conflict:
        service.write(changed, principal=_principal())
    assert conflict.value.code == ErrorCode.IDEMPOTENCY_CONFLICT
    with pytest.raises(CourseRAGError) as forbidden:
        service.write(
            _request(evidence_id, key="write-2"),
            principal=TrustedPrincipal(
                principal_id="teacher-2",
                course_id="course-2",
                roles={PrincipalRole.OWNER},
            ),
        )
    assert forbidden.value.code == ErrorCode.FORBIDDEN


def test_overlay_failure_rolls_back_verified_content(tmp_path: Path, monkeypatch) -> None:
    session, service, evidence_id = _setup(tmp_path)
    monkeypatch.setattr(service.overlay_publisher.artifact_store, "verify", lambda *_: False)
    with pytest.raises(RuntimeError, match="verification failed"):
        service.write(_request(evidence_id), principal=_principal())
    assert session.scalar(select(VerifiedContentRecord)) is None


def test_writeback_enrichment_republishes_searchable_overlay_once(tmp_path: Path) -> None:
    session, service, evidence_id = _setup(tmp_path)
    created = service.write(_request(evidence_id), principal=_principal())
    first_overlay = created.overlay_index_version
    repository = service.repository
    batch_result = EnrichmentService(repository, profile_sha256="c" * 64).start(
        StartEnrichmentBatchRequest(course_id="course-1", actor_id="teacher-1", manual=True),
        principal=_principal(),
    )
    assert batch_result.created is True and batch_result.batch_id is not None

    assert run_enrichment_batch(
        repository,
        batch_result.batch_id,
        overlay_publisher=service.overlay_publisher,
    )
    assert not run_enrichment_batch(
        repository,
        batch_result.batch_id,
        overlay_publisher=service.overlay_publisher,
    )
    content = repository.get_content(created.verified_content_id)
    assert content is not None and content.status == "enriched"
    assert content.current_overlay_version_id != first_overlay
    assert content.current_overlay_version_id is not None
    manifest_uri = repository.overlay_manifest_uri(content.current_overlay_version_id)
    assert manifest_uri is not None
    hits = service.overlay_publisher.search(manifest_uri, "What", top_k=5)
    assert [hit.verified_content_id for hit in hits] == [created.verified_content_id]
    assert hits[0].evidence_ids == (evidence_id,)
    kb = session.scalar(select(KnowledgeBaseRecord))
    assert kb is not None and kb.active_index_version_id is None
