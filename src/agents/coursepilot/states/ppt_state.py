from typing import Any, TypedDict

from langchain_core.messages import AnyMessage


class PPTGraphState(TypedDict, total=False):
    messages: list[AnyMessage]
    course_id: str
    ppt_params: dict[str, Any]
    lesson_design: dict[str, Any]
    slide_outline: dict[str, Any]
    validation_report: dict[str, Any]
