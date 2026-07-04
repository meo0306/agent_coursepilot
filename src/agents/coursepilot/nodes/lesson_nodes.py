import re
from typing import Any

from langchain_core.messages import AIMessage

from agents.coursepilot.states.lesson_state import LessonGraphState
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.lesson_schema import (
    LessonDesignContent,
    LessonGenerationParams,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)


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
    """知识点提取"""
    contexts = state.get("retrieved_contexts", [])
    points: list[str] = []
    seen: set[str] = set()
    for context in contexts:
        content = str(context.get("content", ""))
        for token in re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", content):
            if token in seen:
                continue
            seen.add(token)
            points.append(token)
            if len(points) >= 12:
                return {"knowledge_points": points}
    return {"knowledge_points": points}


def plan_sessions(state: LessonGraphState) -> LessonGraphState:
    params = LessonGenerationParams.model_validate(state.get("lesson_params", {}))
    points = state.get("knowledge_points", []) or [params.chapter_range]
    plans: list[dict[str, Any]] = []
    for index in range(1, params.total_sessions + 1):
        session_points = _slice(points, index, params.total_sessions)
        allocation = _allocation(params.session_duration)
        plans.append(
            SessionPlan(
                session_index=index,
                session_title=f"{params.chapter_range} - {session_points[0]}",
                duration=params.session_duration,
                knowledge_points=session_points,
                teaching_focus=params.teaching_focus or f"Understand {session_points[0]}",
                difficulty_points=session_points[-2:],
                time_allocation=allocation,
            ).model_dump(mode="json")
        )
    return {"session_plan": plans}


def generate_lesson_design(state: LessonGraphState) -> LessonGraphState:
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
    return {"lesson_design": design.model_dump(mode="json")}


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

