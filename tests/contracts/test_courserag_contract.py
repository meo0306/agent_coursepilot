from __future__ import annotations

import ast
import hashlib
import json
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from langchain_core.documents import Document as LangChainDocument
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from coursepilot.adapters.local_courserag import LocalCourseRAGAdapter
from coursepilot.adapters.mock_courserag import MockCourseRAGService
from coursepilot.clients.remote_courserag import RemoteCourseRAGClient
from coursepilot.db.base import Base
from coursepilot.models import Course, Document
from coursepilot.ports.courserag import CourseRAGServicePort
from courserag.api.http_schema import (
    CAPABILITIES_PATH,
    build_path,
    document_builds_path,
    knowledge_base_search_path,
)
from courserag.contracts import (
    BuildJob,
    BuildProgress,
    BuildStatus,
    CapabilitiesResponse,
    ContextRequest,
    CourseRAGError,
    CourseRAGOperation,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    QueryTrace,
    RequestContext,
    ResponseMeta,
    RetrievalOptions,
    RetrievalTrace,
    ScoreBreakdown,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SourceTier,
    StartBuildRequest,
)


@dataclass
class ContractHarness:
    service: CourseRAGServicePort
    course_id: str
    document_id: str
    other_document_id: str


class FakeVectorStore:
    def search(self, **kwargs):
        return [
            (
                LangChainDocument(
                    page_content="启发式搜索使用领域知识指导搜索。",
                    metadata={
                        "chunk_id": "chunk-contract",
                        "course_id": kwargs["course_id"],
                        "document_id": "doc-contract",
                        "source_type": "textbook",
                        "chapter": "第1章",
                        "section": "1.1",
                        "page": 3,
                        "title": "启发式搜索",
                        "verified": False,
                    },
                ),
                0.9,
            )
        ][: kwargs["top_k"]]


@pytest.fixture(params=["local", "mock", "remote"])
def contract_harness(
    request: pytest.FixtureRequest,
) -> Generator[ContractHarness, None, None]:
    if request.param == "local":
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            course = Course(course_name="Contract")
            session.add(course)
            session.flush()
            documents = [
                Document(
                    course_id=course.id,
                    file_name=f"{name}.pdf",
                    file_path=f"{name}.pdf",
                    file_type="pdf",
                    source_type="textbook",
                )
                for name in ("first", "second")
            ]
            session.add_all(documents)
            session.commit()
            yield ContractHarness(
                service=LocalCourseRAGAdapter(session, vector_store=FakeVectorStore()),
                course_id=course.id,
                document_id=documents[0].id,
                other_document_id=documents[1].id,
            )
        Base.metadata.drop_all(engine)
        engine.dispose()
        return

    if request.param == "mock":
        service = MockCourseRAGService()
        service.seed_search("course-contract", [_contract_hit()])
        yield ContractHarness(
            service=service,
            course_id="course-contract",
            document_id="doc-contract",
            other_document_id="doc-other",
        )
        return

    jobs_by_key: dict[str, tuple[str, BuildJob]] = {}

    def handler(http_request: httpx.Request) -> httpx.Response:
        payload = json.loads(http_request.content.decode("utf-8") or "{}")
        context = RequestContext.model_validate(
            payload["context"] if "context" in payload else payload
        )
        if http_request.method == "GET" and http_request.url.path == CAPABILITIES_PATH:
            return httpx.Response(
                200,
                json=CapabilitiesResponse(
                    supported_operations=[
                        CourseRAGOperation.START_BUILD,
                        CourseRAGOperation.GET_BUILD_JOB,
                        CourseRAGOperation.SEARCH,
                    ]
                ).model_dump(mode="json"),
            )
        if http_request.method == "POST" and http_request.url.path == knowledge_base_search_path(
            "course-contract"
        ):
            search_request = SearchRequest.model_validate(payload)
            return httpx.Response(
                200,
                json=SearchResponse(
                    meta=ResponseMeta.from_context(search_request.context),
                    query=QueryTrace(
                        original=search_request.query,
                        normalized=search_request.query,
                    ),
                    hits=[_contract_hit()],
                    retrieval=RetrievalTrace(
                        retrieval_config_version="remote-fake-v1",
                        index_version="remote-fake-index-v1",
                        candidate_count=1,
                        returned_count=1,
                    ),
                ).model_dump(mode="json"),
            )
        if http_request.method == "POST" and http_request.url.path in {
            document_builds_path("doc-contract"),
            document_builds_path("doc-other"),
        }:
            build_request = StartBuildRequest.model_validate(payload)
            key = http_request.headers["Idempotency-Key"]
            semantic_payload = build_request.model_dump(mode="json", exclude={"context"})
            request_hash = hashlib.sha256(
                json.dumps(
                    semantic_payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            existing = jobs_by_key.get(key)
            if existing is not None:
                existing_hash, job = existing
                if existing_hash != request_hash:
                    return _error_response(
                        context,
                        ErrorCode.IDEMPOTENCY_CONFLICT,
                        "Idempotency conflict.",
                        status_code=409,
                    )
                return httpx.Response(
                    200,
                    json=job.model_copy(
                        update={"meta": ResponseMeta.from_context(context)}
                    ).model_dump(mode="json"),
                )
            now = datetime.now(UTC)
            job = BuildJob(
                meta=ResponseMeta.from_context(context),
                job_id="remote-build-1",
                course_id=build_request.course_id,
                status=BuildStatus.QUEUED,
                progress=BuildProgress(completed_units=0, total_units=100, percent=0),
                document_versions={document_id: "v1" for document_id in build_request.document_ids},
                target_index_version="remote-fake-index-v1",
                created_at=now,
                updated_at=now,
            )
            jobs_by_key[key] = (request_hash, job)
            return httpx.Response(202, json=job.model_dump(mode="json"))
        if http_request.method == "GET" and http_request.url.path == build_path("missing-build"):
            return _error_response(
                context,
                ErrorCode.RESOURCE_NOT_FOUND,
                "Build job not found.",
                status_code=404,
            )
        raise AssertionError(
            f"Unexpected remote contract request: {http_request.method} {http_request.url.path}"
        )

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        yield ContractHarness(
            service=RemoteCourseRAGClient(http_client),
            course_id="course-contract",
            document_id="doc-contract",
            other_document_id="doc-other",
        )


def _contract_hit() -> SearchHit:
    return SearchHit(
        rank=1,
        chunk_id="chunk-contract",
        document_id="doc-contract",
        document_version="v1",
        document_type="textbook",
        title="启发式搜索",
        section_path=["第1章", "1.1"],
        page_start=3,
        page_end=3,
        text="启发式搜索使用领域知识指导搜索。",
        scores=ScoreBreakdown(dense=0.9),
        evidence_ids=[],
        source_tier=SourceTier.PRIMARY_SOURCE,
    )


def _error_response(
    context: RequestContext,
    code: ErrorCode,
    message: str,
    *,
    status_code: int,
) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=ErrorResponse(
            meta=ResponseMeta.from_context(context),
            error=ErrorDetail(code=code, message=message),
        ).model_dump(mode="json"),
    )


def test_all_implementations_satisfy_service_protocol(
    contract_harness: ContractHarness,
) -> None:
    assert isinstance(contract_harness.service, CourseRAGServicePort)


def test_all_implementations_round_trip_search_meta(
    contract_harness: ContractHarness,
) -> None:
    context = RequestContext(request_id="req-contract", trace_id="trace-contract")
    response = contract_harness.service.search(
        SearchRequest(
            context=context,
            course_id=contract_harness.course_id,
            query="启发式搜索",
            retrieval=RetrievalOptions(
                candidate_k=5,
                rerank_top_n=5,
                return_top_n=5,
            ),
        )
    )

    assert response.meta.request_id == "req-contract"
    assert response.meta.trace_id == "trace-contract"
    assert response.hits[0].chunk_id == "chunk-contract"
    assert response.retrieval.returned_count == len(response.hits)


def test_all_implementations_replay_build_idempotently(
    contract_harness: ContractHarness,
) -> None:
    first_context = RequestContext(
        request_id="req-build-1",
        trace_id="trace-build",
        idempotency_key="contract-build-key",
    )
    first = contract_harness.service.start_build(
        StartBuildRequest(
            context=first_context,
            course_id=contract_harness.course_id,
            document_ids=[contract_harness.document_id],
        )
    )
    replay = contract_harness.service.start_build(
        StartBuildRequest(
            context=RequestContext(
                request_id="req-build-2",
                trace_id="trace-build",
                idempotency_key="contract-build-key",
            ),
            course_id=contract_harness.course_id,
            document_ids=[contract_harness.document_id],
        )
    )

    assert first.job_id == replay.job_id
    assert replay.meta.request_id == "req-build-2"

    with pytest.raises(CourseRAGError) as exc_info:
        contract_harness.service.start_build(
            StartBuildRequest(
                context=RequestContext(idempotency_key="contract-build-key"),
                course_id=contract_harness.course_id,
                document_ids=[contract_harness.other_document_id],
            )
        )
    assert exc_info.value.code == ErrorCode.IDEMPOTENCY_CONFLICT


def test_all_implementations_return_structured_not_found(
    contract_harness: ContractHarness,
) -> None:
    context = RequestContext(request_id="req-missing", trace_id="trace-missing")

    with pytest.raises(CourseRAGError) as exc_info:
        contract_harness.service.get_build_job("missing-build", context)

    assert exc_info.value.code == ErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.response.meta.request_id == "req-missing"


def test_contract_rejects_naive_utc_timestamp() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        BuildJob(
            meta=ResponseMeta(
                request_id="req-1",
                trace_id="trace-1",
            ),
            job_id="build-1",
            course_id="course-1",
            status=BuildStatus.QUEUED,
            progress=BuildProgress(completed_units=0, total_units=100, percent=0),
            created_at=datetime.now(),
            updated_at=datetime.now(UTC),
        )


def test_source_tier_contract_matches_frozen_values() -> None:
    assert {item.value for item in SourceTier} == {
        "primary_source",
        "teacher_verified",
        "external_reference",
        "generated_draft",
    }


def test_context_request_inherits_frozen_empty_search_request() -> None:
    context = RequestContext(request_id="req-context", trace_id="trace-context")

    request = ContextRequest.model_validate(
        {
            "context": context.model_dump(mode="json"),
            "course_id": "course-1",
            "query": "query",
            "purpose": "lesson_generation",
            "search_request": {},
        }
    )

    assert request.search_request is not None
    assert request.search_request.course_id == request.course_id
    assert request.search_request.query == request.query
    assert request.search_request.context == request.context


@pytest.mark.parametrize(
    "search_request",
    [
        SearchRequest(course_id="course-2", query="query"),
        SearchRequest(course_id="course-1", query="different"),
        SearchRequest(
            context=RequestContext(request_id="other-request", trace_id="other-trace"),
            course_id="course-1",
            query="query",
        ),
    ],
)
def test_context_request_rejects_inconsistent_nested_search(
    search_request: SearchRequest,
) -> None:
    with pytest.raises(ValidationError):
        ContextRequest(
            context=RequestContext(request_id="outer-request", trace_id="outer-trace"),
            course_id="course-1",
            query="query",
            purpose="lesson_generation",
            search_request=search_request,
        )


def test_graph_nodes_do_not_import_chroma_parser_or_legacy_retriever() -> None:
    node_root = Path("src/agents/coursepilot/nodes")
    banned_modules = {
        "coursepilot.rag.parsers",
        "coursepilot.rag.retriever",
        "coursepilot.rag.vector_store",
        "langchain_chroma",
    }
    violations: list[str] = []

    for path in node_root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in banned_modules:
                violations.append(f"{path}:{node.lineno}:{node.module}")
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in banned_modules:
                        violations.append(f"{path}:{node.lineno}:{alias.name}")

    assert violations == []
