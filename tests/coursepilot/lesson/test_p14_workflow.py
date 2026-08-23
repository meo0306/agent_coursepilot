from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from agents.coursepilot.lesson.generator import LessonGenerator
from agents.coursepilot.lesson.graph import build_lesson_graph
from coursepilot.application.lesson_workflow_service import (
    LessonWorkflowError,
    LessonWorkflowService,
)
from coursepilot.domain.context import ContextPackageRef
from courserag.contracts.common import ResponseMeta
from courserag.contracts.knowledge_points import (
    KnowledgePointEvidenceLink,
    KnowledgePointSnapshot,
    KnowledgePointSnapshotItem,
)


def _inputs() -> dict[str, object]:
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
    return {
        "task_id": "task-1",
        "course_id": "course",
        "request": {"chapter_scope": "Attention", "total_sessions": 1, "session_duration": 45},
        "template_snapshot_id": "lesson_standard_university_v1",
        "knowledge_points": snapshot.model_dump(mode="json"),
        "context_ref": context.model_dump(mode="json"),
    }


def test_lesson_graph_has_two_interrupt_boundaries_and_evidence() -> None:
    graph = build_lesson_graph(checkpointer=MemorySaver())
    config = {"configurable": {"thread_id": "lesson-test"}}
    first = graph.invoke(_inputs(), config=config)
    assert first["__interrupt__"][0].value["interrupt_type"] == "lesson_session_plan_review"
    second = graph.invoke(
        Command(resume={"action": "approve"}),
        config=config,
    )
    assert second["__interrupt__"][0].value["interrupt_type"] == "lesson_final_review"
    assert second["validation_report"]["passed"] is True


def test_fragment_writeback_rejects_whole_lesson_scope() -> None:
    inputs = _inputs()
    snapshot = KnowledgePointSnapshot.model_validate(inputs["knowledge_points"])
    context = ContextPackageRef.model_validate(inputs["context_ref"])
    artifact = LessonGenerator().generate_artifact(
        LessonGenerator().build_blueprint(
            course_id="course",
            chapter_scope="Attention",
            total_sessions=1,
            session_duration=45,
            template_snapshot_id="lesson_standard_university_v1",
            kp_snapshot=snapshot,
            context_ref=context,
        ),
        snapshot,
    )

    class FakePort:
        def write_verified_content(self, request):
            return {"content_id": "verified-1", "request": request}

    service = LessonWorkflowService(FakePort())
    for path in ("$", "$.sessions", "$.sessions[0],$.sessions[1]"):
        try:
            service.write_verified_path(
                artifact=artifact,
                json_path=path,
                evidence_ids=["ev-1"],
                approved_by="owner",
                task_id="task-1",
                approval_record_id="approval-1",
            )
        except LessonWorkflowError as exc:
            assert str(exc) == "WRITEBACK_SCOPE_REQUIRED"
        else:
            raise AssertionError("whole-lesson scope must be rejected")
