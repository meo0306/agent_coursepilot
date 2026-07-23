from typing import Literal

from langgraph.graph import END, StateGraph

from agents.coursepilot.nodes.ppt_nodes import (
    chat_response,
    generate_slide_outline,
    repair_slide_outline,
    validate_slide_outline,
)
from agents.coursepilot.states.ppt_state import PPTGraphState
from core.settings import settings


def route_entry(state: PPTGraphState) -> Literal["chat", "workflow"]:
    """入口函数，根据当前状态决定下一步的节点"""
    # 如果传入 lesson_design，表示需要从教案生成 PPT 大纲
    if "lesson_design" in state:
        return "workflow"
    return "chat"


def should_repair(state: PPTGraphState) -> Literal["repair", "done"]:
    report = state.get("validation_report", {})
    passed = all(
        report.get(key, False)
        for key in [
            "schema_valid",
            "slide_count_valid",
            "slide_type_valid",
            "content_not_empty",
            "source_session_valid",
            "citation_present",
            "citation_grounded",
        ]
    )
    if (
        not passed
        and int(report.get("repair_attempts", 0)) < settings.COURSEPILOT_MAX_REPAIR_ROUNDS
    ):
        return "repair"
    return "done"


graph = StateGraph[
    PPTGraphState,
    None,
    PPTGraphState,
    PPTGraphState,
](PPTGraphState)
graph.add_node("route", lambda state: {})
graph.add_node("chat_response", chat_response)
graph.add_node("generate_slide_outline", generate_slide_outline)
graph.add_node("validate_slide_outline", validate_slide_outline)
graph.add_node("repair_slide_outline", repair_slide_outline)

graph.set_entry_point("route")
graph.add_conditional_edges(
    "route",
    route_entry,
    {
        "chat": "chat_response",
        "workflow": "generate_slide_outline",
    },
)
graph.add_edge("chat_response", END)
graph.add_edge("generate_slide_outline", "validate_slide_outline")
graph.add_conditional_edges(
    "validate_slide_outline",
    should_repair,
    {
        "repair": "repair_slide_outline",
        "done": END,
    },
)
graph.add_edge("repair_slide_outline", "validate_slide_outline")

coursepilot_ppt_agent = graph.compile()
