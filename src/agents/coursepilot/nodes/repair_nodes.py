from agents.coursepilot.states.lesson_state import LessonGraphState
from coursepilot.llm import generate_structured
from coursepilot.schemas.lesson_schema import LessonDesignContent, Reference


def reflect_and_revise(state: LessonGraphState) -> LessonGraphState:
    """根据验证报告反思并修复课程设计"""
    # 读取验证报告并增加修复尝试次数
    report = state.get("validation_report", {})
    report["repair_attempts"] = int(report.get("repair_attempts", 0)) + 1
    # 如果课程设计不存在，则只返回验证报告
    if "lesson_design" not in state:
        return {"validation_report": report}
    # 调用 LLM 生成修复后的课程设计，如果失败则使用 deterministic fallback
    repaired = generate_structured(
        prompt_name="repair/fix_json",
        output_schema=LessonDesignContent,
        payload={
            "target_schema": "LessonDesignContent",
            "validation_report": report,
            "lesson_design": state.get("lesson_design", {}),
            "lesson_params": state.get("lesson_params", {}),
            "retrieved_contexts": state.get("retrieved_contexts", []),
        },
        fallback=lambda: _deterministic_repair(state),
    )
    return {
        "lesson_design": repaired.model_dump(mode="json"),
        "validation_report": report,
    }


def _deterministic_repair(state: LessonGraphState) -> LessonDesignContent:
    """fallback策略：根据 state 中的课程设计和检索上下文生成一个确定性的 LessonDesignContent"""
    content = LessonDesignContent.model_validate(state["lesson_design"])
    contexts = state.get("retrieved_contexts", [])
    fallback_ref = None
    if contexts:
        first = contexts[0]
        fallback_ref = Reference(
            chunk_id=first.get("chunk_id", "manual-context"),
            source_type=first.get("source_type"),
            chapter=first.get("chapter"),
            page=first.get("page"),
        )
    fallback_ref = fallback_ref or Reference(chunk_id="manual-context")
    for session in content.sessions:
        if not session.references:
            session.references = [fallback_ref]
        if not session.teaching_objectives:
            session.teaching_objectives = [f"Explain {session.session_title}"]
        if not session.key_points:
            session.key_points = content.knowledge_points[:1] or [content.chapter]
    return content
