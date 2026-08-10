from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from courserag.application.knowledge_point_service import (
    KnowledgePointIdempotencyConflict,
    KnowledgePointService,
    KnowledgePointUpdate,
    KnowledgePointValidationError,
    KnowledgePointVersionConflict,
    MergeKnowledgePoints,
    SplitKnowledgePoint,
    SplitKnowledgePointChild,
)
from courserag.domain.knowledge_point import sha256_text
from courserag.persistence.models import (
    EvidenceBlockLinkRecord,
    EvidenceRecord,
    KnowledgePointEvidenceRecord,
    KnowledgePointRecord,
)
from tests.courserag.knowledge_points.test_persistence import _facts


def _knowledge_point(session: Session, *, identifier: str, title: str) -> KnowledgePointRecord:
    record = KnowledgePointRecord(
        id=identifier,
        knowledge_base_id="kb-1",
        stable_key=f"stable-{identifier}",
        title=title,
        normalized_name=title.casefold(),
        description=f"{title} summary",
        publish_score=0.8,
        publish_score_components_json={"evidence": 1.0},
        status="needs_review",
    )
    session.add(record)
    session.add(
        KnowledgePointEvidenceRecord(
            knowledge_point_id=identifier,
            evidence_id="evidence-db-1",
            role="definition",
            strength=1.0,
            is_primary=True,
            review_status="unreviewed",
        )
    )
    session.flush()
    return record


def test_modify_and_approve_are_versioned_and_idempotent(p03_session: Session) -> None:
    _facts(p03_session)
    _knowledge_point(p03_session, identifier="kp-1", title="人工智能")
    service = KnowledgePointService(p03_session)

    modified = service.modify(
        "kp-1",
        KnowledgePointUpdate(aliases=("AI",), summary="人工智能的新摘要"),
        expected_version=1,
        idempotency_key="modify-1",
        reviewer_id="teacher-1",
    )
    replay = service.modify(
        "kp-1",
        KnowledgePointUpdate(aliases=("AI",), summary="人工智能的新摘要"),
        expected_version=1,
        idempotency_key="modify-1",
        reviewer_id="teacher-1",
    )

    assert modified == replay
    assert modified.version_number == 2
    assert modified.aliases == ("AI",)
    approved = service.transition(
        "kp-1",
        action="approve",
        expected_version=2,
        idempotency_key="approve-1",
        reviewer_id="teacher-1",
    )
    assert approved.review_status == "approved"
    with pytest.raises(KnowledgePointVersionConflict):
        service.transition(
            "kp-1",
            action="reject",
            expected_version=2,
            idempotency_key="reject-stale",
            reviewer_id="teacher-1",
        )
    with pytest.raises(KnowledgePointIdempotencyConflict):
        service.modify(
            "kp-1",
            KnowledgePointUpdate(summary="different"),
            expected_version=3,
            idempotency_key="modify-1",
            reviewer_id="teacher-1",
        )


def test_merge_is_same_kb_audited_and_deprecates_source(p03_session: Session) -> None:
    _facts(p03_session)
    _knowledge_point(p03_session, identifier="kp-target", title="人工智能")
    _knowledge_point(p03_session, identifier="kp-source", title="AI 系统")
    service = KnowledgePointService(p03_session)

    merged = service.merge(
        "kp-target",
        MergeKnowledgePoints(source_ids=("kp-source",), source_versions={"kp-source": 1}),
        expected_version=1,
        idempotency_key="merge-1",
        reviewer_id="teacher-1",
    )

    assert merged.review_status == "approved"
    assert "AI 系统" in merged.aliases
    assert service.get("kp-source").review_status == "deprecated"


def test_split_requires_disjoint_complete_evidence_assignments(p03_session: Session) -> None:
    _facts(p03_session)
    second_text = "机器学习是人工智能的一个领域。"
    p03_session.add(
        EvidenceRecord(
            id="evidence-db-2",
            parsed_document_id="parsed-1",
            block_id="block-1",
            stable_key=f"ev1_{2:064x}",
            evidence_type="definition",
            text=second_text,
            content_sha256=sha256_text(second_text),
        )
    )
    p03_session.add(
        EvidenceBlockLinkRecord(
            evidence_id="evidence-db-2",
            block_id="block-1",
            ordinal=1,
            char_start=0,
            char_end=len(second_text),
            text_sha256=sha256_text(second_text),
        )
    )
    source = _knowledge_point(p03_session, identifier="kp-source", title="人工智能与机器学习")
    p03_session.add(
        KnowledgePointEvidenceRecord(
            knowledge_point_id=source.id,
            evidence_id="evidence-db-2",
            role="definition",
            strength=1.0,
            is_primary=False,
            review_status="unreviewed",
        )
    )
    p03_session.flush()
    service = KnowledgePointService(p03_session)

    children = service.split(
        source.id,
        SplitKnowledgePoint(
            children=(
                SplitKnowledgePointChild(
                    canonical_name="人工智能",
                    summary="人工智能定义",
                    evidence_ids=(f"ev1_{1:064x}",),
                ),
                SplitKnowledgePointChild(
                    canonical_name="机器学习",
                    summary="机器学习定义",
                    evidence_ids=(f"ev1_{2:064x}",),
                ),
            )
        ),
        expected_version=1,
        idempotency_key="split-1",
        reviewer_id="teacher-1",
    )

    assert len(children) == 2
    assert all(item.review_status == "approved" for item in children)
    assert service.get(source.id).review_status == "deprecated"

    other = _knowledge_point(p03_session, identifier="kp-invalid", title="待拆分")
    with pytest.raises(KnowledgePointValidationError):
        service.split(
            other.id,
            SplitKnowledgePoint(
                children=(
                    SplitKnowledgePointChild(
                        canonical_name="A",
                        summary="A summary",
                        evidence_ids=(f"ev1_{1:064x}",),
                    ),
                    SplitKnowledgePointChild(
                        canonical_name="B",
                        summary="B summary",
                        evidence_ids=(f"ev1_{1:064x}",),
                    ),
                )
            ),
            expected_version=1,
            idempotency_key="split-invalid",
            reviewer_id="teacher-1",
        )
