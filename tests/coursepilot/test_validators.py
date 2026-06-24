from coursepilot.schemas.lesson_schema import (
    LessonDesignContent,
    LessonSession,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)
from coursepilot.validators import LessonValidator


def test_lesson_validator_passes_valid_design():
    design = LessonDesignContent(
        course_name="AI",
        chapter="Search",
        total_sessions=1,
        session_duration=45,
        knowledge_points=["state space"],
        session_plan=[
            SessionPlan(
                session_index=1,
                session_title="Search",
                duration=45,
                knowledge_points=["state space"],
                teaching_focus="state space",
                difficulty_points=["abstraction"],
                time_allocation=[
                    TimeAllocation(activity="Intro", minutes=5),
                    TimeAllocation(activity="Lecture", minutes=30),
                    TimeAllocation(activity="Practice", minutes=5),
                    TimeAllocation(activity="Summary", minutes=5),
                ],
            )
        ],
        sessions=[
            LessonSession(
                session_index=1,
                session_title="Search",
                teaching_objectives=["Explain state space"],
                key_points=["state space"],
                difficult_points=["abstraction"],
                teaching_process=[
                    TeachingProcessItem(stage="Intro", minutes=5, content="case")
                ],
                references=[Reference(chunk_id="chunk-1")],
            )
        ],
    )

    report = LessonValidator().validate(design, expected_sessions=1, session_duration=45)

    assert report.passed is True

