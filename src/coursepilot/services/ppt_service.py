from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.coursepilot.graphs.ppt_graph import coursepilot_ppt_agent
from core.settings import settings
from coursepilot.domain.task import WorkflowType
from coursepilot.exporters import PPTXExporter
from coursepilot.llm import collect_coursepilot_llm_metadata
from coursepilot.models import (
    ExportFile,
    KnowledgeChunk,
    LessonDesign,
    SlideOutline,
)
from coursepilot.runtime.legacy_adapter import LegacyRuntimeAdapter
from coursepilot.runtime.repository import RuntimeRepository
from coursepilot.schemas.lesson_schema import LessonDesignContent
from coursepilot.schemas.ppt_schema import (
    PPTExportResponse,
    PPTGenerationParams,
    PPTGenerationResponse,
    SlideOutlineContent,
    SlideValidationReport,
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
from coursepilot.validators import (
    PPTValidator,
    inherit_session_references,
    session_references,
)


class PPTService:
    def __init__(self, session: Session):
        self.session = session

    def generate_outline(
        self,
        lesson_id: str,
        params: PPTGenerationParams,
        *,
        task_id: str | None = None,
    ) -> PPTGenerationResponse | None:
        lesson = self.session.get(LessonDesign, lesson_id)
        if lesson is None:
            return None
        LegacyRuntimeAdapter.validate_template(WorkflowType.PPT, params.style_template)

        task = prepare_execution_task(
            self.session,
            task_id=task_id,
            course_id=lesson.course_id,
            task_type="ppt_outline",
            input_params=params.model_dump(mode="json"),
        )
        runtime = LegacyRuntimeAdapter(RuntimeRepository(self.session))
        runtime_run_id = runtime.begin(
            task=task,
            workflow_type=WorkflowType.PPT,
            legacy_template=params.style_template,
            input_payload=params.model_dump(mode="json"),
            request_id=f"legacy:{task.id}",
            trace_id=f"legacy:{task.id}:1",
        )

        config = new_workflow_config(namespace="ppt", course_id=lesson.course_id, task_id=task.id)
        thread_id = workflow_thread_id(config)
        task.intermediate_outputs_json = start_graph_invocation(
            task_outputs=task.intermediate_outputs_json,
            namespace="ppt",
            thread_id=thread_id,
        )
        self.session.commit()
        collector = None
        try:
            lesson_content = LessonDesignContent.model_validate(lesson.content_json)
            with collect_coursepilot_llm_metadata(thread_id=thread_id) as collector:
                graph_input = cast(
                    Any,
                    {
                        "course_id": lesson.course_id,
                        "ppt_params": {
                            **params.model_dump(mode="json"),
                            "lesson_id": lesson.id,
                        },
                        "lesson_design": lesson_content.model_dump(mode="json"),
                        "valid_chunk_ids": sorted(self._course_chunk_ids(lesson.course_id)),
                    },
                )
                result = coursepilot_ppt_agent.invoke(graph_input, config=config)
            outline_content = SlideOutlineContent.model_validate(result["slide_outline"])
            validation_report = SlideValidationReport.model_validate(result["validation_report"])
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
            outputs = finish_graph_invocation(
                task_outputs=task.intermediate_outputs_json,
                thread_id=thread_id,
                status="success",
            )
            task.intermediate_outputs_json = merge_llm_metadata(outputs, collector)
            self.session.add(outline)
            self.session.flush()
            response = PPTGenerationResponse(
                outline_id=outline.id,
                task_id=task.id,
                status=outline.status,
                outline=outline_content,
                validation_report=validation_report,
            )
            complete_execution_task(
                task,
                response,
                status="completed" if validation_report.passed else "needs_review",
            )
            runtime.complete(
                task=task,
                run_id=runtime_run_id,
                artifact_type="ppt_outline",
                content=response.model_dump(mode="json"),
                status="completed" if validation_report.passed else "needs_review",
                invocations=collector.invocations,
            )
            self.session.commit()
            self.session.refresh(outline)
            return response
        except Exception as exc:
            runtime.fail(runtime_run_id)
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
            self.session.commit()
            raise

    def get_outline(self, outline_id: str) -> SlideOutline | None:
        return self.session.get(SlideOutline, outline_id)

    def export_pptx(self, outline_id: str) -> PPTExportResponse | None:
        """根据 slide_outline 渲染 PPTX 文件，返回导出文件元数据"""
        outline = self.get_outline(outline_id)
        if outline is None:
            return None
        # 验证并加载 PPT 大纲内容
        content = SlideOutlineContent.model_validate(outline.outline_json)
        lesson = self.session.get(LessonDesign, outline.lesson_design_id)
        if lesson is None:
            raise ValueError("Lesson design not found for this PPT outline")
        lesson_content = LessonDesignContent.model_validate(lesson.content_json)
        content = inherit_session_references(content, lesson_content)
        references_by_session = session_references(lesson_content)
        # 校验 PPT 大纲是否符合要求，如果不符合则不允许导出
        validation_report = PPTValidator().validate(
            content,
            expected_slide_count=len(content.slides),
            total_sessions=lesson_content.total_sessions,
            valid_session_indices=set(references_by_session),
            valid_chunk_ids=self._course_chunk_ids(outline.course_id),
            session_reference_ids={
                session_index: {reference.chunk_id for reference in references}
                for session_index, references in references_by_session.items()
            },
        )
        outline.outline_json = content.model_dump(mode="json")
        outline.validation_report_json = validation_report.model_dump(mode="json")
        if not validation_report.passed:
            outline.status = "needs_review"
            self.session.commit()
            details = ", ".join(validation_report.errors)
            raise ValueError(f"PPT outline validation failed before export: {details}")
        if outline.status == "needs_review":
            outline.status = "draft"
        # 生成 PPTX 文件并保存到数据库
        export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / outline.course_id
        file_name = readable_export_filename(
            course_name=lesson_content.course_name,
            topic=content.chapter,
            role="ppt_outline",
            unique_id=outline.id,
            extension="pptx",
        )
        output_path = export_dir / file_name
        path = PPTXExporter().export(content, output_path)

        export_file = ExportFile(
            course_id=outline.course_id,
            task_id=outline.task_id,
            file_type="pptx",
            file_name=file_name,
            file_path=str(path),
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

    def _course_chunk_ids(self, course_id: str) -> set[str]:
        return set(
            self.session.scalars(
                select(KnowledgeChunk.id).where(KnowledgeChunk.course_id == course_id)
            ).all()
        )
