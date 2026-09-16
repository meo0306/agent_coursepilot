from __future__ import annotations

import httpx
import pytest

from coursepilot.clients.remote_courserag import RemoteCourseRAGClient
from courserag.api.http_schema import knowledge_base_search_path
from courserag.contracts import (
    CourseRAGError,
    ErrorCode,
    ErrorDetail,
    ErrorResponse,
    QueryTrace,
    RequestContext,
    ResponseMeta,
    RetrievalTrace,
    SearchRequest,
    SearchResponse,
)


def test_remote_client_serializes_search_contract_and_trace_headers() -> None:
    request = SearchRequest(
        context=RequestContext(request_id="req-1", trace_id="trace-1"),
        course_id="course-1",
        query="启发式搜索",
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert http_request.url.path == knowledge_base_search_path("course-1")
        assert http_request.headers["X-Request-ID"] == "req-1"
        assert http_request.headers["X-Trace-ID"] == "trace-1"
        return httpx.Response(
            200,
            json=SearchResponse(
                meta=ResponseMeta.from_context(request.context),
                query=QueryTrace(original=request.query, normalized=request.query),
                hits=[],
                retrieval=RetrievalTrace(
                    retrieval_config_version="fake-v1",
                    index_version="fake-index-v1",
                    candidate_count=0,
                    returned_count=0,
                ),
            ).model_dump(mode="json"),
        )

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        response = RemoteCourseRAGClient(http_client).search(request)

    assert response.meta.trace_id == "trace-1"
    assert response.hits == []


def test_remote_client_maps_structured_error_without_fallback() -> None:
    request = SearchRequest(course_id="course-1", query="query")

    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json=ErrorResponse(
                meta=ResponseMeta.from_context(request.context),
                error=ErrorDetail(
                    code=ErrorCode.INDEX_NOT_READY,
                    message="building",
                    retryable=True,
                    retry_after_ms=1000,
                ),
            ).model_dump(mode="json"),
        )

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        with pytest.raises(CourseRAGError) as exc_info:
            RemoteCourseRAGClient(http_client).search(request)

    assert exc_info.value.code == ErrorCode.INDEX_NOT_READY
    assert exc_info.value.response.error.retry_after_ms == 1000


def test_remote_client_encodes_opaque_path_segments() -> None:
    request = SearchRequest(
        context=RequestContext(request_id="req-path", trace_id="trace-path"),
        course_id="../capabilities?admin=true",
        query="query",
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        assert b"%2E%2E%2Fcapabilities%3Fadmin%3Dtrue" in http_request.url.raw_path
        assert http_request.url.query == b""
        return httpx.Response(
            200,
            json=SearchResponse(
                meta=ResponseMeta.from_context(request.context),
                query=QueryTrace(original=request.query, normalized=request.query),
                hits=[],
                retrieval=RetrievalTrace(
                    retrieval_config_version="fake-v1",
                    index_version="fake-index-v1",
                    candidate_count=0,
                    returned_count=0,
                ),
            ).model_dump(mode="json"),
        )

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        response = RemoteCourseRAGClient(http_client).search(request)

    assert response.meta.request_id == request.context.request_id


@pytest.mark.parametrize(
    ("meta", "expected_code"),
    [
        (
            ResponseMeta(
                request_id="server-request",
                trace_id="trace-1",
            ),
            ErrorCode.INTERNAL_ERROR,
        ),
        (
            ResponseMeta(
                request_id="req-1",
                trace_id="server-trace",
            ),
            ErrorCode.INTERNAL_ERROR,
        ),
        (
            ResponseMeta(
                request_id="req-1",
                trace_id="trace-1",
                api_version="v999",
            ),
            ErrorCode.VERSION_CONFLICT,
        ),
    ],
)
def test_remote_client_rejects_mismatched_success_metadata(
    meta: ResponseMeta,
    expected_code: ErrorCode,
) -> None:
    request = SearchRequest(
        context=RequestContext(request_id="req-1", trace_id="trace-1"),
        course_id="course-1",
        query="query",
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=SearchResponse(
                meta=meta,
                query=QueryTrace(original=request.query, normalized=request.query),
                hits=[],
                retrieval=RetrievalTrace(
                    retrieval_config_version="fake-v1",
                    index_version="fake-index-v1",
                    candidate_count=0,
                    returned_count=0,
                ),
            ).model_dump(mode="json"),
        )

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        with pytest.raises(CourseRAGError) as exc_info:
            RemoteCourseRAGClient(http_client).search(request)

    assert exc_info.value.code == expected_code
    assert exc_info.value.response.meta.request_id == request.context.request_id
    assert exc_info.value.response.meta.trace_id == request.context.trace_id


def test_remote_client_rejects_mismatched_error_metadata() -> None:
    request = SearchRequest(
        context=RequestContext(request_id="req-1", trace_id="trace-1"),
        course_id="course-1",
        query="query",
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            503,
            json=ErrorResponse(
                meta=ResponseMeta(
                    request_id="server-request",
                    trace_id="server-trace",
                ),
                error=ErrorDetail(
                    code=ErrorCode.INDEX_NOT_READY,
                    message="building",
                ),
            ).model_dump(mode="json"),
        )

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        with pytest.raises(CourseRAGError) as exc_info:
            RemoteCourseRAGClient(http_client).search(request)

    assert exc_info.value.code == ErrorCode.INTERNAL_ERROR
    assert exc_info.value.response.meta.request_id == request.context.request_id
    assert exc_info.value.response.meta.trace_id == request.context.trace_id


def test_remote_client_rejects_unsupported_request_version_before_transport() -> None:
    request = SearchRequest(
        context=RequestContext(api_version="v999"),
        course_id="course-1",
        query="query",
    )

    def handler(http_request: httpx.Request) -> httpx.Response:
        raise AssertionError("transport must not be called")

    with httpx.Client(
        base_url="https://courserag.invalid",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        with pytest.raises(CourseRAGError) as exc_info:
            RemoteCourseRAGClient(http_client).search(request)

    assert exc_info.value.code == ErrorCode.VERSION_CONFLICT
