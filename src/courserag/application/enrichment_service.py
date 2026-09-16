from __future__ import annotations

from datetime import UTC, datetime

from courserag.contracts import (
    CourseRAGError,
    EnrichmentBatchResult,
    EnrichmentTriggerReason,
    ErrorCode,
    ResponseMeta,
    StartEnrichmentBatchRequest,
)
from courserag.jobs.enrichment import PendingEnrichment, plan_enrichment_batch
from courserag.persistence.models import EnrichmentBatchRecord
from courserag.persistence.writeback_repository import WritebackRepository
from courserag.security import PrincipalRole, TrustedPrincipal, require_course_role


class EnrichmentService:
    def __init__(self, repository: WritebackRepository, *, profile_sha256: str) -> None:
        self.repository = repository
        self.profile_sha256 = profile_sha256

    def start(
        self,
        request: StartEnrichmentBatchRequest,
        *,
        principal: TrustedPrincipal,
    ) -> EnrichmentBatchResult:
        try:
            require_course_role(principal, request.course_id, PrincipalRole.OWNER)
        except PermissionError as exc:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message=str(exc),
            ) from exc
        knowledge_base = self.repository.knowledge_base_for_course(request.course_id)
        if knowledge_base is None:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Knowledge base not found.",
            )
        pending = self.repository.pending_enrichment(knowledge_base.id)
        plan = plan_enrichment_batch(
            [
                PendingEnrichment(
                    content_id=item.id,
                    token_count=item.token_count,
                    created_at=item.created_at,
                )
                for item in pending
            ],
            now=datetime.now(UTC),
            profile_sha256=self.profile_sha256,
            manual=request.manual,
        )
        if plan is None:
            self.repository.session.rollback()
            return EnrichmentBatchResult(
                meta=ResponseMeta.from_context(request.context),
                created=False,
            )
        existing = self.repository.get_enrichment_batch_by_identity(plan.identity_sha256)
        if existing is not None:
            self.repository.session.rollback()
            return EnrichmentBatchResult(
                meta=ResponseMeta.from_context(request.context),
                batch_id=existing.id,
                created=False,
                trigger_reason=EnrichmentTriggerReason(plan.trigger.value),
                item_count=len(plan.content_ids),
            )
        batch = EnrichmentBatchRecord(
            knowledge_base_id=knowledge_base.id,
            status="pending",
            actor_id=principal.principal_id,
            identity_sha256=plan.identity_sha256,
            trigger_reason=plan.trigger.value,
            trigger_snapshot_json={"content_ids": list(plan.content_ids)},
            profile_sha256=self.profile_sha256,
            request_sha256=plan.identity_sha256,
        )
        self.repository.add_enrichment_batch(
            batch,
            content_ids=plan.content_ids,
            profile_sha256=self.profile_sha256,
        )
        self.repository.session.commit()
        return EnrichmentBatchResult(
            meta=ResponseMeta.from_context(request.context),
            batch_id=batch.id,
            created=True,
            trigger_reason=EnrichmentTriggerReason(plan.trigger.value),
            item_count=len(plan.content_ids),
        )
