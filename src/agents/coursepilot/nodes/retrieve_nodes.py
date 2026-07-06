from typing import Any

from agents.coursepilot.states.lesson_state import LessonGraphState
from coursepilot.rag.retriever import CoursePilotRetriever


LESSON_CONTEXT_ERROR = (
    "No course knowledge base context found. "
    "Build course documents before generating a lesson design."
)
EXAM_CONTEXT_ERROR = (
    "No course knowledge base context found. Build course documents before generating an exam."
)


def retrieve_course_context(state: LessonGraphState) -> LessonGraphState:
    """检索课程知识库上下文"""
    # 如果 state 中已经有检索到的上下文，直接返回这些上下文
    if state.get("retrieved_contexts"):
        return {"retrieved_contexts": state.get("retrieved_contexts", [])}

    course_id = state.get("course_id")
    # 如果state 中没有检索到的上下文
    # 读错误信息
    required_context_error = _required_context_error(state)
    # 如果也没有 course_id，则无法检索上下文，直接返回空列表或抛出错误
    if not course_id:
        if required_context_error:
            raise ValueError(required_context_error)
        return {"retrieved_contexts": []}
    # 如果state无已检索到的上下文且有 course_id，则根据 state 中的参数构造查询，调用 CoursePilotRetriever 检索上下文
    query, top_k = _query_from_state(state)
    results = CoursePilotRetriever().search(course_id=course_id, query=query, top_k=top_k)
    if not results and required_context_error:
        raise ValueError(required_context_error)
    return {"retrieved_contexts": [result.model_dump(mode="json") for result in results]}


def _required_context_error(state: dict[str, Any]) -> str | None:
    """
    返回在检索上下文是必需的情况下产品的工作流错误消息。
    """
    # 如果 state 中有 lesson_params 或 exam_params，但没有检索到上下文，则返回错误消息
    if "lesson_params" in state:
        return LESSON_CONTEXT_ERROR
    if "exam_params" in state:
        return EXAM_CONTEXT_ERROR
    return None


def _query_from_state(state: dict[str, Any]) -> tuple[str, int]:
    """从 state 中提取查询参数"""
    if "lesson_params" in state:
        params = state["lesson_params"]
        query_parts = [params.get("chapter_range", "")]
        if params.get("teaching_focus"):
            query_parts.append(params["teaching_focus"])
        return " ".join(part for part in query_parts if part).strip(), 8
    if "exam_params" in state:
        params = state["exam_params"]
        return str(params.get("chapter_range", "")).strip(), 8
    return str(state.get("query", "")).strip(), 5
