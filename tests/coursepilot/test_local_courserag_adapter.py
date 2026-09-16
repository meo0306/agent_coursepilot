from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.db.base import Base
from coursepilot.models import Course, Document
from coursepilot.schemas.kb_schema import KBSearchResult
from courserag.contracts import (
    CourseRAGError,
    ErrorCode,
    FileReference,
    ListDocumentsRequest,
    RegisterDocumentRequest,
    RequestContext,
    RetrievalOptions,
    SearchFilters,
    SearchRequest,
    SourceTier,
    StartBuildRequest,
)


@pytest.fixture
def local_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def _seed_document(session: Session) -> tuple[Course, Document]:
    course = Course(course_name="AI")
    session.add(course)
    session.flush()
    document = Document(
        course_id=course.id,
        file_name="textbook.pdf",
        file_path="unused.pdf",
        file_type="pdf",
        source_type="textbook",
    )
    session.add(document)
    session.commit()
    session.refresh(course)
    session.refresh(document)
    return course, document


def test_local_adapter_start_build_is_idempotent(local_session: Session) -> None:
    course, document = _seed_document(local_session)
    adapter = LocalCourseRAGAdapter(local_session)
    context = RequestContext(idempotency_key="build-once")
    request = StartBuildRequest(
        context=context,
        course_id=course.id,
        document_ids=[document.id],
    )

    first = adapter.start_build(request)
    second = adapter.start_build(
        request.model_copy(
            update={
                "context": RequestContext(
                    request_id="req_retry",
                    trace_id=context.trace_id,
                    idempotency_key="build-once",
                )
            }
        )
    )

    assert first.job_id == second.job_id
    assert first.status == second.status


def test_local_adapter_rejects_idempotency_key_reuse(local_session: Session) -> None:
    course, document = _seed_document(local_session)
    other = Document(
        course_id=course.id,
        file_name="other.pdf",
        file_path="unused-other.pdf",
        file_type="pdf",
        source_type="textbook",
    )
    local_session.add(other)
    local_session.commit()
    adapter = LocalCourseRAGAdapter(local_session)
    adapter.start_build(
        StartBuildRequest(
            context=RequestContext(idempotency_key="same-key"),
            course_id=course.id,
            document_ids=[document.id],
        )
    )

    with pytest.raises(CourseRAGError) as exc_info:
        adapter.start_build(
            StartBuildRequest(
                context=RequestContext(idempotency_key="same-key"),
                course_id=course.id,
                document_ids=[other.id],
            )
        )

    assert exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


def test_local_adapter_lists_legacy_documents(local_session: Session) -> None:
    course, document = _seed_document(local_session)

    page = LocalCourseRAGAdapter(local_session).list_documents(
        ListDocumentsRequest(course_id=course.id)
    )

    assert [item.document_id for item in page.documents] == [document.id]
    assert page.documents[0].document_version == "legacy-unversioned"
    assert page.documents[0].created_at.tzinfo is not None


def test_local_adapter_maps_search_without_fabricating_evidence(monkeypatch) -> None:
    class FakeRetriever:
        def __init__(self, vector_store) -> None:
            self.vector_store = vector_store

        def search(self, **kwargs) -> list[KBSearchResult]:
            assert kwargs["course_id"] == "course-1"
            return [
                KBSearchResult(
                    chunk_id="chunk-1",
                    course_id="course-1",
                    document_id="doc-1",
                    source_type="textbook",
                    chapter="第1章",
                    section="1.1",
                    page=3,
                    title="导论",
                    content="启发式搜索",
                    score=0.9,
                    verified=False,
                )
            ]

    monkeypatch.setattr(
        "coursepilot.adapters.local_courserag.CoursePilotRetriever",
        FakeRetriever,
    )
    adapter = LocalCourseRAGAdapter(vector_store=object())

    response = adapter.search(
        SearchRequest(
            course_id="course-1",
            query="启发式搜索",
            retrieval=RetrievalOptions(
                candidate_k=5,
                rerank_top_n=5,
                return_top_n=5,
            ),
        )
    )

    assert response.hits[0].chunk_id == "chunk-1"
    assert response.hits[0].document_version == "legacy-unversioned"
    assert response.hits[0].evidence_ids == []
    assert "LEGACY_CHUNKS_HAVE_NO_STABLE_EVIDENCE_IDS" in response.meta.warnings


@pytest.mark.parametrize(
    ("filters", "retrieval"),
    [
        (
            SearchFilters(section_paths=[["chapter", "section"]]),
            RetrievalOptions(candidate_k=5, rerank_top_n=5, return_top_n=5),
        ),
        (
            SearchFilters(),
            RetrievalOptions(candidate_k=30, rerank_top_n=8, return_top_n=5),
        ),
        (
            SearchFilters(source_tiers=[SourceTier.EXTERNAL_REFERENCE]),
            RetrievalOptions(candidate_k=5, rerank_top_n=5, return_top_n=5),
        ),
    ],
)
def test_local_adapter_fails_closed_for_unsupported_search_options(
    filters: SearchFilters,
    retrieval: RetrievalOptions,
) -> None:
    adapter = LocalCourseRAGAdapter(vector_store=object())

    with pytest.raises(CourseRAGError) as exc_info:
        adapter.search(
            SearchRequest(
                course_id="course-1",
                query="query",
                filters=filters,
                retrieval=retrieval,
            )
        )

    assert exc_info.value.code == ErrorCode.FEATURE_NOT_AVAILABLE


def test_local_adapter_maps_backend_errors_without_leaking_details(monkeypatch) -> None:
    class FailingRetriever:
        def __init__(self, vector_store) -> None:
            pass

        def search(self, **kwargs) -> list[KBSearchResult]:
            raise RuntimeError("secret backend path")

    monkeypatch.setattr(
        "coursepilot.adapters.local_courserag.CoursePilotRetriever",
        FailingRetriever,
    )
    adapter = LocalCourseRAGAdapter(vector_store=object())

    with pytest.raises(CourseRAGError) as exc_info:
        adapter.search(
            SearchRequest(
                course_id="course-1",
                query="query",
                retrieval=RetrievalOptions(
                    candidate_k=5,
                    rerank_top_n=5,
                    return_top_n=5,
                ),
            )
        )

    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    assert "secret backend path" not in str(exc_info.value)


def test_local_adapter_explicitly_rejects_later_phase_capability() -> None:
    adapter = LocalCourseRAGAdapter()

    with pytest.raises(CourseRAGError) as exc_info:
        adapter.register_document(
            RegisterDocumentRequest(
                course_id="course-1",
                file=FileReference(
                    object_uri="file:///unused.pdf",
                    filename="unused.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    sha256="0" * 64,
                ),
                document_type="textbook",
            )
        )

    assert exc_info.value.code == ErrorCode.FEATURE_NOT_AVAILABLE
