from __future__ import annotations

import hashlib
import json

from courserag.contracts import (
    CourseRAGError,
    ErrorCode,
    ResponseMeta,
    RevokeVerifiedContentRequest,
    RevokeVerifiedContentResult,
    VerifiedContentStatus,
    VerifiedContentWriteRequest,
    VerifiedContentWriteResult,
    require_idempotency_key,
)
from courserag.indexing.verified_overlay import VerifiedOverlayPublisher
from courserag.persistence.base import utc_now
from courserag.persistence.models import VerifiedContentRecord
from courserag.persistence.writeback_repository import WritebackRepository
from courserag.security.principal import PrincipalRole, TrustedPrincipal, require_course_role


class VerifiedWritebackService:
    def __init__(
        self,
        repository: WritebackRepository,
        overlay_publisher: VerifiedOverlayPublisher,
    ) -> None:
        self.repository = repository
        self.overlay_publisher = overlay_publisher

    def write(
        self,
        request: VerifiedContentWriteRequest,
        *,
        principal: TrustedPrincipal,
    ) -> VerifiedContentWriteResult:
        self._authorize(request.context, principal, request.course_id, PrincipalRole.EDITOR)
        key = require_idempotency_key(request.context)
        knowledge_base = self.repository.knowledge_base_for_course(request.course_id)
        if knowledge_base is None:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Knowledge base not found.",
            )
        request_hash = _sha256(request.model_dump(mode="json", exclude={"context"}))
        existing = self.repository.get_by_idempotency_key(knowledge_base.id, key)
        if existing is not None:
            if existing.request_sha256 != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Idempotency key was reused with different verified content.",
                )
            return self._write_result(request, existing, created=False)
        if not self.repository.evidence_belongs_to(request.evidence_ids, knowledge_base.id):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message="Evidence does not belong to the authorized course.",
            )
        if not self.repository.knowledge_points_belong_to(
            request.knowledge_point_ids, knowledge_base.id
        ):
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message="Knowledge point does not belong to the authorized course.",
            )
        body = json.dumps(
            request.content, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        content_sha256 = hashlib.sha256(body.encode()).hexdigest()
        record = VerifiedContentRecord(
            knowledge_base_id=knowledge_base.id,
            idempotency_key=key,
            content_type=request.content_type.value,
            title=_content_title(request.content),
            body=body,
            content_sha256=content_sha256,
            version_sha256=_sha256({"content": content_sha256, "version": 1}),
            request_sha256=request_hash,
            source_tier=request.source_tier.value,
            status=VerifiedContentStatus.PENDING_ENRICHMENT.value,
            retrieval_active=True,
            token_count=_estimate_tokens(body),
            approved_by=request.approved_by,
            task_id=request.task_id,
            approval_record_id=request.approval_record_id,
            source_metadata_json={"principal_id": principal.principal_id},
        )
        try:
            self.repository.add_content(
                record,
                evidence_ids=request.evidence_ids,
                knowledge_point_ids=request.knowledge_point_ids,
            )
            overlay = self.overlay_publisher.publish(
                knowledge_base.id,
                expected_active_id=knowledge_base.active_verified_index_version_id,
            )
            record.current_overlay_version_id = overlay.id
            self.repository.session.commit()
        except Exception:
            self.repository.session.rollback()
            raise
        return self._write_result(request, record, created=True)

    def revoke(
        self,
        request: RevokeVerifiedContentRequest,
        *,
        principal: TrustedPrincipal,
    ) -> RevokeVerifiedContentResult:
        self._authorize(request.context, principal, request.course_id, PrincipalRole.OWNER)
        key = require_idempotency_key(request.context)
        request_hash = _sha256(request.model_dump(mode="json", exclude={"context"}))
        knowledge_base = self.repository.knowledge_base_for_course(request.course_id)
        record = self.repository.get_content(request.verified_content_id)
        if knowledge_base is None or record is None:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.RESOURCE_NOT_FOUND,
                message="Verified content not found.",
            )
        if record.knowledge_base_id != knowledge_base.id:
            raise CourseRAGError(
                context=request.context,
                code=ErrorCode.FORBIDDEN,
                message="Verified content does not belong to the authorized course.",
            )
        if record.revoke_idempotency_key is not None:
            if record.revoke_idempotency_key != key or record.revoke_request_sha256 != request_hash:
                raise CourseRAGError(
                    context=request.context,
                    code=ErrorCode.IDEMPOTENCY_CONFLICT,
                    message="Revoke idempotency key or request does not match the completed revoke.",
                )
            return RevokeVerifiedContentResult(
                meta=ResponseMeta.from_context(request.context),
                verified_content_id=record.id,
                status=VerifiedContentStatus.REVOKED,
                revoked=False,
                overlay_index_version=record.current_overlay_version_id,
            )
        old_active = knowledge_base.active_verified_index_version_id
        record.retrieval_active = False
        try:
            self.repository.flush()
            overlay = self.overlay_publisher.publish(
                knowledge_base.id,
                expected_active_id=old_active,
            )
            record.status = VerifiedContentStatus.REVOKED.value
            record.current_overlay_version_id = overlay.id
            record.revoked_by = request.revoked_by
            record.revoked_reason = request.reason
            record.revoked_at = utc_now()
            record.revoke_idempotency_key = key
            record.revoke_request_sha256 = request_hash
            self.repository.session.commit()
        except Exception:
            self.repository.session.rollback()
            raise
        return RevokeVerifiedContentResult(
            meta=ResponseMeta.from_context(request.context),
            verified_content_id=record.id,
            status=VerifiedContentStatus.REVOKED,
            revoked=True,
            overlay_index_version=overlay.id,
        )

    @staticmethod
    def _authorize(
        context, principal: TrustedPrincipal, course_id: str, role: PrincipalRole
    ) -> None:
        try:
            require_course_role(principal, course_id, role)
        except PermissionError as exc:
            raise CourseRAGError(
                context=context,
                code=ErrorCode.FORBIDDEN,
                message=str(exc),
            ) from exc

    @staticmethod
    def _write_result(
        request: VerifiedContentWriteRequest,
        record: VerifiedContentRecord,
        *,
        created: bool,
    ) -> VerifiedContentWriteResult:
        overlay_id = record.current_overlay_version_id or "overlay_pending"
        return VerifiedContentWriteResult(
            meta=ResponseMeta.from_context(request.context),
            verified_content_id=record.id,
            version=record.version_sha256 or "legacy",
            status=VerifiedContentStatus(record.status),
            index_version=overlay_id,
            overlay_index_version=record.current_overlay_version_id,
            content_sha256=record.content_sha256,
            enrichment_status=VerifiedContentStatus(record.status),
            created=created,
        )


def _content_title(content: dict) -> str:
    for key in ("title", "question", "name"):
        value = content.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:500]
    return "Teacher verified content"


def _sha256(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 2) // 3)
