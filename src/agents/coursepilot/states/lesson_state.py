from typing import Any, TypedDict

from langchain_core.messages import AnyMessage


class LessonGraphState(TypedDict, total=False):
    messages: list[AnyMessage]
    lesson_params: dict[str, Any]
    retrieved_contexts: list[dict[str, Any]]
    knowledge_points: list[str]
    session_plan: list[dict[str, Any]]
    lesson_design: dict[str, Any]
    validation_report: dict[str, Any]

