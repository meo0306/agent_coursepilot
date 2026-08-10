"""Application service for reviewable CourseRAG Knowledge Point assets."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from courserag.domain.document import stable_ir_id
from courserag.domain.knowledge_point import (
    KnowledgePointStatus,
    normalized_knowledge_point_name,
    stable_knowledge_point_key,
)
from courserag.knowledge_points.materialize import rebuild_knowledge_point_chunk_links
from courserag.persistence.base import utc_now
from courserag.persistence.models import (
    KnowledgePointAliasRecord,
    KnowledgePointEvidenceRecord,
    KnowledgePointRecord,
    KnowledgePointReviewRecord,
)
from courserag.persistence.repositories import CourseRAGRepository


class KnowledgePointApplicationError(RuntimeError):
    pass


class KnowledgePointNotFound(KnowledgePointApplicationError):
    pass


class KnowledgePointVersionConflict(KnowledgePointApplicationError):
    pass


class KnowledgePointIdempotencyConflict(KnowledgePointApplicationError):
    pass


class KnowledgePointValidationError(KnowledgePointApplicationError):
    pass


class ApplicationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class KnowledgePointEvidenceView(ApplicationModel):
    evidence_id: str
    role: str
    strength: float
    is_primary: bool
    review_status: str


class KnowledgePointChunkView(ApplicationModel):
    chunk_id: str
    role: str
    strength: float
    use_for_filtering: bool
    use_for_ranking: bool


class KnowledgePointReviewView(ApplicationModel):
    reviewer_id: str
    action: str
    comment: str | None
    resulting_version_number: int | None
    created_at: datetime


class KnowledgePointView(ApplicationModel):
    knowledge_point_id: str
    knowledge_base_id: str
    canonical_name: str
    normalized_name: str | None
    aliases: tuple[str, ...]
    summary: str | None
    parent_knowledge_point_id: str | None
    publish_score: float | None
    publish_score_components: dict[str, float]
    auto_published: bool
    origin: str
    review_status: KnowledgePointStatus
    version_number: int
    section_ids: tuple[str, ...]
    evidence_links: tuple[KnowledgePointEvidenceView, ...]
    chunk_links: tuple[KnowledgePointChunkView, ...]
    reviews: tuple[KnowledgePointReviewView, ...]
    created_at: datetime
    updated_at: datetime


class KnowledgePointUpdate(ApplicationModel):
    canonical_name: str | None = Field(default=None, min_length=1, max_length=240)
    aliases: tuple[str, ...] | None = None
    summary: str | None = Field(default=None, min_length=1, max_length=4000)
    parent_knowledge_point_id: str | None = Field(default=None, max_length=36)
    clear_parent: bool = False
    comment: str | None = Field(default=None, max_length=4000)


class MergeKnowledgePoints(ApplicationModel):
    source_ids: tuple[str, ...] = Field(min_length=1)
    source_versions: dict[str, int]
    comment: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_sources(self) -> MergeKnowledgePoints:
        if len(self.source_ids) != len(set(self.source_ids)):
            raise ValueError("Merge source IDs must be unique")
        if set(self.source_versions) != set(self.source_ids):
            raise ValueError("Merge source versions must cover every source")
        return self


class SplitKnowledgePointChild(ApplicationModel):
    canonical_name: str = Field(min_length=1, max_length=240)
    aliases: tuple[str, ...] = ()
    summary: str = Field(min_length=1, max_length=4000)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class SplitKnowledgePoint(ApplicationModel):
    children: tuple[SplitKnowledgePointChild, ...] = Field(min_length=2)
    comment: str | None = Field(default=None, max_length=4000)


class KnowledgePointService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.repository = CourseRAGRepository(session)

    def list(
        self,
        knowledge_base_id: str,
        *,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[KnowledgePointView, ...]:
        if self.repository.get_knowledge_base(knowledge_base_id) is None:
            raise KnowledgePointNotFound("Knowledge Base not found")
        return tuple(
            self._view(record)
            for record in self.repository.list_knowledge_points(
                knowledge_base_id, status=status, limit=limit, offset=offset
            )
        )

    def get(self, knowledge_point_id: str) -> KnowledgePointView:
        return self._view(self._record(knowledge_point_id))

    def modify(
        self,
        knowledge_point_id: str,
        payload: KnowledgePointUpdate,
        *,
        expected_version: int,
        idempotency_key: str,
        reviewer_id: str,
    ) -> KnowledgePointView:
        request = self._request_payload(knowledge_point_id, expected_version, payload)
        replay = self._replay_one("modify", idempotency_key, request)
        if replay is not None:
            return replay
        record = self._record(knowledge_point_id)
        self._check_version(record, expected_version)
        if record.status == "deprecated":
            raise KnowledgePointValidationError("Deprecated Knowledge Point cannot be modified")
        before = self._view(record).model_dump(mode="json")
        if payload.canonical_name is not None:
            record.title = payload.canonical_name.strip()
            record.normalized_name = normalized_knowledge_point_name(record.title)
        if payload.summary is not None:
            record.description = payload.summary.strip()
        if payload.clear_parent:
            record.parent_knowledge_point_id = None
        elif payload.parent_knowledge_point_id is not None:
            self._validate_parent(record, payload.parent_knowledge_point_id)
            record.parent_knowledge_point_id = payload.parent_knowledge_point_id
        if payload.aliases is not None:
            self._replace_aliases(record, payload.aliases, basis="human")
        record.version_number += 1
        record.updated_at = utc_now()
        self.repository.flush()
        after = self._view(record)
        self._review(
            record,
            action="modify",
            idempotency_key=idempotency_key,
            request=request,
            reviewer_id=reviewer_id,
            comment=payload.comment,
            before=before,
            after=after.model_dump(mode="json"),
        )
        self.session.commit()
        return after

    def transition(
        self,
        knowledge_point_id: str,
        *,
        action: Literal["approve", "reject", "deprecate"],
        expected_version: int,
        idempotency_key: str,
        reviewer_id: str,
        comment: str | None = None,
    ) -> KnowledgePointView:
        request = {
            "knowledge_point_id": knowledge_point_id,
            "expected_version": expected_version,
            "comment": comment,
        }
        replay = self._replay_one(action, idempotency_key, request)
        if replay is not None:
            return replay
        record = self._record(knowledge_point_id)
        self._check_version(record, expected_version)
        target = {"approve": "approved", "reject": "rejected", "deprecate": "deprecated"}[action]
        before = self._view(record).model_dump(mode="json")
        record.status = target
        record.auto_published = False
        record.version_number += 1
        record.updated_at = utc_now()
        self.repository.flush()
        rebuild_knowledge_point_chunk_links(self.repository, record)
        after = self._view(record)
        self._review(
            record,
            action=action,
            idempotency_key=idempotency_key,
            request=request,
            reviewer_id=reviewer_id,
            comment=comment,
            before=before,
            after=after.model_dump(mode="json"),
        )
        self.session.commit()
        return after

    def merge(
        self,
        target_id: str,
        payload: MergeKnowledgePoints,
        *,
        expected_version: int,
        idempotency_key: str,
        reviewer_id: str,
    ) -> KnowledgePointView:
        request = self._request_payload(target_id, expected_version, payload)
        replay = self._replay_one("merge", idempotency_key, request)
        if replay is not None:
            return replay
        target = self._record(target_id)
        self._check_version(target, expected_version)
        if target_id in payload.source_ids:
            raise KnowledgePointValidationError("Merge target cannot also be a source")
        sources = [self._record(source_id) for source_id in payload.source_ids]
        for source in sources:
            if source.knowledge_base_id != target.knowledge_base_id:
                raise KnowledgePointValidationError("Cannot merge across Knowledge Bases")
            self._check_version(source, payload.source_versions[source.id])
        before = self._view(target).model_dump(mode="json")
        for source in sources:
            for alias in (
                source.title,
                *(item.alias for item in self.repository.list_knowledge_point_aliases(source.id)),
            ):
                self._add_alias(target, alias, basis="human_merge")
            for link in self.repository.list_knowledge_point_evidence(source.id):
                existing = self.repository.get_knowledge_point_evidence_link(
                    target.id, link.evidence_id
                )
                if existing is None:
                    self.repository.add(
                        KnowledgePointEvidenceRecord(
                            knowledge_point_id=target.id,
                            evidence_id=link.evidence_id,
                            role=link.role,
                            strength=link.strength,
                            is_primary=link.is_primary,
                            extraction_batch_id=link.extraction_batch_id,
                            review_status="approved",
                            created_at=utc_now(),
                        )
                    )
            source.status = "deprecated"
            source.auto_published = False
            source.version_number += 1
            source.updated_at = utc_now()
        target.status = "approved"
        target.auto_published = False
        target.version_number += 1
        target.updated_at = utc_now()
        self.repository.flush()
        rebuild_knowledge_point_chunk_links(self.repository, target)
        after = self._view(target)
        self._review(
            target,
            action="merge",
            idempotency_key=idempotency_key,
            request=request,
            reviewer_id=reviewer_id,
            comment=payload.comment,
            before=before,
            after=after.model_dump(mode="json"),
            related_ids=list(payload.source_ids),
        )
        self.session.commit()
        return after

    def split(
        self,
        source_id: str,
        payload: SplitKnowledgePoint,
        *,
        expected_version: int,
        idempotency_key: str,
        reviewer_id: str,
    ) -> tuple[KnowledgePointView, ...]:
        request = self._request_payload(source_id, expected_version, payload)
        existing = self.repository.get_kp_review_by_idempotency("split", idempotency_key)
        digest = self._hash(request)
        if existing is not None:
            if existing.request_sha256 != digest:
                raise KnowledgePointIdempotencyConflict("Idempotency-Key request mismatch")
            return tuple(
                KnowledgePointView.model_validate(item)
                for item in existing.response_json.get("items", [])
            )
        source = self._record(source_id)
        self._check_version(source, expected_version)
        source_links = self.repository.list_knowledge_point_evidence(source.id)
        stable_to_link = {}
        for link in source_links:
            evidence = self.repository.get_evidence(link.evidence_id)
            if evidence is not None:
                stable_to_link[evidence.stable_key] = link
        assigned = [item for child in payload.children for item in child.evidence_ids]
        if len(assigned) != len(set(assigned)) or set(assigned) != set(stable_to_link):
            raise KnowledgePointValidationError(
                "Split Evidence assignments must be disjoint and cover the source"
            )
        knowledge_base = self.repository.get_knowledge_base(source.knowledge_base_id)
        if knowledge_base is None:
            raise KnowledgePointNotFound("Knowledge Base not found")
        before = self._view(source).model_dump(mode="json")
        children: list[KnowledgePointRecord] = []
        for child in payload.children:
            normalized = normalized_knowledge_point_name(child.canonical_name)
            stable_key = stable_knowledge_point_key(
                knowledge_base.course_id, normalized, tuple(sorted(child.evidence_ids))
            )
            if self.repository.get_knowledge_point_by_key(source.knowledge_base_id, stable_key):
                raise KnowledgePointValidationError("Split child already exists")
            record = KnowledgePointRecord(
                id=stable_ir_id("kp", stable_key),
                knowledge_base_id=source.knowledge_base_id,
                stable_key=stable_key,
                title=child.canonical_name.strip(),
                normalized_name=normalized,
                description=child.summary.strip(),
                publish_score=source.publish_score,
                publish_score_components_json=dict(source.publish_score_components_json),
                auto_published=False,
                origin="human_split",
                version_number=1,
                status="approved",
                metadata_json={"split_from": source.id},
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            self.repository.add(record)
            self.repository.flush()
            self._replace_aliases(record, child.aliases, basis="human_split")
            for evidence_id in child.evidence_ids:
                original = stable_to_link[evidence_id]
                self.repository.add(
                    KnowledgePointEvidenceRecord(
                        knowledge_point_id=record.id,
                        evidence_id=original.evidence_id,
                        role=original.role,
                        strength=original.strength,
                        is_primary=original.is_primary,
                        extraction_batch_id=original.extraction_batch_id,
                        review_status="approved",
                        created_at=utc_now(),
                    )
                )
            self.repository.flush()
            rebuild_knowledge_point_chunk_links(self.repository, record)
            children.append(record)
        source.status = "deprecated"
        source.auto_published = False
        source.version_number += 1
        source.updated_at = utc_now()
        self.repository.flush()
        views = tuple(self._view(item) for item in children)
        self._review(
            source,
            action="split",
            idempotency_key=idempotency_key,
            request=request,
            reviewer_id=reviewer_id,
            comment=payload.comment,
            before=before,
            after={"source_status": source.status},
            related_ids=[item.id for item in children],
            response={"items": [item.model_dump(mode="json") for item in views]},
        )
        self.session.commit()
        return views

    def _record(self, knowledge_point_id: str) -> KnowledgePointRecord:
        record = self.repository.get_knowledge_point(knowledge_point_id)
        if record is None:
            raise KnowledgePointNotFound("Knowledge Point not found")
        return record

    @staticmethod
    def _check_version(record: KnowledgePointRecord, expected_version: int) -> None:
        if record.version_number != expected_version:
            raise KnowledgePointVersionConflict("Knowledge Point version changed")

    def _validate_parent(self, record: KnowledgePointRecord, parent_id: str) -> None:
        if parent_id == record.id:
            raise KnowledgePointValidationError("Knowledge Point cannot parent itself")
        parent = self._record(parent_id)
        if parent.knowledge_base_id != record.knowledge_base_id:
            raise KnowledgePointValidationError("Parent must belong to the same Knowledge Base")
        seen = {record.id}
        cursor: KnowledgePointRecord | None = parent
        while cursor is not None:
            if cursor.id in seen:
                raise KnowledgePointValidationError("Knowledge Point Parent cycle detected")
            seen.add(cursor.id)
            cursor = (
                self.repository.get_knowledge_point(cursor.parent_knowledge_point_id)
                if cursor.parent_knowledge_point_id
                else None
            )

    def _replace_aliases(
        self, record: KnowledgePointRecord, aliases: tuple[str, ...], *, basis: str
    ) -> None:
        normalized = [normalized_knowledge_point_name(alias) for alias in aliases]
        if len(normalized) != len(set(normalized)):
            raise KnowledgePointValidationError("Knowledge Point Aliases must be unique")
        if normalized_knowledge_point_name(record.title) in normalized:
            raise KnowledgePointValidationError("Canonical name cannot repeat as an Alias")
        self.repository.delete_knowledge_point_aliases(record.id)
        self.repository.flush()
        for alias in aliases:
            self._add_alias(record, alias, basis=basis)

    def _add_alias(self, record: KnowledgePointRecord, alias: str, *, basis: str) -> None:
        text = alias.strip()
        normalized = normalized_knowledge_point_name(text)
        if not text or normalized == normalized_knowledge_point_name(record.title):
            return
        if self.repository.get_knowledge_point_alias(record.id, normalized) is None:
            self.repository.add(
                KnowledgePointAliasRecord(
                    id=stable_ir_id("kpa", record.id, normalized),
                    knowledge_point_id=record.id,
                    alias=text,
                    normalized_alias=normalized,
                    basis=basis,
                    created_at=utc_now(),
                )
            )

    def _view(self, record: KnowledgePointRecord) -> KnowledgePointView:
        evidence_views = []
        for evidence_link in self.repository.list_knowledge_point_evidence(record.id):
            evidence = self.repository.get_evidence(evidence_link.evidence_id)
            if evidence is None:
                raise KnowledgePointValidationError("Knowledge Point Evidence disappeared")
            evidence_views.append(
                KnowledgePointEvidenceView(
                    evidence_id=evidence.stable_key,
                    role=evidence_link.role,
                    strength=evidence_link.strength,
                    is_primary=evidence_link.is_primary,
                    review_status=evidence_link.review_status,
                )
            )
        chunk_views = []
        for chunk_link in self.repository.list_knowledge_point_chunks(record.id):
            chunk = self.repository.get_chunk(chunk_link.chunk_id)
            if chunk is None:
                raise KnowledgePointValidationError("Knowledge Point Chunk disappeared")
            chunk_views.append(
                KnowledgePointChunkView(
                    chunk_id=chunk.chunk_key,
                    role=chunk_link.role,
                    strength=chunk_link.strength,
                    use_for_filtering=chunk_link.use_for_filtering,
                    use_for_ranking=chunk_link.use_for_ranking,
                )
            )
        metadata = record.metadata_json or {}
        raw_components = record.publish_score_components_json or {}
        return KnowledgePointView(
            knowledge_point_id=record.id,
            knowledge_base_id=record.knowledge_base_id,
            canonical_name=record.title,
            normalized_name=record.normalized_name,
            aliases=tuple(
                item.alias for item in self.repository.list_knowledge_point_aliases(record.id)
            ),
            summary=record.description,
            parent_knowledge_point_id=record.parent_knowledge_point_id,
            publish_score=record.publish_score,
            publish_score_components={
                str(key): float(value)
                for key, value in raw_components.items()
                if isinstance(value, (int, float))
            },
            auto_published=record.auto_published,
            origin=record.origin,
            review_status=record.status,
            version_number=record.version_number,
            section_ids=tuple(str(item) for item in metadata.get("section_ids", [])),
            evidence_links=tuple(evidence_views),
            chunk_links=tuple(chunk_views),
            reviews=tuple(
                KnowledgePointReviewView(
                    reviewer_id=item.reviewer_id,
                    action=item.action,
                    comment=item.comment,
                    resulting_version_number=item.resulting_version_number,
                    created_at=item.created_at,
                )
                for item in self.repository.list_knowledge_point_reviews(record.id)
            ),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _replay_one(
        self, action: str, idempotency_key: str, request: dict[str, object]
    ) -> KnowledgePointView | None:
        existing = self.repository.get_kp_review_by_idempotency(action, idempotency_key)
        if existing is None:
            return None
        if existing.request_sha256 != self._hash(request):
            raise KnowledgePointIdempotencyConflict("Idempotency-Key request mismatch")
        return KnowledgePointView.model_validate(existing.response_json)

    def _review(
        self,
        record: KnowledgePointRecord,
        *,
        action: str,
        idempotency_key: str,
        request: dict[str, object],
        reviewer_id: str,
        comment: str | None,
        before: dict[str, object],
        after: dict[str, object],
        related_ids: Sequence[str] | None = None,
        response: dict[str, object] | None = None,
    ) -> None:
        self.repository.add(
            KnowledgePointReviewRecord(
                knowledge_point_id=record.id,
                reviewer_id=reviewer_id,
                action=action,
                idempotency_key=idempotency_key,
                request_sha256=self._hash(request),
                comment=comment,
                before_json=before,
                after_json=after,
                related_knowledge_point_ids_json=list(related_ids or ()),
                response_json=response or after,
                resulting_version_number=record.version_number,
                created_at=utc_now(),
            )
        )

    @staticmethod
    def _request_payload(
        knowledge_point_id: str, expected_version: int, payload: ApplicationModel
    ) -> dict[str, object]:
        return {
            "knowledge_point_id": knowledge_point_id,
            "expected_version": expected_version,
            "payload": payload.model_dump(mode="json"),
        }

    @staticmethod
    def _hash(value: dict[str, object]) -> str:
        encoded = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
