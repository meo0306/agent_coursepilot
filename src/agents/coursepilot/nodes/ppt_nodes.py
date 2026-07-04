from langchain_core.messages import AIMessage

from agents.coursepilot.states.ppt_state import PPTGraphState
from coursepilot.schemas.lesson_schema import LessonDesignContent, Reference
from coursepilot.schemas.ppt_schema import PPTGenerationParams, SlideItem, SlideOutlineContent
from coursepilot.validators import PPTValidator


def chat_response(state: PPTGraphState) -> PPTGraphState:
    return {
        "messages": [
            AIMessage(
                content=(
                    "CoursePilot PPT agent is available. "
                    "Use /api/coursepilot/lessons/{lesson_id}/ppt/generate "
                    "for product workflow generation."
                )
            )
        ]
    }


def generate_slide_outline(state: PPTGraphState) -> PPTGraphState:
    params = PPTGenerationParams.model_validate(state.get("ppt_params", {}))
    lesson = LessonDesignContent.model_validate(state.get("lesson_design", {}))
    references = _references(lesson)
    slides: list[SlideItem] = [
        SlideItem(
            slide_index=1,
            slide_type="title",
            title=f"{lesson.course_name}: {lesson.chapter}",
            bullet_points=[f"{lesson.total_sessions} sessions"],
        )
    ]
    for session in lesson.sessions:
        ref = session.references[0] if session.references else references[0]
        slides.append(
            SlideItem(
                slide_index=len(slides) + 1,
                slide_type="objectives",
                title=f"Session {session.session_index}: Objectives",
                bullet_points=session.teaching_objectives[:5],
                references=[ref],
                source_session_index=session.session_index,
            )
        )
        slides.append(
            SlideItem(
                slide_index=len(slides) + 1,
                slide_type="content",
                title=f"Session {session.session_index}: Key Points",
                bullet_points=session.key_points[:6],
                references=[ref],
                source_session_index=session.session_index,
            )
        )
    if params.include_references:
        slides.append(
            SlideItem(
                slide_index=len(slides) + 1,
                slide_type="references",
                title="Source References",
                bullet_points=[f"{ref.source_type or 'source'} chunk={ref.chunk_id}" for ref in references[:8]],
                references=references[:8],
            )
        )
    if params.slide_count is not None:
        slides = _fit_slide_count(slides, params.slide_count, references)
    for index, slide in enumerate(slides, start=1):
        slide.slide_index = index
    outline = SlideOutlineContent(
        course_name=lesson.course_name,
        chapter=lesson.chapter,
        lesson_id=str(state.get("ppt_params", {}).get("lesson_id", "manual-lesson")),
        style_template=params.style_template,
        slides=slides,
    )
    return {"slide_outline": outline.model_dump(mode="json")}


def validate_slide_outline(state: PPTGraphState) -> PPTGraphState:
    params = PPTGenerationParams.model_validate(state.get("ppt_params", {}))
    lesson = LessonDesignContent.model_validate(state.get("lesson_design", {}))
    outline = SlideOutlineContent.model_validate(state.get("slide_outline", {}))
    report = PPTValidator().validate(
        outline,
        expected_slide_count=params.slide_count,
        total_sessions=lesson.total_sessions,
    )
    return {"validation_report": report.model_dump(mode="json")}


def repair_slide_outline(state: PPTGraphState) -> PPTGraphState:
    outline = SlideOutlineContent.model_validate(state.get("slide_outline", {}))
    references = _references(LessonDesignContent.model_validate(state.get("lesson_design", {})))
    for slide in outline.slides:
        if slide.slide_type != "title" and not slide.references:
            slide.references = [references[0]]
        if not slide.bullet_points:
            slide.bullet_points = ["Review the source-grounded teaching point."]
    report = dict(state.get("validation_report", {}))
    report["repair_attempts"] = int(report.get("repair_attempts", 0)) + 1
    return {
        "slide_outline": outline.model_dump(mode="json"),
        "validation_report": report,
    }


def _references(lesson: LessonDesignContent) -> list[Reference]:
    refs: list[Reference] = []
    seen: set[str] = set()
    for session in lesson.sessions:
        for ref in session.references:
            if ref.chunk_id in seen:
                continue
            seen.add(ref.chunk_id)
            refs.append(ref)
    return refs or [Reference(chunk_id="manual-context")]


def _fit_slide_count(
    slides: list[SlideItem],
    target_count: int,
    references: list[Reference],
) -> list[SlideItem]:
    if len(slides) > target_count:
        if slides[-1].slide_type == "references" and target_count >= 3:
            return slides[: target_count - 1] + [slides[-1]]
        return slides[:target_count]
    while len(slides) < target_count:
        slides.insert(
            -1 if slides[-1].slide_type == "references" else len(slides),
            SlideItem(
                slide_index=len(slides) + 1,
                slide_type="activity",
                title="Classroom Activity",
                bullet_points=["Discuss a course example.", "Summarize source-backed reasoning."],
                references=[references[0]],
            ),
        )
    return slides
