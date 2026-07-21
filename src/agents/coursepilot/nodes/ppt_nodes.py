from langchain_core.messages import AIMessage

from agents.coursepilot.states.ppt_state import PPTGraphState
from coursepilot.llm import generate_structured
from coursepilot.schemas.lesson_schema import LessonDesignContent, Reference
from coursepilot.schemas.ppt_schema import PPTGenerationParams, SlideItem, SlideOutlineContent
from coursepilot.validators import PPTValidator, inherit_session_references, session_references


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
    """根据 lesson_design 和 ppt_params 生成 PPT 大纲 SlideOutlineContent"""
    outline = generate_structured(
        prompt_name="ppt/generate_slide_outline",
        output_schema=SlideOutlineContent,
        payload={
            "ppt_params": state.get("ppt_params", {}),
            "lesson_design": state.get("lesson_design", {}),
        },
        fallback=lambda: _deterministic_slide_outline(state),
    )
    return {"slide_outline": outline.model_dump(mode="json")}


def _deterministic_slide_outline(state: PPTGraphState) -> SlideOutlineContent:
    """fallback策略：直接组装课程信息和检索到的内容"""
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
                bullet_points=[
                    f"{ref.source_type or 'source'} chunk={ref.chunk_id}" for ref in references[:8]
                ],
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
    return outline


def validate_slide_outline(state: PPTGraphState) -> PPTGraphState:
    """校验页数、类型、内容、课时来源、引用等是否符合要求，返回 validation_report"""
    params = PPTGenerationParams.model_validate(state.get("ppt_params", {}))
    lesson = LessonDesignContent.model_validate(state.get("lesson_design", {}))
    outline = inherit_session_references(
        SlideOutlineContent.model_validate(state.get("slide_outline", {})),
        lesson,
    )
    references_by_session = session_references(lesson)
    valid_chunk_ids = set(state.get("valid_chunk_ids", []))
    if "valid_chunk_ids" not in state:
        valid_chunk_ids = {
            reference.chunk_id
            for references in references_by_session.values()
            for reference in references
        }
    report = PPTValidator().validate(
        outline,
        expected_slide_count=params.slide_count,
        total_sessions=lesson.total_sessions,
        valid_session_indices=set(references_by_session),
        valid_chunk_ids=valid_chunk_ids,
        session_reference_ids={
            session_index: {reference.chunk_id for reference in references}
            for session_index, references in references_by_session.items()
        },
    )
    report.repair_attempts = int(state.get("validation_report", {}).get("repair_attempts", 0))
    return {
        "slide_outline": outline.model_dump(mode="json"),
        "validation_report": report.model_dump(mode="json"),
    }


def repair_slide_outline(state: PPTGraphState) -> PPTGraphState:
    """根据 validation_report 修复 slide_outline"""
    report = dict(state.get("validation_report", {}))
    report["repair_attempts"] = int(report.get("repair_attempts", 0)) + 1
    outline = generate_structured(
        prompt_name="ppt/repair_slide_outline",
        output_schema=SlideOutlineContent,
        payload={
            "slide_outline": state.get("slide_outline", {}),
            "lesson_design": state.get("lesson_design", {}),
            "validation_report": report,
        },
        fallback=lambda: _deterministic_repair_slide_outline(state),
    )
    return {
        "slide_outline": outline.model_dump(mode="json"),
        "validation_report": report,
    }


def _deterministic_repair_slide_outline(state: PPTGraphState) -> SlideOutlineContent:
    """fallback策略：根据 validation_report 规则化修复 slide_outline"""
    outline = SlideOutlineContent.model_validate(state.get("slide_outline", {}))
    references = _references(LessonDesignContent.model_validate(state.get("lesson_design", {})))
    for slide in outline.slides:
        if slide.slide_type != "title" and not slide.references:
            slide.references = [references[0]]
        if not slide.bullet_points:
            slide.bullet_points = ["Review the source-grounded teaching point."]
    return outline


def _references(lesson: LessonDesignContent) -> list[Reference]:
    """fallback策略：从 lesson.sessions 中收集所有 references，去重后返回"""
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
    """fallback策略：根据 target_count 调整 slides 数量，保留 references slide"""
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
