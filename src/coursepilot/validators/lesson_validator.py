"""
教学设计校验器
"""

from coursepilot.schemas.lesson_schema import LessonDesignContent, LessonValidationReport


class LessonValidator:
    def validate(
        self,
        lesson_design: LessonDesignContent,
        *,
        expected_sessions: int,
        session_duration: int,
    ) -> LessonValidationReport:
        """"""
        errors: list[str] = []
        # 校验课时数量是否正确
        session_count_valid = len(lesson_design.sessions) == expected_sessions
        if not session_count_valid:
            errors.append("session_count_valid failed")
        # 校验课时计划数量是否正确
        plan_count_valid = len(lesson_design.session_plan) == expected_sessions
        if not plan_count_valid:
            errors.append("session_plan count does not match expected sessions")
        # 校验每个课时的时间分配是否等于用户要求的时长
        time_allocation_valid = True
        for plan in lesson_design.session_plan:
            plan_minutes = sum(item.minutes for item in plan.time_allocation)
            # 每个课时的 duration 和 每个课时内部的时间分配之和 必须和用户要求相同
            if plan.duration != session_duration or plan_minutes != session_duration:
                time_allocation_valid = False
                errors.append(f"time allocation invalid for session {plan.session_index}")

        # TODO: 三类校验需要区分具体是哪个字段没填/哪个知识点没覆盖/哪个课时没有引用
        # 校验必填字段是否完整：每个课时必须有教学目标、重点和教学过程
        required_fields_valid = all(
            session.teaching_objectives and session.key_points and session.teaching_process
            for session in lesson_design.sessions
        )
        if not required_fields_valid:
            errors.append("required fields missing")

        # 校验知识覆盖情况
        knowledge_coverage_valid = bool(lesson_design.knowledge_points) and all(
            session.key_points for session in lesson_design.sessions
        )
        if not knowledge_coverage_valid:
            errors.append("knowledge coverage missing")

        # 校验引用是否完整：每个课时都必须带至少一个引用
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
