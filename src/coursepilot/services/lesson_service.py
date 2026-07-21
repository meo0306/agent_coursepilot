"""
教学设计/教案生成 服务端

"""

from pathlib import Path
from typing import Any, cast

from sqlalchemy.orm import Session

from agents.coursepilot.graphs.lesson_graph import coursepilot_lesson_agent
from core.settings import settings
from coursepilot.exporters import LessonDocxExporter
from coursepilot.llm import collect_coursepilot_llm_metadata, generate_structured
from coursepilot.models import Course, ExportFile, LessonDesign
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.lesson_schema import (
    ExportFileRead,
    LessonDesignContent,
    LessonGenerationParams,
    LessonGenerationResponse,
    LessonRevisionRequest,
    LessonRevisionResponse,
    LessonValidationReport,
    TeachingProcessItem,
)
from coursepilot.services.async_task_service import (
    complete_execution_task,
    fail_execution_task,
    prepare_execution_task,
)
from coursepilot.services.file_naming import readable_export_filename
from coursepilot.services.graph_config import new_workflow_config, workflow_thread_id
from coursepilot.services.workflow_tracking import (
    finish_graph_invocation,
    merge_llm_metadata,
    start_graph_invocation,
)
from coursepilot.validators import LessonValidator


class LessonService:
    def __init__(self, session: Session):
        self.session = session
        self.validator = LessonValidator()

    def generate_lesson(
        self,
        course_id: str,
        params: LessonGenerationParams,
        *,
        task_id: str | None = None,
    ) -> LessonGenerationResponse:
        """核心服务：生成教学设计"""
        # 1. 绑定已有课程==检查课程是否存在
        course = self.session.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course not found: {course_id}")

        # 2. 创建生成任务记录
        task = prepare_execution_task(
            self.session,
            task_id=task_id,
            course_id=course_id,
            task_type="lesson_design",
            input_params=params.model_dump(mode="json"),
        )

        # 3. 执行任务：检索课程知识库上下文，生成教学设计
        config = new_workflow_config(namespace="lesson", course_id=course_id)
        thread_id = workflow_thread_id(config)
        # graph invoke 前先写 running 记录并 commit。
        # 如果 graph 启动后立刻失败，数据库里仍然能看到 thread_id。
        task.intermediate_outputs_json = start_graph_invocation(
            task_outputs=task.intermediate_outputs_json,
            namespace="lesson",
            thread_id=thread_id,
        )
        self.session.commit()
        collector = None
        try:
            # 执行 graph 时包一层 collector：
            with collect_coursepilot_llm_metadata(thread_id=thread_id) as collector:
                graph_input = cast(
                    Any,
                    {
                        "course_id": course_id,
                        "lesson_params": {
                            **params.model_dump(mode="json"),
                            "course_name": course.course_name,
                        },
                    },
                )
                result = coursepilot_lesson_agent.invoke(graph_input, config=config)
            contexts = [
                KBSearchResult.model_validate(item) for item in result.get("retrieved_contexts", [])
            ]
            # 后校验，用于兜底检查：如果没有检索到上下文，不允许生成教学设计
            if not contexts:
                raise ValueError(
                    "No course knowledge base context found. "
                    "Build course documents before generating a lesson design."
                )

            # 3.4 结构化教学设计和校验报告写入数据库
            lesson_design = LessonDesignContent.model_validate(result["lesson_design"])
            validation_report = LessonValidationReport.model_validate(result["validation_report"])
            lesson = LessonDesign(
                course_id=course_id,
                task_id=task.id,
                chapter=params.chapter_range,
                status="draft" if validation_report.passed else "needs_review",
                total_sessions=params.total_sessions,
                content_json=lesson_design.model_dump(mode="json"),
                validation_report_json=validation_report.model_dump(mode="json"),
            )
            # 更新任务状态，并把检索上下文保存到任务中，方便后续审核“生成依据是什么”
            task.status = "completed" if validation_report.passed else "needs_review"
            outputs = dict(task.intermediate_outputs_json or {})
            outputs.update(
                {
                    "retrieved_contexts": [c.model_dump(mode="json") for c in contexts],
                    "knowledge_points": result.get("knowledge_points", []),
                    "session_plan": result.get("session_plan", []),
                }
            )
            outputs = finish_graph_invocation(
                task_outputs=outputs,
                thread_id=thread_id,
                status="success",
            )
            task.intermediate_outputs_json = merge_llm_metadata(outputs, collector)
            task.validation_report_json = validation_report.model_dump(mode="json")
            self.session.add(lesson)
            self.session.flush()
            response = LessonGenerationResponse(
                lesson_id=lesson.id,
                task_id=task.id,
                status=lesson.status,
                lesson_design=lesson_design,
                validation_report=validation_report,
            )
            complete_execution_task(
                task,
                response,
                status="completed" if validation_report.passed else "needs_review",
            )
            self.session.commit()
            self.session.refresh(lesson)
            return response
        except Exception as exc:
            fail_execution_task(task, exc)
            outputs = finish_graph_invocation(
                task_outputs=task.intermediate_outputs_json,
                thread_id=thread_id,
                status="failed",
                error_message=str(exc),
                exc_info=exc,
            )
            if collector is not None:
                outputs = merge_llm_metadata(outputs, collector)
            task.intermediate_outputs_json = outputs
            self.session.commit()  # 如果报错，提交以往过程数据
            raise

    def get_lesson(self, lesson_id: str) -> LessonDesign | None:
        """读取已有教学设计"""
        return self.session.get(LessonDesign, lesson_id)

    def revise_lesson(
        self,
        lesson_id: str,
        request: LessonRevisionRequest,
    ) -> LessonRevisionResponse | None:
        """修改教学设计"""

        lesson = self.get_lesson(lesson_id)
        if lesson is None:
            return None
        # 从数据库 JSON 恢复成 Pydantic 对象
        content = LessonDesignContent.model_validate(lesson.content_json)
        # 调用 LLM 生成修订后的课程设计，如果失败则使用 deterministic fallback
        content = generate_structured(
            prompt_name="lesson/revise_lesson_design",
            output_schema=LessonDesignContent,
            payload={
                "lesson_design": content.model_dump(mode="json"),
                "target_scope": request.target_scope,
                "feedback_text": request.feedback_text,
                "keep_unchanged_parts": request.keep_unchanged_parts,
                "retrieved_contexts": [
                    item.model_dump(mode="json") for item in content.retrieved_contexts
                ],
            },
            fallback=lambda: self._revise_lesson_deterministically(content, request),
        )

        # 校验+上传数据库
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
            modification_summary=(
                f"Updated session {self._resolve_target_session(content, request.target_scope) + 1}: "
                f"{request.target_scope}"
            ),
            lesson_design=content,
            validation_report=report,
        )

    def _revise_lesson_deterministically(
        self,
        content: LessonDesignContent,
        request: LessonRevisionRequest,
    ) -> LessonDesignContent:
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
        return content

    def export_lesson_docx(self, lesson_id: str) -> ExportFileRead | None:
        """导出教学设计为 DOCX 文件"""
        # 读取教学设计记录
        lesson = self.get_lesson(lesson_id)
        if lesson is None:
            return None

        # 从数据库 JSON 恢复成 Pydantic 对象
        content = LessonDesignContent.model_validate(lesson.content_json)
        # 指定路径和文件名
        export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / lesson.course_id
        course = self.session.get(Course, lesson.course_id)
        file_name = readable_export_filename(
            course_name=course.course_name if course else content.course_name,
            topic=lesson.chapter,
            role="lesson_design",
            unique_id=lesson.id,
            extension="docx",
        )
        output_path = export_dir / file_name
        # 写入 DOCX 文件
        LessonDocxExporter().export(content, output_path)

        # 导出后新增一条文件记录
        # TODO: 后续历史文件页面或下载接口可以基于这张表扩展
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

    def _resolve_target_session(self, content: LessonDesignContent, target_scope: str) -> int:
        """正则匹配，找出目标课时的索引"""
        import re

        match = re.search(r"第?\s*(\d+)\s*(课时|节|session)?", target_scope, re.IGNORECASE)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(content.sessions):
                return index
        return 0
