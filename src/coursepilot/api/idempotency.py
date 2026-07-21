from collections.abc import Callable
from typing import Any

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session

from coursepilot.services.idempotency_service import (
    IdempotencyConflictError,
    IdempotencyInProgressError,
    IdempotencyService,
    InvalidIdempotencyKeyError,
)


def execute_idempotent(
    *,
    session: Session,
    response: Response,
    operation: str,
    idempotency_key: str | None,
    request_payload: Any,
    fn: Callable[[], Any],
    response_status: int = 200,
    resource_type: str | None = None,
    resource_id_field: str | None = None,
    retry_if_resource_failed: bool = False,
) -> Any:
    try:
        result = IdempotencyService(session).execute(
            operation=operation,
            idempotency_key=idempotency_key,
            request_payload=request_payload,
            fn=fn,
            response_status=response_status,
            resource_type=resource_type,
            resource_id_field=resource_id_field,
            retry_if_resource_failed=retry_if_resource_failed,
        )
    except InvalidIdempotencyKeyError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except IdempotencyInProgressError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
            headers={"Retry-After": "5"},
        ) from exc

    if result.replayed:
        response.headers["Idempotency-Replayed"] = "true"
    return result.value
