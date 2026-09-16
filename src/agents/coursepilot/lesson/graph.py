from __future__ import annotations

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from agents.coursepilot.lesson.generator import LessonGenerator
from agents.coursepilot.lesson.state import LessonWorkflowState
from agents.coursepilot.lesson.validation import LessonP14Validator
from coursepilot.domain.context import ContextPackageRef
from coursepilot.domain.interrupts import InterruptType
from courserag.contracts.knowledge_points import KnowledgePointSnapshot


def _prepare(state: LessonWorkflowState) -> dict[str, Any]:
    if "knowledge_points" not in state or "context_ref" not in state:
        return {"legacy": True}
    request = state["request"]
    snapshot = KnowledgePointSnapshot.model_validate(state["knowledge_points"])
    context = ContextPackageRef.model_validate(state["context_ref"])
    generator = LessonGenerator()
    blueprint = generator.build_blueprint(
        course_id=state["course_id"],
        chapter_scope=str(request.get("chapter_scope", request.get("chapter_range", "course"))),
        total_sessions=int(str(request.get("total_sessions", 1))),
        session_duration=int(str(request.get("session_duration", 45))),
        template_snapshot_id=state["template_snapshot_id"],
        kp_snapshot=snapshot,
        context_ref=context,
    )
    return {"blueprint": blueprint.model_dump(mode="json")}


def _session_review(state: LessonWorkflowState) -> dict[str, Any]:
    if state.get("legacy"):
        decision = interrupt({"interrupt_type": InterruptType.LESSON_SESSION_PLAN.value})
        return {"decision": decision}
    decision = interrupt(
        {
            "interrupt_type": InterruptType.LESSON_SESSION_PLAN.value,
            "task_id": state["task_id"],
            "blueprint": state["blueprint"],
            "allowed_actions": ["approve", "edit_resume", "replan", "reject", "cancel"],
        }
    )
    return {"decision": decision}


def _generate(state: LessonWorkflowState) -> dict[str, Any]:
    if state.get("legacy"):
        return {}
    snapshot = KnowledgePointSnapshot.model_validate(state["knowledge_points"])
    blueprint = state["blueprint"]
    from coursepilot.domain.lesson import LessonBlueprint

    artifact = LessonGenerator().generate_artifact(
        LessonBlueprint.model_validate(blueprint), snapshot
    )
    report = LessonP14Validator().validate(artifact)
    return {
        "sessions": [session.model_dump(mode="json") for session in artifact.sessions],
        "artifact": artifact.model_dump(mode="json"),
        "validation_report": report.model_dump(mode="json"),
    }


def _final_review(state: LessonWorkflowState) -> dict[str, Any]:
    if state.get("legacy"):
        decision = interrupt({"interrupt_type": InterruptType.LESSON_FINAL.value})
        return {"decision": decision}
    decision = interrupt(
        {
            "interrupt_type": InterruptType.LESSON_FINAL.value,
            "task_id": state["task_id"],
            "artifact": state.get("artifact"),
            "validation_report": state.get("validation_report"),
            "allowed_actions": ["approve", "edit_resume", "replan", "reject", "cancel"],
        }
    )
    return {"decision": decision}


def build_lesson_graph(*, checkpointer: BaseCheckpointSaver) -> Any:
    graph = StateGraph(LessonWorkflowState)
    graph.add_node("prepare", _prepare)
    graph.add_node("lesson_session_plan_review", _session_review)
    graph.add_node("generate_sessions", _generate)
    graph.add_node("lesson_final_review", _final_review)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "lesson_session_plan_review")
    graph.add_edge("lesson_session_plan_review", "generate_sessions")
    graph.add_edge("generate_sessions", "lesson_final_review")
    graph.add_edge("lesson_final_review", END)
    return graph.compile(checkpointer=checkpointer)
