from __future__ import annotations

from agents.coursepilot.lesson.generator import LessonGenerator
from coursepilot.domain.context import ContextPackageRef
from courserag.contracts.common import ResponseMeta
from courserag.contracts.knowledge_points import (
    KnowledgePointEvidenceLink,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotItem,
)


def test_model_generator_uses_planner_and_session_profiles(monkeypatch) -> None:
    snapshot = KnowledgePointSnapshot(
        meta=ResponseMeta(request_id="r", trace_id="t"),
        course_id="course",
        items=[
            KnowledgePointSnapshotItem(
                knowledge_point_id="kp-1",
                course_id="course",
                canonical_name="Transformer",
                summary="An encoder-decoder architecture.",
                evidence_links=[KnowledgePointEvidenceLink(evidence_id="ev-1")],
            )
        ],
        snapshot_sha256="0" * 64,
    )
    context = ContextPackageRef(
        context_id="ctx-1",
        purpose="lesson_generation",
        course_id="course",
        index_version="index-1",
        evidence_ids=["ev-1"],
        token_count=10,
        content_hash="1" * 64,
        trace_id="trace-1",
    )
    profiles: list[tuple[str, bool | None]] = []

    def fake_generate_structured(*, fallback, profile_id, allow_fallback, **kwargs):
        profiles.append((profile_id, allow_fallback))
        return fallback()

    monkeypatch.setattr(
        "agents.coursepilot.lesson.generator.generate_structured", fake_generate_structured
    )
    generator = LessonGenerator(use_model=True)
    blueprint = generator.build_blueprint(
        course_id="course",
        chapter_scope="Attention",
        total_sessions=1,
        session_duration=45,
        template_snapshot_id="lesson_standard_university_v1",
        kp_snapshot=snapshot,
        context_ref=context,
        context_records=[{"evidence_id": "ev-1", "text": "source"}],
    )
    artifact = generator.generate_artifact(
        blueprint,
        snapshot,
        context_records=[{"evidence_id": "ev-1", "text": "source"}],
    )
    assert len(artifact.sessions) == 1
    assert profiles == [("planner_main", False), ("generator_main", False)]


def test_model_generator_replan_includes_previous_blueprint(monkeypatch) -> None:
    snapshot = KnowledgePointSnapshot(
        meta=ResponseMeta(request_id="r", trace_id="t"),
        course_id="course",
        items=[
            KnowledgePointSnapshotItem(
                knowledge_point_id="kp-1",
                course_id="course",
                canonical_name="Transformer",
                evidence_links=[KnowledgePointEvidenceLink(evidence_id="ev-1")],
            )
        ],
        snapshot_sha256="0" * 64,
    )
    context = ContextPackageRef(
        context_id="ctx-1",
        purpose="lesson_generation",
        course_id="course",
        index_version="index-1",
        evidence_ids=["ev-1"],
        token_count=10,
        content_hash="1" * 64,
        trace_id="trace-1",
    )
    payloads = []

    def fake_generate_structured(*, payload, fallback, **_kwargs):
        payloads.append(payload)
        return fallback()

    monkeypatch.setattr(
        "agents.coursepilot.lesson.generator.generate_structured", fake_generate_structured
    )
    generator = LessonGenerator(use_model=True)
    initial = generator.build_blueprint(
        course_id="course",
        chapter_scope="Attention",
        total_sessions=1,
        session_duration=45,
        template_snapshot_id="lesson_standard_university_v1",
        kp_snapshot=snapshot,
        context_ref=context,
    )
    generator.build_blueprint(
        course_id="course",
        chapter_scope="Attention",
        total_sessions=1,
        session_duration=45,
        template_snapshot_id="lesson_standard_university_v1",
        kp_snapshot=snapshot,
        context_ref=context,
        replan_instruction="Move practice earlier.",
        previous_blueprint=initial,
    )

    assert "previous_blueprint" not in payloads[0]
    assert payloads[1]["previous_blueprint"]["course_id"] == "course"
    assert payloads[1]["replan_instruction"] == "Move practice earlier."
