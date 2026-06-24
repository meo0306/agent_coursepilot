from agents.coursepilot.states.lesson_state import LessonGraphState
from coursepilot.schemas.lesson_schema import LessonDesignContent, LessonGenerationParams
from coursepilot.validators import LessonValidator


def validate_lesson_design(state: LessonGraphState) -> LessonGraphState:
    params = LessonGenerationParams.model_validate(state.get("lesson_params", {}))
    design = LessonDesignContent.model_validate(state["lesson_design"])
    report = LessonValidator().validate(
        design,
        expected_sessions=params.total_sessions,
        session_duration=params.session_duration,
    )
    return {"validation_report": report.model_dump(mode="json")}

