from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.models import GenerationTask, IdempotencyRecord


class InvalidIdempotencyKeyError(ValueError):
    pass


class IdempotencyConflictError(ValueError):
    pass


class IdempotencyInProgressError(ValueError):
    pass


@dataclass(frozen=True)
class IdempotencyExecutionResult:
    value: Any
    replayed: bool


class IdempotencyService:
    def __init__(self, session: Session):
        self.session = session

    def execute(
        self,
        *,
        operation: str,
        idempotency_key: str | None,
        request_payload: Any,
        fn: Callable[[], Any],
        response_status: int = 200,
        resource_type: str | None = None,
        resource_id_field: str | None = None,
        retry_if_resource_failed: bool = False,
    ) -> IdempotencyExecutionResult:
        if idempotency_key is None:
            return IdempotencyExecutionResult(value=fn(), replayed=False)

        key = self._validate_key(idempotency_key)
        request_hash = self.request_hash(request_payload)
        record, replay = self._acquire(
            operation,
            key,
            request_hash,
            retry_if_resource_failed=retry_if_resource_failed,
        )
        if replay is not None:
            return replay

        try:
            encoded_response = jsonable_encoder(fn())
        except BaseException as exc:
            self._mark_failed(record.id, exc)
            raise

        record = self.session.get(IdempotencyRecord, record.id)
        if record is None:
            raise RuntimeError("Idempotency record disappeared while completing request")
        record.status = "succeeded"
        record.response_status = response_status
        record.response_json = encoded_response
        record.error_message = None
        record.locked_until = utc_now()
        record.resource_type = resource_type
        if resource_id_field and isinstance(encoded_response, dict):
            resource_id = encoded_response.get(resource_id_field)
            record.resource_id = str(resource_id) if resource_id is not None else None
        self.session.commit()
        return IdempotencyExecutionResult(value=encoded_response, replayed=False)

    @staticmethod
    def request_hash(payload: Any) -> str:
        canonical = json.dumps(
            jsonable_encoder(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()

    def _acquire(
        self,
        operation: str,
        key: str,
        request_hash: str,
        *,
        retry_if_resource_failed: bool,
    ) -> tuple[IdempotencyRecord, IdempotencyExecutionResult | None]:
        record = self._find(operation, key)
        if record is not None:
            return self._reuse_or_reclaim(
                record,
                request_hash,
                retry_if_resource_failed=retry_if_resource_failed,
            )

        record = IdempotencyRecord(
            operation=operation,
            idempotency_key=key,
            request_hash=request_hash,
            status="in_progress",
            attempt_count=1,
            locked_until=lease_deadline(),
        )
        self.session.add(record)
        try:
            self.session.commit()
            self.session.refresh(record)
            return record, None
        except IntegrityError:
            self.session.rollback()
            existing = self._find(operation, key)
            if existing is None:
                raise
            return self._reuse_or_reclaim(
                existing,
                request_hash,
                retry_if_resource_failed=retry_if_resource_failed,
            )

    def _reuse_or_reclaim(
        self,
        record: IdempotencyRecord,
        request_hash: str,
        *,
        retry_if_resource_failed: bool,
    ) -> tuple[IdempotencyRecord, IdempotencyExecutionResult | None]:
        if record.request_hash != request_hash:
            raise IdempotencyConflictError(
                "Idempotency-Key was already used with a different request payload"
            )
        if record.status == "succeeded":
            if retry_if_resource_failed and self._resource_failed(record):
                return self._reclaim(record)
            return record, IdempotencyExecutionResult(
                value=record.response_json,
                replayed=True,
            )
        if record.status == "in_progress" and is_future(record.locked_until):
            raise IdempotencyInProgressError(
                "A request with this Idempotency-Key is still in progress"
            )

        return self._reclaim(record)

    def _reclaim(
        self,
        record: IdempotencyRecord,
    ) -> tuple[IdempotencyRecord, None]:
        record.status = "in_progress"
        record.attempt_count += 1
        record.response_status = None
        record.response_json = None
        record.error_message = None
        record.locked_until = lease_deadline()
        self.session.commit()
        self.session.refresh(record)
        return record, None

    def _resource_failed(self, record: IdempotencyRecord) -> bool:
        if record.resource_type != "async_task" or not record.resource_id:
            return False
        task = self.session.get(GenerationTask, record.resource_id)
        return task is None or task.status == "failed"

    def _mark_failed(self, record_id: str, exc: BaseException) -> None:
        self.session.rollback()
        record = self.session.get(IdempotencyRecord, record_id)
        if record is None or record.status == "succeeded":
            return
        record.status = "failed"
        record.error_message = str(exc)
        record.locked_until = utc_now()
        self.session.commit()

    def _find(self, operation: str, key: str) -> IdempotencyRecord | None:
        return self.session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.idempotency_key == key,
            )
        )

    @staticmethod
    def _validate_key(value: str) -> str:
        key = value.strip()
        if not key:
            raise InvalidIdempotencyKeyError("Idempotency-Key cannot be empty")
        if len(key) > 255:
            raise InvalidIdempotencyKeyError("Idempotency-Key cannot exceed 255 characters")
        return key


def utc_now() -> datetime:
    return datetime.now(UTC)


def lease_deadline() -> datetime:
    return utc_now() + timedelta(seconds=settings.COURSEPILOT_IDEMPOTENCY_LEASE_SECONDS)


def is_future(value: datetime) -> bool:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value > utc_now()
