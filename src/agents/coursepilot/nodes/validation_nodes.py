from agents.coursepilot.states.lesson_state import LessonGraphState
from coursepilot.schemas.lesson_schema import LessonDesignContent, LessonGenerationParams
from coursepilot.validators import LessonValidator


def validate_lesson_design(state: LessonGraphState) -> LessonGraphState:
    """用 LessonValidator 做 schema、课时数、时间、引用等校验"""
    params = LessonGenerationParams.model_validate(state.get("lesson_params", {}))
    design = LessonDesignContent.model_validate(state["lesson_design"])
    report = LessonValidator().validate(
        design,
        expected_sessions=params.total_sessions,
        session_duration=params.session_duration,
    )
    report.repair_attempts = int(state.get("validation_report", {}).get("repair_attempts", 0))
    return {"validation_report": report.model_dump(mode="json")}
