from pathlib import Path

from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.exporters import PPTXExporter
from coursepilot.models import ExportFile, GenerationTask, LessonDesign, SlideOutline
from coursepilot.schemas.lesson_schema import LessonDesignContent, Reference
from coursepilot.schemas.ppt_schema import (
    PPTExportResponse,
    PPTGenerationParams,
    PPTGenerationResponse,
    SlideItem,
    SlideOutlineContent,
)
from coursepilot.validators import PPTValidator


class PPTService:
    def __init__(self, session: Session):
        self.session = session
        self.validator = PPTValidator()

    def generate_outline(
        self,
        lesson_id: str,
        params: PPTGenerationParams,
    ) -> PPTGenerationResponse | None:
        lesson = self.session.get(LessonDesign, lesson_id)
        if lesson is None:
            return None

        task = GenerationTask(
            course_id=lesson.course_id,
            task_type="ppt_outline",
            status="running",
            input_params_json=params.model_dump(mode="json"),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        try:
            lesson_content = LessonDesignContent.model_validate(lesson.content_json)
            outline_content = self._build_outline(lesson.id, lesson_content, params)
            validation_report = self.validator.validate(
                outline_content,
                expected_slide_count=params.slide_count,
                total_sessions=lesson_content.total_sessions,
            )
            outline = SlideOutline(
                course_id=lesson.course_id,
                task_id=task.id,
                lesson_design_id=lesson.id,
                status="draft" if validation_report.passed else "needs_review",
                outline_json=outline_content.model_dump(mode="json"),
                validation_report_json=validation_report.model_dump(mode="json"),
            )
            task.status = "completed" if validation_report.passed else "needs_review"
            task.validation_report_json = validation_report.model_dump(mode="json")
            self.session.add(outline)
            self.session.commit()
            self.session.refresh(outline)
            return PPTGenerationResponse(
                outline_id=outline.id,
                task_id=task.id,
                status=outline.status,
                outline=outline_content,
                validation_report=validation_report,
            )
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)
            self.session.commit()
            raise

    def get_outline(self, outline_id: str) -> SlideOutline | None:
        return self.session.get(SlideOutline, outline_id)

    def export_pptx(self, outline_id: str) -> PPTExportResponse | None:
        outline = self.get_outline(outline_id)
        if outline is None:
            return None

        content = SlideOutlineContent.model_validate(outline.outline_json)
        report = self.validator.validate(content)
        if not report.passed:
            raise ValueError("PPT outline validation failed before export")
        export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / outline.course_id
        file_name = f"ppt_outline_{outline.id}.pptx"
        output_path = PPTXExporter().export(content, export_dir / file_name)

        export_file = ExportFile(
            course_id=outline.course_id,
            task_id=outline.task_id,
            file_type="pptx",
            file_name=file_name,
            file_path=str(output_path),
            file_role="pptx",
        )
        self.session.add(export_file)
        self.session.flush()
        outline.pptx_file_id = export_file.id
        self.session.commit()
        self.session.refresh(export_file)
        return PPTExportResponse(
            outline_id=outline.id,
            file_id=export_file.id,
            file_name=export_file.file_name,
            file_path=export_file.file_path,
        )

    def _build_outline(
        self,
        lesson_id: str,
        lesson: LessonDesignContent,
        params: PPTGenerationParams,
    ) -> SlideOutlineContent:
        references = self._references(lesson)
        slides: list[SlideItem] = [
            SlideItem(
                slide_index=1,
                slide_type="title",
                title=f"{lesson.course_name}: {lesson.chapter}",
                bullet_points=[f"{lesson.total_sessions} sessions", f"{lesson.session_duration} minutes each"],
                speaker_notes="Opening slide generated from the structured lesson design.",
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
                    speaker_notes=session.session_title,
                    references=[ref],
                    source_session_index=session.session_index,
                )
            )
            slides.append(
                SlideItem(
                    slide_index=len(slides) + 1,
                    slide_type="content",
                    title=f"Session {session.session_index}: Key Points",
                    bullet_points=(session.key_points + session.difficult_points)[:6],
                    speaker_notes="Cover key points before practice activities.",
                    references=[ref],
                    source_session_index=session.session_index,
                )
            )

        summary_ref = references[0]
        slides.append(
            SlideItem(
                slide_index=len(slides) + 1,
                slide_type="summary",
                title="Summary and Homework",
                bullet_points=[
                    point for session in lesson.sessions for point in session.homework_suggestion[:1]
                ]
                or ["Review the key points and complete the assigned practice."],
                references=[summary_ref],
            )
        )
        if params.include_references:
            slides.append(
                SlideItem(
                    slide_index=len(slides) + 1,
                    slide_type="references",
                    title="Source References",
                    bullet_points=[
                        f"{ref.source_type or 'source'} | {ref.chapter or '-'} | chunk={ref.chunk_id}"
                        for ref in references[:8]
                    ],
                    references=references[:8],
                )
            )

        if params.slide_count is not None:
            slides = self._fit_slide_count(slides, params.slide_count, references)
        for index, slide in enumerate(slides, start=1):
            slide.slide_index = index

        return SlideOutlineContent(
            course_name=lesson.course_name,
            chapter=lesson.chapter,
            lesson_id=lesson_id,
            style_template=params.style_template,
            slides=slides,
        )

    def _fit_slide_count(
        self,
        slides: list[SlideItem],
        target_count: int,
        references: list[Reference],
    ) -> list[SlideItem]:
        if len(slides) > target_count:
            if slides[-1].slide_type == "references" and target_count >= 3:
                return slides[: target_count - 1] + [slides[-1]]
            return slides[:target_count]
        while len(slides) < target_count:
            index = len(slides) + 1
            slides.insert(
                -1 if slides[-1].slide_type == "references" else len(slides),
                SlideItem(
                    slide_index=index,
                    slide_type="activity",
                    title=f"Classroom Activity {index}",
                    bullet_points=[
                        "Discuss the concept with a concrete course example.",
                        "Ask students to explain the source-backed reasoning.",
                    ],
                    references=[references[(index - 1) % len(references)]],
                ),
            )
        return slides

    def _references(self, lesson: LessonDesignContent) -> list[Reference]:
        refs: list[Reference] = []
        seen: set[str] = set()
        for session in lesson.sessions:
            for ref in session.references:
                if ref.chunk_id in seen:
                    continue
                seen.add(ref.chunk_id)
                refs.append(ref)
        return refs or [Reference(chunk_id="manual-context")]
