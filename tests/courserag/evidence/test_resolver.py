from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from courserag.evidence.builder import EvidenceBuilder
from courserag.evidence.materialize import materialize_evidence_artifact
from courserag.evidence.resolver import EvidenceNotFoundError, EvidenceResolver
from courserag.persistence.base import CourseRAGBase
from courserag.persistence.materialize import materialize_parsed_document
from courserag.persistence.models import (
    ArtifactRecord,
    DocumentVersionRecord,
    KnowledgeBaseRecord,
    SourceDocumentRecord,
)
from courserag.persistence.repositories import CourseRAGRepository
from tests.courserag.evidence.test_builder import _document


def _resolver(tmp_path: Path) -> tuple[EvidenceResolver, list[str]]:
    engine = create_engine(f"sqlite:///{tmp_path / 'resolver.db'}")
    CourseRAGBase.metadata.create_all(engine)
    session = Session(engine)
    repository = CourseRAGRepository(session)
    repository.add(KnowledgeBaseRecord(id="kb-1", course_id="course-1", name="Course"))
    repository.add(
        SourceDocumentRecord(
            id="doc-1",
            knowledge_base_id="kb-1",
            filename="fixture.pdf",
            document_type="pdf",
        )
    )
    repository.add(
        DocumentVersionRecord(
            id="version-1",
            source_document_id="doc-1",
            version_number=1,
            content_sha256="a" * 64,
            object_uri="fixture://document",
            mime_type="application/pdf",
            size_bytes=1,
        )
    )
    artifact = ArtifactRecord(
        id="artifact-1",
        uri="fixture://parsed",
        sha256="b" * 64,
        size_bytes=1,
        media_type="application/zip",
        status="available",
    )
    repository.add(artifact)
    repository.flush()
    parsed = materialize_parsed_document(repository, document=_document(), artifact=artifact)
    evidence = EvidenceBuilder().build(_document())
    materialize_evidence_artifact(
        repository,
        parsed_document_id=parsed.id,
        artifact=evidence,
    )
    session.commit()
    return EvidenceResolver(repository), [record.evidence_id for record in evidence.records]


def test_resolver_round_trips_and_previews_adjacency(tmp_path: Path) -> None:
    resolver, ids = _resolver(tmp_path)

    first = resolver.resolve("course-1", ids[0])
    preview = resolver.source_preview("course-1", ids[1], max_context_chars=20)

    assert first.evidence_id == ids[0]
    assert first.next_evidence_id == ids[1]
    assert preview.evidence.evidence_id == ids[1]
    assert preview.previous_text is not None
    assert len(preview.previous_text) <= 20


def test_batch_resolver_preserves_order_and_isolates_course(tmp_path: Path) -> None:
    resolver, ids = _resolver(tmp_path)

    batch = resolver.batch_resolve("course-1", [ids[1], "ev1_" + "f" * 64, ids[0]])

    assert [record.evidence_id for record in batch.records] == [ids[1], ids[0]]
    assert batch.missing_ids == ("ev1_" + "f" * 64,)
    with pytest.raises(EvidenceNotFoundError):
        resolver.resolve("other-course", ids[0])
