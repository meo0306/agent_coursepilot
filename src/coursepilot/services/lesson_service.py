from pathlib import Path

from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.exporters import LessonDocxExporter
from coursepilot.models import Course, ExportFile, GenerationTask, LessonDesign
from coursepilot.schemas.kb_schema import KBSearchRequest, KBSearchResult
from coursepilot.schemas.lesson_schema import (
    ExportFileRead,
    LessonDesignContent,
    LessonGenerationParams,
    LessonGenerationResponse,
    LessonRevisionRequest,
    LessonRevisionResponse,
    Reference,
    SessionPlan,
    TeachingProcessItem,
    TimeAllocation,
)
from coursepilot.services.kb_service import KnowledgeBaseService
from coursepilot.validators import LessonValidator


class LessonService:
    def __init__(self, session: Session):
        self.session = session
        self.validator = LessonValidator()

    def generate_lesson(
        self,
        course_id: str,
        params: LessonGenerationParams,
    ) -> LessonGenerationResponse:
        course = self.session.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course not found: {course_id}")

        task = GenerationTask(
            course_id=course_id,
            task_type="lesson_design",
            status="running",
            input_params_json=params.model_dump(),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        try:
            contexts = self._retrieve_contexts(course_id, params)
            if not contexts:
                raise ValueError(
                    "No course knowledge base context found. Build course documents before generating a lesson design."
                )

            lesson_design = self._build_lesson_design(course, params, contexts)
            validation_report = self.validator.validate(
                lesson_design,
                expected_sessions=params.total_sessions,
                session_duration=params.session_duration,
            )
            lesson = LessonDesign(
                course_id=course_id,
                task_id=task.id,
                chapter=params.chapter_range,
                status="draft" if validation_report.passed else "needs_review",
                total_sessions=params.total_sessions,
                content_json=lesson_design.model_dump(mode="json"),
                validation_report_json=validation_report.model_dump(mode="json"),
            )
            task.status = "completed" if validation_report.passed else "needs_review"
            task.intermediate_outputs_json = {"retrieved_contexts": [c.model_dump() for c in contexts]}
            task.validation_report_json = validation_report.model_dump(mode="json")
            self.session.add(lesson)
            self.session.commit()
            self.session.refresh(lesson)

            return LessonGenerationResponse(
                lesson_id=lesson.id,
                task_id=task.id,
                status=lesson.status,
                lesson_design=lesson_design,
                validation_report=validation_report,
            )
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)
            self.session.commit()
            raise

    def get_lesson(self, lesson_id: str) -> LessonDesign | None:
        return self.session.get(LessonDesign, lesson_id)

    def revise_lesson(
        self,
        lesson_id: str,
        request: LessonRevisionRequest,
    ) -> LessonRevisionResponse | None:
        lesson = self.get_lesson(lesson_id)
        if lesson is None:
            return None

        content = LessonDesignContent.model_validate(lesson.content_json)
        target_index = self._resolve_target_session(content, request.target_scope)
        target_session = content.sessions[target_index]
        note = f"Revision for {request.target_scope}: {request.feedback_text}"

        if request.keep_unchanged_parts:
            target_session.interaction_design.append(note)
        else:
            target_session.teaching_process.append(
                TeachingProcessItem(stage="Revision", minutes=5, content=note)
            )
        target_session.blackboard_or_slide_suggestions.append(
            f"Update emphasis according to teacher feedback: {request.feedback_text}"
        )

        report = self.validator.validate(
            content,
            expected_sessions=content.total_sessions,
            session_duration=content.session_duration,
        )
        lesson.content_json = content.model_dump(mode="json")
        lesson.validation_report_json = report.model_dump(mode="json")
        lesson.status = "draft" if report.passed else "needs_review"
        self.session.commit()

        return LessonRevisionResponse(
            lesson_id=lesson.id,
            modification_summary=f"Updated session {target_session.session_index}: {request.target_scope}",
            lesson_design=content,
            validation_report=report,
        )

    def export_lesson_docx(self, lesson_id: str) -> ExportFileRead | None:
        lesson = self.get_lesson(lesson_id)
        if lesson is None:
            return None

        content = LessonDesignContent.model_validate(lesson.content_json)
        export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / lesson.course_id
        file_name = f"lesson_design_{lesson.id}.docx"
        output_path = export_dir / file_name
        LessonDocxExporter().export(content, output_path)

        export_file = ExportFile(
            course_id=lesson.course_id,
            task_id=lesson.task_id,
            file_type="docx",
            file_name=file_name,
            file_path=str(output_path),
            file_role="lesson_docx",
        )
        self.session.add(export_file)
        self.session.commit()
        self.session.refresh(export_file)
        return ExportFileRead.model_validate(export_file)

    def _retrieve_contexts(
        self,
        course_id: str,
        params: LessonGenerationParams,
    ) -> list[KBSearchResult]:
        queries = [params.chapter_range]
        if params.teaching_focus:
            queries.append(params.teaching_focus)
        results: list[KBSearchResult] = []
        seen: set[str] = set()
        kb_service = KnowledgeBaseService(self.session)
        for query in queries:
            for result in kb_service.search(
                course_id,
                KBSearchRequest(query=query, top_k=5),
            ):
                if result.chunk_id in seen:
                    continue
                seen.add(result.chunk_id)
                results.append(result)
        return results[:8]

    def _build_lesson_design(
        self,
        course: Course,
        params: LessonGenerationParams,
        contexts: list[KBSearchResult],
    ) -> LessonDesignContent:
        knowledge_points = self._knowledge_points_from_contexts(contexts)
        references = [
            Reference(
                chunk_id=context.chunk_id,
                source_type=context.source_type,
                chapter=context.chapter,
                page=context.page,
            )
            for context in contexts[: max(1, min(len(contexts), params.total_sessions))]
        ]

        session_plans: list[SessionPlan] = []
        sessions = []
        for index in range(1, params.total_sessions + 1):
            session_points = self._slice_for_session(knowledge_points, index, params.total_sessions)
            if not session_points:
                session_points = knowledge_points[:3] or [params.chapter_range]
            reference = references[(index - 1) % len(references)]
            allocation = self._default_time_allocation(params.session_duration)
            title_focus = session_points[0] if session_points else params.chapter_range
            session_plans.append(
                SessionPlan(
                    session_index=index,
                    session_title=f"{params.chapter_range} - {title_focus}",
                    duration=params.session_duration,
                    knowledge_points=session_points,
                    teaching_focus=params.teaching_focus or f"Understand and apply {title_focus}",
                    difficulty_points=session_points[-2:],
                    time_allocation=allocation,
                )
            )
            sessions.append(
                {
                    "session_index": index,
                    "session_title": f"{params.chapter_range} - {title_focus}",
                    "teaching_objectives": [
                        f"Explain the key idea of {point}" for point in session_points[:3]
                    ],
                    "key_points": session_points,
                    "difficult_points": session_points[-2:],
                    "teaching_process": [
                        TeachingProcessItem(
                            stage=item.activity,
                            minutes=item.minutes,
                            content=self._process_content(item.activity, session_points, contexts),
                        )
                        for item in allocation
                    ],
                    "interaction_design": [
                        f"Ask students to connect {session_points[0]} with a concrete course example."
                    ]
                    if params.include_interaction and session_points
                    else [],
                    "blackboard_or_slide_suggestions": [
                        f"Use a concept map for {params.chapter_range}.",
                        "List retrieved source chunks on the final slide.",
                    ],
                    "homework_suggestion": [
                        f"Summarize {', '.join(session_points[:3])} with one example."
                    ]
                    if params.include_homework
                    else [],
                    "references": [reference],
                }
            )

        return LessonDesignContent(
            course_name=course.course_name,
            chapter=params.chapter_range,
            total_sessions=params.total_sessions,
            session_duration=params.session_duration,
            retrieved_contexts=contexts,
            knowledge_points=knowledge_points,
            session_plan=session_plans,
            sessions=sessions,
        )

    def _knowledge_points_from_contexts(self, contexts: list[KBSearchResult]) -> list[str]:
        points: list[str] = []
        seen: set[str] = set()
        for context in contexts:
            for token in self._candidate_points(context.content):
                if token in seen:
                    continue
                seen.add(token)
                points.append(token)
                if len(points) >= 12:
                    return points
        return points

    def _candidate_points(self, content: str) -> list[str]:
        import re

        return re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", content)

    def _slice_for_session(self, points: list[str], index: int, total_sessions: int) -> list[str]:
        if not points:
            return []
        bucket_size = max(1, len(points) // total_sessions)
        start = (index - 1) * bucket_size
        end = len(points) if index == total_sessions else start + bucket_size
        return points[start:end][:5]

    def _default_time_allocation(self, duration: int) -> list[TimeAllocation]:
        intro = max(5, duration // 9)
        practice = max(5, duration // 4)
        summary = 5
        lecture = duration - intro - practice - summary
        if lecture < 5:
            lecture = 5
            practice = max(1, duration - intro - lecture - summary)
        return [
            TimeAllocation(activity="导入与目标说明", minutes=intro),
            TimeAllocation(activity="核心概念讲解", minutes=lecture),
            TimeAllocation(activity="课堂练习与互动", minutes=practice),
            TimeAllocation(activity="总结与作业说明", minutes=summary),
        ]

    def _process_content(
        self,
        activity: str,
        session_points: list[str],
        contexts: list[KBSearchResult],
    ) -> str:
        context_preview = contexts[0].content[:120] if contexts else ""
        points = "、".join(session_points[:3])
        return f"{activity}: focus on {points}. Source context: {context_preview}"

    def _resolve_target_session(self, content: LessonDesignContent, target_scope: str) -> int:
        import re

        match = re.search(r"第?\s*(\d+)\s*(课时|节|session)?", target_scope, re.IGNORECASE)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(content.sessions):
                return index
        return 0

