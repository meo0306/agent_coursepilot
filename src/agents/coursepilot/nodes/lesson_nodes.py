from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel, Field

from agents.coursepilot.states.lesson_state import LessonGraphState
from coursepilot.llm import generate_structured
from coursepilot.rag.knowledge_points import KnowledgePointList, extract_keywords_deterministic
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.lesson_schema import (
    LessonDesignContent,
    LessonGenerationParams,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)


class SessionPlanSet(BaseModel):
    # 课时计划集合
    session_plan: list[SessionPlan] = Field(min_length=1)


def chat_response(state: LessonGraphState) -> LessonGraphState:
    """聊天入口，如果用户通过普通聊天方式调用这个 agent，返回一条 AIMessage，提示用户使用 API 生成教案"""
    return {
        "messages": [
            AIMessage(
                content=(
                    "CoursePilot lesson agent is available. "
                    "Use /api/coursepilot/courses/{course_id}/lessons/generate "
                    "for product workflow generation."
                )
            )
        ]
    }


def extract_knowledge_points(state: LessonGraphState) -> LessonGraphState:
    """从检索上下文中抽知识点"""
    # 从 state 中获取检索到的上下文
    contexts = state.get("retrieved_contexts", [])
    # 把检索到的 chunk 内容合并，作为知识点抽取材料
    content = "\n\n".join(str(context.get("content", "")) for context in contexts)
    # 调用 LLM 生成知识点列表，如果失败则使用 deterministic fallback
    result = generate_structured(
        prompt_name="lesson/extract_knowledge_points",
        output_schema=KnowledgePointList,
        payload={
            "lesson_params": state.get("lesson_params", {}),
            "retrieved_contexts": contexts,
            "max_points": 12,
        },
        # 无 LLM 时用正则关键词 fallback
        fallback=lambda: KnowledgePointList(
            knowledge_points=extract_keywords_deterministic(content, max_points=12)
        ),
    )
    return {"knowledge_points": result.knowledge_points[:12]}


def plan_sessions(state: LessonGraphState) -> LessonGraphState:
    """根据知识点和参数规划每个课时"""
    params = LessonGenerationParams.model_validate(state.get("lesson_params", {}))
    points = state.get("knowledge_points", []) or [params.chapter_range]
    result = generate_structured(
        prompt_name="lesson/plan_sessions",
        output_schema=SessionPlanSet,
        payload={
            "lesson_params": state.get("lesson_params", {}),
            "knowledge_points": points,
            "retrieved_contexts": state.get("retrieved_contexts", []),
        },
        fallback=lambda: SessionPlanSet(
            session_plan=[
                SessionPlan(
                    session_index=index,
                    session_title=f"{params.chapter_range} - {_slice(points, index, params.total_sessions)[0]}",
                    duration=params.session_duration,
                    knowledge_points=_slice(points, index, params.total_sessions),
                    teaching_focus=params.teaching_focus
                    or f"Understand {_slice(points, index, params.total_sessions)[0]}",
                    difficulty_points=_slice(points, index, params.total_sessions)[-2:],
                    time_allocation=_allocation(params.session_duration),
                )
                for index in range(1, params.total_sessions + 1)
            ]
        ),
    )
    return {"session_plan": [plan.model_dump(mode="json") for plan in result.session_plan]}


def generate_lesson_design(state: LessonGraphState) -> LessonGraphState:
    """生成完整LessonDesignContent"""
    design = generate_structured(
        prompt_name="lesson/generate_lesson_design",
        output_schema=LessonDesignContent,
        payload={
            "lesson_params": state.get("lesson_params", {}),
            "retrieved_contexts": state.get("retrieved_contexts", []),
            "knowledge_points": state.get("knowledge_points", []),
            "session_plan": state.get("session_plan", []),
        },
        fallback=lambda: _deterministic_lesson_design(state),
    )
    return {"lesson_design": design.model_dump(mode="json")}


def _deterministic_lesson_design(state: LessonGraphState) -> LessonDesignContent:
    """fallback策略：根据 state 中的参数和计划生成一个确定性的 LessonDesignContent"""
    params = LessonGenerationParams.model_validate(state.get("lesson_params", {}))
    contexts = [KBSearchResult.model_validate(item) for item in state.get("retrieved_contexts", [])]
    points = state.get("knowledge_points", []) or [params.chapter_range]
    references = [
        Reference(
            chunk_id=context.chunk_id,
            source_type=context.source_type,
            chapter=context.chapter,
            page=context.page,
        )
        for context in contexts[: max(1, min(len(contexts), params.total_sessions))]
    ] or [Reference(chunk_id="manual-context")]
    sessions = []
    for plan_data in state.get("session_plan", []):
        plan = SessionPlan.model_validate(plan_data)
        reference = references[(plan.session_index - 1) % len(references)]
        sessions.append(
            {
                "session_index": plan.session_index,
                "session_title": plan.session_title,
                "teaching_objectives": [
                    f"Explain {point}" for point in plan.knowledge_points[:3]
                ],
                "key_points": plan.knowledge_points,
                "difficult_points": plan.difficulty_points,
                "teaching_process": [
                    TeachingProcessItem(
                        stage=item.activity,
                        minutes=item.minutes,
                        content=f"{item.activity}: {', '.join(plan.knowledge_points[:3])}",
                    ).model_dump(mode="json")
                    for item in plan.time_allocation
                ],
                "interaction_design": [f"Discuss {plan.knowledge_points[0]} in groups."],
                "blackboard_or_slide_suggestions": [f"Draw a concept map for {plan.session_title}."],
                "homework_suggestion": [f"Summarize {plan.knowledge_points[0]} with an example."],
                "references": [reference.model_dump(mode="json")],
            }
        )
    design = LessonDesignContent(
        course_name=str(state.get("lesson_params", {}).get("course_name", "CoursePilot Course")),
        chapter=params.chapter_range,
        total_sessions=params.total_sessions,
        session_duration=params.session_duration,
        retrieved_contexts=contexts,
        knowledge_points=points,
        session_plan=[SessionPlan.model_validate(item) for item in state.get("session_plan", [])],
        sessions=sessions,
    )
    return design


def _allocation(duration: int) -> list[TimeAllocation]:
    intro = max(5, duration // 9)
    practice = max(5, duration // 4)
    summary = 5
    lecture = duration - intro - practice - summary
    return [
        TimeAllocation(activity="导入与目标说明", minutes=intro),
        TimeAllocation(activity="核心概念讲解", minutes=lecture),
        TimeAllocation(activity="课堂练习与互动", minutes=practice),
        TimeAllocation(activity="总结与作业说明", minutes=summary),
    ]


def _slice(points: list[str], index: int, total: int) -> list[str]:
    bucket = max(1, len(points) // total)
    start = (index - 1) * bucket
    end = len(points) if index == total else start + bucket
    return points[start:end][:5] or points[:1]
