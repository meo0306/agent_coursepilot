from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.db.session import get_session
from courserag.api.http_schema import API_PREFIX
from courserag.api.principal import trusted_principal
from courserag.api.retrieval_qa import _api_error, _bind_context, _request_context
from courserag.application.enrichment_service import EnrichmentService
from courserag.application.writeback_service import VerifiedWritebackService
from courserag.contracts import (
    EnrichmentBatchResult,
    RequestContext,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    StartEnrichmentBatchRequest,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
)
from courserag.indexing.dense import (
    LocalSentenceTransformerEmbeddingAdapter,
    OpenAICompatibleEmbeddingAdapter,
)
from courserag.indexing.verified_overlay import VerifiedOverlayPublisher
from courserag.jobs.artifacts import FileArtifactStore
from courserag.persistence.writeback_repository import WritebackRepository
from courserag.security import TrustedPrincipal

router = APIRouter(prefix=API_PREFIX, tags=["CourseRAG Verified Content"])


def _writeback(session: Session) -> VerifiedWritebackService:
    repository = WritebackRepository(session)
    publisher = VerifiedOverlayPublisher(
        repository,
        FileArtifactStore(Path(settings.COURSERAG_ARTIFACT_DIR) / "verified-overlay"),
        _embedding_adapter(),
    )
    return VerifiedWritebackService(repository, publisher)


def _embedding_adapter():
    if settings.COURSERAG_EMBEDDING_PROVIDER == "local_sentence_transformers":
        required = (
            settings.COURSERAG_EMBEDDING_MODEL_PATH,
            settings.COURSERAG_EMBEDDING_MODEL,
            settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256,
            settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256,
        )
        if not all(required):
            raise RuntimeError("Verified overlay requires the frozen local Embedding configuration")
        return LocalSentenceTransformerEmbeddingAdapter(
            model_path=settings.COURSERAG_EMBEDDING_MODEL_PATH,
            model_name=settings.COURSERAG_EMBEDDING_MODEL,
            model_bundle_sha256=settings.COURSERAG_EMBEDDING_MODEL_BUNDLE_SHA256,
            weights_sha256=settings.COURSERAG_EMBEDDING_WEIGHTS_SHA256,
            device=settings.COURSERAG_EMBEDDING_DEVICE,
            dtype=settings.COURSERAG_EMBEDDING_DTYPE,
            max_length=settings.COURSERAG_EMBEDDING_MAX_LENGTH,
            batch_size=settings.COURSERAG_EMBEDDING_LOCAL_BATCH_SIZE,
            query_prompt_name=settings.COURSERAG_EMBEDDING_QUERY_PROMPT_NAME,
        )
    if settings.COURSERAG_EMBEDDING_PROVIDER == "openai-compatible":
        if (
            settings.COURSERAG_EMBEDDING_BASE_URL is None
            or settings.COURSERAG_EMBEDDING_API_KEY is None
            or settings.COURSERAG_EMBEDDING_MODEL is None
        ):
            raise RuntimeError(
                "Verified overlay requires explicit Embedding Provider configuration"
            )
        return OpenAICompatibleEmbeddingAdapter(
            endpoint=settings.COURSERAG_EMBEDDING_BASE_URL,
            api_key=settings.COURSERAG_EMBEDDING_API_KEY.get_secret_value(),
            model=settings.COURSERAG_EMBEDDING_MODEL,
            timeout_seconds=settings.COURSERAG_EMBEDDING_TIMEOUT_SECONDS,
        )
    raise RuntimeError("Verified overlay Embedding is disabled; write-back fails closed")


@router.post(
    "/knowledge-bases/{course_id}/verified-content",
    response_model=VerifiedContentWriteResult,
)
def write_verified_content(
    course_id: str,
    payload: VerifiedContentWriteRequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    session: Annotated[Session, Depends(get_session)],
) -> VerifiedContentWriteResult:
    _bind_context(payload, headers)
    if payload.course_id != course_id:
        raise _api_error(headers, ValueError("Path course_id differs from request body"))
    try:
        return _writeback(session).write(payload, principal=principal)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc


@router.post(
    "/verified-content/{content_id}/revoke",
    response_model=RevokeVerifiedContentResult,
)
def revoke_verified_content(
    content_id: str,
    payload: RevokeVerifiedContentRequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    session: Annotated[Session, Depends(get_session)],
) -> RevokeVerifiedContentResult:
    _bind_context(payload, headers)
    if payload.verified_content_id != content_id:
        raise _api_error(headers, ValueError("Path content_id differs from request body"))
    try:
        return _writeback(session).revoke(payload, principal=principal)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc


@router.post(
    "/knowledge-bases/{course_id}/enrichment-batches",
    response_model=EnrichmentBatchResult,
)
def start_enrichment_batch(
    course_id: str,
    payload: StartEnrichmentBatchRequest,
    headers: Annotated[RequestContext, Depends(_request_context)],
    principal: Annotated[TrustedPrincipal, Depends(trusted_principal)],
    session: Annotated[Session, Depends(get_session)],
) -> EnrichmentBatchResult:
    _bind_context(payload, headers)
    if payload.course_id != course_id:
        raise _api_error(headers, ValueError("Path course_id differs from request body"))
    profile_sha256 = hashlib.sha256(b"courserag-enrichment/default-v1").hexdigest()
    try:
        service = EnrichmentService(
            WritebackRepository(session),
            profile_sha256=profile_sha256,
        )
        return service.start(payload, principal=principal)
    except Exception as exc:
        raise _api_error(payload.context, exc) from exc
