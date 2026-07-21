from typing import Any, TypedDict

from langchain_core.messages import AnyMessage


class LessonGraphState(TypedDict, total=False):  # total=False 表示字段不是一开始都必须存在
    messages: list[AnyMessage]
    course_id: str
    lesson_params: dict[str, Any]
    retrieved_contexts: list[dict[str, Any]]
    knowledge_points: list[str]
    session_plan: list[dict[str, Any]]
    lesson_design: dict[str, Any]
    validation_report: dict[str, Any]
