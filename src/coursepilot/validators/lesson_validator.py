from coursepilot.schemas.lesson_schema import LessonDesignContent, LessonValidationReport


class LessonValidator:
    def validate(
        self,
        lesson_design: LessonDesignContent,
        *,
        expected_sessions: int,
        session_duration: int,
    ) -> LessonValidationReport:
        errors: list[str] = []

        session_count_valid = len(lesson_design.sessions) == expected_sessions
        if not session_count_valid:
            errors.append("session_count_valid failed")

        plan_count_valid = len(lesson_design.session_plan) == expected_sessions
        if not plan_count_valid:
            errors.append("session_plan count does not match expected sessions")

        time_allocation_valid = True
        for plan in lesson_design.session_plan:
            plan_minutes = sum(item.minutes for item in plan.time_allocation)
            if plan.duration != session_duration or plan_minutes != session_duration:
                time_allocation_valid = False
                errors.append(f"time allocation invalid for session {plan.session_index}")

        required_fields_valid = all(
            session.teaching_objectives and session.key_points and session.teaching_process
            for session in lesson_design.sessions
        )
        if not required_fields_valid:
            errors.append("required fields missing")

        knowledge_coverage_valid = bool(lesson_design.knowledge_points) and all(
            session.key_points for session in lesson_design.sessions
        )
        if not knowledge_coverage_valid:
            errors.append("knowledge coverage missing")

        citation_valid = all(session.references for session in lesson_design.sessions)
        if not citation_valid:
            errors.append("references missing")

        return LessonValidationReport(
            session_count_valid=session_count_valid and plan_count_valid,
            time_allocation_valid=time_allocation_valid,
            required_fields_valid=required_fields_valid,
            knowledge_coverage_valid=knowledge_coverage_valid,
            citation_valid=citation_valid,
            errors=errors,
        )

