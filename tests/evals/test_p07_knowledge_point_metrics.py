from __future__ import annotations

from courserag.domain.knowledge_point import (
    KnowledgePointDraft,
    KnowledgePointEvidenceRef,
    PublishScore,
    PublishScoreComponents,
)
from courserag.evals.knowledge_point_metrics import (
    knowledge_point_metric_report,
    match_knowledge_points,
    threshold_report,
)
from courserag.evals.schemas import KnowledgePointRecord


def _gold(identifier: str, name: str, aliases: list[str] | None = None):
    return KnowledgePointRecord(
        record_id=identifier,
        gold_kp_id=identifier,
        course_id="course-1",
        canonical_name=name,
        aliases=aliases or [],
        summary="source grounded summary",
        section_ids=["section-1"],
        evidence_ids=["gold-ev-1"],
        roles=["definition"],
        importance="core",
        granularity="atomic",
        candidate_source="human",
    )


def _draft(identifier: str, name: str, aliases: tuple[str, ...] = ()):
    return KnowledgePointDraft(
        knowledge_base_id="kb-1",
        course_id="course-1",
        stable_key=identifier,
        canonical_name=name,
        normalized_name=name.casefold(),
        aliases=aliases,
        summary="summary",
        section_ids=("section-1",),
        window_ids=("window-1",),
        evidence_refs=(
            KnowledgePointEvidenceRef(
                evidence_id=f"ev1_{1:064x}", role="definition", is_primary=True
            ),
        ),
    )


def test_exact_and_alias_matching_is_one_to_one_and_reports_evidence() -> None:
    gold = [_gold("gold-1", "Artificial intelligence", ["AI"])]
    system = [_draft("system-1", "AI", ("Artificial intelligence",))]

    matches, ambiguous = match_knowledge_points(gold, system)
    report = knowledge_point_metric_report(
        gold,
        system,
        matches,
        evidence_adapter={f"ev1_{1:064x}": "gold-ev-1"},
    )

    assert not ambiguous
    assert matches[0].basis == "system_canonical_to_gold_alias"
    assert report["f1"] == 1.0
    assert report["evidence_link_recall"] == 1.0


def test_name_collision_is_emitted_for_human_review() -> None:
    gold = [_gold("gold-1", "AI"), _gold("gold-2", "Artificial intelligence", ["AI"])]
    matches, ambiguous = match_knowledge_points(gold, [_draft("system-1", "AI")])

    assert not matches
    assert ambiguous[0].candidate_gold_ids == ("gold-1", "gold-2")


def test_threshold_report_uses_only_deterministic_score() -> None:
    gold = [_gold("gold-1", "AI")]
    system = [_draft("system-1", "AI"), _draft("system-2", "ML")]
    matches, _ = match_knowledge_points(gold, system)
    components = PublishScoreComponents(
        evidence=1,
        naming=1,
        cross_window=1,
        ambiguity_safety=1,
        duplicate_safety=1,
    )
    scores = {
        "system-1": PublishScore(
            total=0.8,
            components=components,
            profile_sha256="a" * 64,
            threshold=0.75,
            deterministic_checks_passed=True,
            status="unreviewed",
        ),
        "system-2": PublishScore(
            total=0.7,
            components=components,
            profile_sha256="a" * 64,
            threshold=0.75,
            deterministic_checks_passed=True,
            status="needs_review",
        ),
    }

    rows = threshold_report(gold, system, matches, scores, (0.65, 0.75, 0.85))

    assert rows[0]["published_count"] == 2
    assert rows[1]["f1"] == 1.0
    assert rows[2]["published_count"] == 0
