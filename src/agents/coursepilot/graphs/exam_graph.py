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


def route_entry(state: ExamGraphState) -> Literal["chat", "workflow"]:
    if "exam_params" in state:
        return "workflow"
    return "chat"


def should_repair(state: ExamGraphState) -> Literal["repair", "done"]:
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
    if not passed and int(report.get("repair_attempts", 0)) < 2:
        return "repair"
    return "done"


graph = StateGraph(ExamGraphState)
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
    },
)
graph.add_edge("chat_response", END)
graph.add_edge("retrieve_course_context", "plan_exam_blueprint")
graph.add_edge("plan_exam_blueprint", "generate_exam_questions")
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
