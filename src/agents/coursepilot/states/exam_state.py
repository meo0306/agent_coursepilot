from typing import Any, TypedDict

from langchain_core.messages import AnyMessage


class ExamGraphState(TypedDict, total=False):
    messages: list[AnyMessage]
    exam_params: dict[str, Any]
    retrieved_contexts: list[dict[str, Any]]
    exam_blueprint: dict[str, Any]
    questions: list[dict[str, Any]]
    validation_report: dict[str, Any]
