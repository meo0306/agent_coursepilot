from agents.coursepilot.states.lesson_state import LessonGraphState


def reflect_and_revise(state: LessonGraphState) -> LessonGraphState:
    report = state.get("validation_report", {})
    report["repair_attempts"] = int(report.get("repair_attempts", 0)) + 1
    return {"validation_report": report}

