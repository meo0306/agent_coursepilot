from datetime import UTC, datetime, timedelta

from courserag.jobs.enrichment import EnrichmentTrigger, PendingEnrichment, plan_enrichment_batch


def _item(index: int, *, tokens: int = 100, age_hours: int = 1) -> PendingEnrichment:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    return PendingEnrichment(
        content_id=f"content-{index:02d}",
        token_count=tokens,
        created_at=now - timedelta(hours=age_hours),
    )


def test_trigger_precedence_and_identity_are_deterministic() -> None:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    items = [_item(index, tokens=400, age_hours=30) for index in range(10)]
    first = plan_enrichment_batch(items, now=now, profile_sha256="a" * 64)
    second = plan_enrichment_batch(list(reversed(items)), now=now, profile_sha256="a" * 64)
    assert first is not None and first.trigger == EnrichmentTrigger.RECORD_COUNT
    assert second == first
    manual = plan_enrichment_batch(items, now=now, profile_sha256="a" * 64, manual=True)
    assert manual is not None and manual.trigger == EnrichmentTrigger.MANUAL


def test_token_age_and_no_trigger_boundaries() -> None:
    now = datetime(2026, 8, 10, tzinfo=UTC)
    token = plan_enrichment_batch(
        [_item(index, tokens=1000) for index in range(3)],
        now=now,
        profile_sha256="b" * 64,
    )
    age = plan_enrichment_batch([_item(1, age_hours=24)], now=now, profile_sha256="b" * 64)
    none = plan_enrichment_batch([_item(1, age_hours=23)], now=now, profile_sha256="b" * 64)
    assert token is not None and token.trigger == EnrichmentTrigger.TOKEN_COUNT
    assert age is not None and age.trigger == EnrichmentTrigger.AGE
    assert none is None
