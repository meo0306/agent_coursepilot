from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum


class EnrichmentTrigger(StrEnum):
    MANUAL = "manual"
    RECORD_COUNT = "record_count"
    TOKEN_COUNT = "token_count"
    AGE = "age"


@dataclass(frozen=True)
class PendingEnrichment:
    content_id: str
    token_count: int
    created_at: datetime


@dataclass(frozen=True)
class EnrichmentBatchPlan:
    trigger: EnrichmentTrigger
    content_ids: tuple[str, ...]
    identity_sha256: str


def plan_enrichment_batch(
    pending: list[PendingEnrichment],
    *,
    now: datetime,
    profile_sha256: str,
    manual: bool = False,
    record_threshold: int = 10,
    token_threshold: int = 3_000,
    max_age: timedelta = timedelta(hours=24),
) -> EnrichmentBatchPlan | None:
    ordered = sorted(pending, key=lambda item: (item.created_at, item.content_id))
    if manual and ordered:
        trigger = EnrichmentTrigger.MANUAL
    elif len(ordered) >= record_threshold:
        trigger = EnrichmentTrigger.RECORD_COUNT
    elif sum(item.token_count for item in ordered) >= token_threshold:
        trigger = EnrichmentTrigger.TOKEN_COUNT
    elif ordered and now - ordered[0].created_at >= max_age:
        trigger = EnrichmentTrigger.AGE
    else:
        return None
    content_ids = tuple(item.content_id for item in ordered)
    identity = hashlib.sha256(
        json.dumps(
            {
                "content_ids": content_ids,
                "profile_sha256": profile_sha256,
                "trigger": trigger.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return EnrichmentBatchPlan(
        trigger=trigger,
        content_ids=content_ids,
        identity_sha256=identity,
    )
