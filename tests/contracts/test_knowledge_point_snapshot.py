from coursepilot.adapters.mock_courserag import MockCourseRAGService
from courserag.contracts.knowledge_points import (
    KnowledgePointEvidenceLink,
    KnowledgePointSnapshotItem,
    KnowledgePointSnapshotRequest,
)


def test_mock_knowledge_point_snapshot_filters_approved_and_sections() -> None:
    service = MockCourseRAGService()
    service.seed_knowledge_points(
        "course",
        [
            KnowledgePointSnapshotItem(
                knowledge_point_id="kp-1",
                course_id="course",
                canonical_name="Transformer",
                section_ids=["s1"],
                evidence_links=[KnowledgePointEvidenceLink(evidence_id="ev-1")],
            ),
            KnowledgePointSnapshotItem(
                knowledge_point_id="kp-2",
                course_id="course",
                canonical_name="Draft",
                review_status="needs_review",
                section_ids=["s2"],
            ),
        ],
    )
    snapshot = service.list_knowledge_points(
        KnowledgePointSnapshotRequest(course_id="course", section_ids=["s1"])
    )
    assert [item.knowledge_point_id for item in snapshot.items] == ["kp-1"]
    assert len(snapshot.snapshot_sha256) == 64
