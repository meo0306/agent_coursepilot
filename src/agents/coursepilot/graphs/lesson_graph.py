"""
课程设计 Agent workflow
"""

from typing import Literal

from langgraph.graph import END, StateGraph

from agents.coursepilot.nodes.lesson_nodes import (
    chat_response,
    extract_knowledge_points,
    generate_lesson_design,
    plan_sessions,
    reflect_and_revise,
    validate_lesson_design,
)
from agents.coursepilot.nodes.retrieve_nodes import retrieve_course_context
from agents.coursepilot.states.lesson_state import LessonGraphState
from core.settings import settings


def route_entry(state: LessonGraphState) -> Literal["chat", "workflow"]:
    """
    Determines the entry point for the lesson graph based on the state.
    基于当前状态确定课程图的入口点。
    """
    if "lesson_params" in state:
        return "workflow"
    return "chat"


def should_repair(state: LessonGraphState) -> Literal["repair", "done"]:
    """
    Determines whether the lesson design should be repaired based on the validation report.
    基于校验报告确定课程设计是否需要修复。
    """
    report = state.get("validation_report", {})
    passed = all(
        report.get(key, False)
        for key in [
            "schema_valid",
            "session_count_valid",
            "time_allocation_valid",
            "required_fields_valid",
            "knowledge_coverage_valid",
            "citation_valid",
        ]
    )
    if (
        not passed
        and int(report.get("repair_attempts", 0)) < settings.COURSEPILOT_MAX_REPAIR_ROUNDS
    ):
        return "repair"
    return "done"


# 构造
graph = StateGraph[
    LessonGraphState,
    None,
    LessonGraphState,
    LessonGraphState,
](LessonGraphState)
graph.add_node("route", lambda state: {})
graph.add_node("chat_response", chat_response)
graph.add_node("retrieve_course_context", retrieve_course_context)
graph.add_node("extract_knowledge_points", extract_knowledge_points)
graph.add_node("plan_sessions", plan_sessions)
graph.add_node("generate_lesson_design", generate_lesson_design)
graph.add_node("validate_lesson_design", validate_lesson_design)
graph.add_node("reflect_and_revise", reflect_and_revise)

graph.set_entry_point("route")
graph.add_conditional_edges(
    "route",
    route_entry,
    {
        "chat": "chat_response",
        "workflow": "retrieve_course_context",
    },
)
graph.add_edge("chat_response", END)
graph.add_edge("retrieve_course_context", "extract_knowledge_points")
graph.add_edge("extract_knowledge_points", "plan_sessions")
graph.add_edge("plan_sessions", "generate_lesson_design")
graph.add_edge("generate_lesson_design", "validate_lesson_design")
graph.add_conditional_edges(
    "validate_lesson_design",
    should_repair,
    {
        "repair": "reflect_and_revise",
        "done": END,
    },
)
graph.add_edge("reflect_and_revise", "validate_lesson_design")

coursepilot_lesson_agent = graph.compile()
