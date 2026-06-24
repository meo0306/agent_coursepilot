from docx import Document

from coursepilot.exporters import LessonDocxExporter
from coursepilot.schemas.lesson_schema import (
    LessonDesignContent,
    LessonSession,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)


def test_lesson_docx_exporter_writes_file(tmp_path):
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
                teaching_process=[
                    TeachingProcessItem(stage="Intro", minutes=5, content="case")
                ],
                references=[Reference(chunk_id="chunk-1")],
            )
        ],
    )

    output = LessonDocxExporter().export(design, tmp_path / "lesson.docx")

    assert output.exists()
    doc = Document(output)
    assert "AI - Search" in doc.paragraphs[0].text

