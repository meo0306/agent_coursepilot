from typing import Literal

from langgraph.graph import END, StateGraph

from agents.coursepilot.nodes.exam_nodes import (
    chat_response,
    generate_exam_questions,
    plan_exam_blueprint,
    repair_exam_questions,
    validate_exam_questions,
)
from agents.coursepilot.nodes.retrieve_nodes import retrieve_course_context
from agents.coursepilot.states.exam_state import ExamGraphState
from core.settings import settings


def route_entry(state: ExamGraphState) -> Literal["chat", "workflow", "questions"]:
    """入口函数，根据 state 中的 workflow_phase 和 exam_blueprint 判断当前应该进入哪个节点"""
    # 已经有确认后的蓝图，直接进入出题阶段
    if state.get("workflow_phase") == "questions" and "exam_blueprint" in state:
        return "questions"
    # 如果传入 exam_params，表示要创建蓝图
    if "exam_params" in state:
        return "workflow"
    return "chat"


def should_repair(state: ExamGraphState) -> Literal["repair", "done"]:
    """根据 state 中的 validation_report 判断是否需要进入 repair 节点"""
    report = state.get("validation_report", {})
    passed = all(
        report.get(key, False)
        for key in [
            "schema_valid",
            "question_count_valid",
            "score_valid",
            "option_valid",
            "answer_valid",
            "explanation_valid",
            "knowledge_coverage_valid",
            "citation_valid",
            "duplicate_valid",
        ]
    )
    if (
        not passed
        and int(report.get("repair_attempts", 0)) < settings.COURSEPILOT_MAX_REPAIR_ROUNDS
    ):
        return "repair"
    return "done"


def after_blueprint(state: ExamGraphState) -> Literal["generate", "done"]:
    """根据 state 中的 workflow_phase 判断是否需要进入 generate 节点"""
    # create_blueprint API 只生成蓝图，不直接出题，给教师留下审核/确认蓝图的步骤
    if state.get("workflow_phase") == "blueprint":
        return "done"
    return "generate"


graph = StateGraph[
    ExamGraphState,
    None,
    ExamGraphState,
    ExamGraphState,
](ExamGraphState)
graph.add_node("route", lambda state: {})
graph.add_node("chat_response", chat_response)
graph.add_node("retrieve_course_context", retrieve_course_context)
graph.add_node("plan_exam_blueprint", plan_exam_blueprint)
graph.add_node("generate_exam_questions", generate_exam_questions)
graph.add_node("validate_exam_questions", validate_exam_questions)
graph.add_node("repair_exam_questions", repair_exam_questions)

graph.set_entry_point("route")
graph.add_conditional_edges(
    "route",
    route_entry,
    {
        "chat": "chat_response",
        "workflow": "retrieve_course_context",
        "questions": "generate_exam_questions",
    },
)
graph.add_edge("chat_response", END)
graph.add_edge("retrieve_course_context", "plan_exam_blueprint")
graph.add_conditional_edges(
    "plan_exam_blueprint",
    after_blueprint,
    {
        "generate": "generate_exam_questions",
        "done": END,
    },
)
graph.add_edge("generate_exam_questions", "validate_exam_questions")
graph.add_conditional_edges(
    "validate_exam_questions",
    should_repair,
    {
        "repair": "repair_exam_questions",
        "done": END,
    },
)
graph.add_edge("repair_exam_questions", "validate_exam_questions")

coursepilot_exam_agent = graph.compile()
