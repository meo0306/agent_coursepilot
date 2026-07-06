from pathlib import Path

from sqlalchemy.orm import Session

from agents.coursepilot.graphs.ppt_graph import coursepilot_ppt_agent
from core.settings import settings
from coursepilot.exporters import PPTXExporter
from coursepilot.llm import collect_coursepilot_llm_metadata
from coursepilot.models import ExportFile, GenerationTask, LessonDesign, SlideOutline
from coursepilot.schemas.lesson_schema import LessonDesignContent
from coursepilot.schemas.ppt_schema import (
    PPTExportResponse,
    PPTGenerationParams,
    PPTGenerationResponse,
    SlideOutlineContent,
    SlideValidationReport,
)
from coursepilot.services.file_naming import readable_export_filename
from coursepilot.services.graph_config import new_workflow_config, workflow_thread_id
from coursepilot.services.workflow_tracking import (
    finish_graph_invocation,
    merge_llm_metadata,
    start_graph_invocation,
)
from coursepilot.validators import PPTValidator


class PPTService:
    def __init__(self, session: Session):
        self.session = session

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

        config = new_workflow_config(namespace="ppt", course_id=lesson.course_id)
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
                result = coursepilot_ppt_agent.invoke(
                    {
                        "course_id": lesson.course_id,
                        "ppt_params": {
                            **params.model_dump(mode="json"),
                            "lesson_id": lesson.id,
                        },
                        "lesson_design": lesson_content.model_dump(mode="json"),
                    },
                    config=config,
                )
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
            outputs = finish_graph_invocation(
                task_outputs=task.intermediate_outputs_json,
                thread_id=thread_id,
                status="failed",
                error_message=str(exc),
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
        # 校验 PPT 大纲是否符合要求，如果不符合则不允许导出
        validation_report = PPTValidator().validate(
            content,
            expected_slide_count=len(content.slides),
            total_sessions=lesson_content.total_sessions,
        )
        outline.validation_report_json = validation_report.model_dump(mode="json")
        if not validation_report.passed:
            outline.status = "needs_review"
            self.session.commit()
            raise ValueError("PPT outline validation failed before export")
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
