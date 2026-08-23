from coursepilot.domain.context import ContextPackageRef
from coursepilot.integration.context_binding import (
    ContextBindingStatus,
    validate_context_binding,
)


def _reference() -> ContextPackageRef:
    return ContextPackageRef(
        context_id="context-1",
        purpose="lesson_generation",
        course_id="course-1",
        index_version="primary-v1",
        verified_overlay_version="overlay-v1",
        retrieval_snapshot_id="snapshot-1",
        evidence_ids=["evidence-1"],
        evidence_versions={"evidence-1": "a" * 64},
        token_count=10,
        content_hash="b" * 64,
        trace_id="trace-1",
    )


def test_context_binding_detects_every_stale_version_axis() -> None:
    reference = _reference()
    compatible = validate_context_binding(
        reference,
        course_id="course-1",
        primary_index_version="primary-v1",
        verified_overlay_version="overlay-v1",
        evidence_hashes={"evidence-1": "a" * 64},
    )
    assert compatible.status == ContextBindingStatus.COMPATIBLE
    assert not compatible.stale

    primary = validate_context_binding(
        reference,
        course_id="course-1",
        primary_index_version="primary-v2",
        verified_overlay_version="overlay-v1",
        evidence_hashes={"evidence-1": "a" * 64},
    )
    overlay = validate_context_binding(
        reference,
        course_id="course-1",
        primary_index_version="primary-v1",
        verified_overlay_version="overlay-v2",
        evidence_hashes={"evidence-1": "a" * 64},
    )
    changed = validate_context_binding(
        reference,
        course_id="course-1",
        primary_index_version="primary-v1",
        verified_overlay_version="overlay-v1",
        evidence_hashes={"evidence-1": "c" * 64},
    )
    missing = validate_context_binding(
        reference,
        course_id="course-1",
        primary_index_version="primary-v1",
        verified_overlay_version="overlay-v1",
        evidence_hashes={},
    )
    cross_course = validate_context_binding(
        reference,
        course_id="course-2",
        primary_index_version="primary-v1",
        verified_overlay_version="overlay-v1",
        evidence_hashes={"evidence-1": "a" * 64},
    )
    assert primary.status == ContextBindingStatus.STALE_PRIMARY_INDEX
    assert overlay.status == ContextBindingStatus.STALE_VERIFIED_OVERLAY
    assert changed.status == ContextBindingStatus.CHANGED_EVIDENCE
    assert missing.status == ContextBindingStatus.MISSING_EVIDENCE
    assert cross_course.status == ContextBindingStatus.CROSS_COURSE_EVIDENCE
