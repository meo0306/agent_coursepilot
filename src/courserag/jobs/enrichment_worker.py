"""Idempotent, provider-independent enrichment executor.

The worker deliberately records a completed deterministic enrichment when no
KP provider is configured. It never invents a KnowledgePoint; future semantic
links remain review candidates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from courserag.persistence.writeback_repository import WritebackRepository

if TYPE_CHECKING:
    from courserag.indexing.verified_overlay import VerifiedOverlayPublisher


def run_enrichment_batch(
    repository: WritebackRepository,
    batch_id: str,
    *,
    worker_id: str = "courserag-enrichment-worker",
    lease_seconds: int = 300,
    overlay_publisher: VerifiedOverlayPublisher | None = None,
) -> bool:
    batch = repository.claim_enrichment_batch(batch_id, worker_id, lease_seconds)
    if batch is None:
        return False
    items = repository.enrichment_items(batch_id)
    for item in items:
        if item.status == "completed":
            continue
        item.attempt_count += 1
        item.status = "completed"
        item.result_json = {"provider": "deterministic", "knowledge_point_candidates": []}
        item.knowledge_point_links_json = []
        item.completed_at = datetime.now(UTC)
        content = repository.get_content(item.verified_content_id)
        if content is not None:
            content.status = "enriched"
    if overlay_publisher is not None:
        knowledge_base = repository.lock_knowledge_base(batch.knowledge_base_id)
        if knowledge_base is None:
            repository.session.rollback()
            raise RuntimeError("Enrichment batch Knowledge Base is unavailable")
        overlay = overlay_publisher.publish(
            batch.knowledge_base_id,
            expected_active_id=knowledge_base.active_verified_index_version_id,
        )
        for item in items:
            content = repository.get_content(item.verified_content_id)
            if content is not None:
                content.current_overlay_version_id = overlay.id
    batch.status = "completed"
    batch.completed_at = datetime.now(UTC)
    batch.locked_until = None
    repository.session.commit()
    return True
