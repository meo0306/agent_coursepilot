from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from coursepilot.domain import InterruptType
from coursepilot.runtime.checkpoint import recoverable_config


class RecoverableState(TypedDict, total=False):
    interrupt_payload: dict[str, Any]
    last_decision: Any


def _review_node(interrupt_type: InterruptType, state: RecoverableState) -> dict[str, Any]:
    payload = state.get("interrupt_payload", {})
    decision = interrupt({"interrupt_type": interrupt_type.value, **payload})
    return {"last_decision": decision}


def build_recoverable_graph(
    workflow_type: str,
    *,
    checkpointer: BaseCheckpointSaver,
) -> Any:
    """Build the P12 recovery skeleton around versioned business artifacts.

    P14-P16 will replace the placeholder artifact nodes with the final workflows.
    The interrupt boundaries and resume semantics remain shared.
    """
    graph = StateGraph(RecoverableState)
    if workflow_type == "lesson":
        from agents.coursepilot.lesson.graph import build_lesson_graph

        return build_lesson_graph(checkpointer=checkpointer)
    elif workflow_type == "exam":
        graph.add_node(
            "exam_blueprint_review", lambda s: _review_node(InterruptType.EXAM_BLUEPRINT, s)
        )
        graph.add_node("exam_global_review", lambda s: _review_node(InterruptType.EXAM_GLOBAL, s))
        graph.add_edge(START, "exam_blueprint_review")
        graph.add_edge("exam_blueprint_review", "exam_global_review")
        graph.add_edge("exam_global_review", END)
    elif workflow_type == "ppt":
        graph.add_node(
            "ppt_architecture_review", lambda s: _review_node(InterruptType.PPT_ARCHITECTURE, s)
        )
        graph.add_node("ppt_final_review", lambda s: _review_node(InterruptType.PPT_FINAL, s))
        graph.add_edge(START, "ppt_architecture_review")
        graph.add_edge("ppt_architecture_review", "ppt_final_review")
        graph.add_edge("ppt_final_review", END)
    else:
        raise ValueError(f"Unsupported workflow type: {workflow_type}")
    return graph.compile(checkpointer=checkpointer)


def recoverable_graph_config(workflow_type: str, task_id: str, course_id: str) -> Any:
    return recoverable_config(workflow_type=workflow_type, task_id=task_id, course_id=course_id)
