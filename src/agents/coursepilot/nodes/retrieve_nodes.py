from agents.coursepilot.states.lesson_state import LessonGraphState


def retrieve_course_context(state: LessonGraphState) -> LessonGraphState:
    return {"retrieved_contexts": state.get("retrieved_contexts", [])}

