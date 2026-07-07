from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from agents.coursepilot.graphs.exam_graph import coursepilot_exam_agent
from core.settings import settings
from coursepilot.exporters import ExamDocxExporter
from coursepilot.llm import collect_coursepilot_llm_metadata
from coursepilot.models import Course, ExamBlueprint, ExportFile, GenerationTask, Question
from coursepilot.schemas.exam_schema import (
    ExamBlueprintContent,
    ExamBlueprintResponse,
    ExamExportResponse,
    ExamGenerationParams,
    ExamValidationReport,
    QuestionGenerationResponse,
)
from coursepilot.schemas.kb_schema import KBSearchResult
from coursepilot.schemas.lesson_schema import Reference
from coursepilot.schemas.question_schema import QuestionItem, QuestionRead
from coursepilot.services.file_naming import readable_export_filename
from coursepilot.services.graph_config import new_workflow_config, workflow_thread_id
from coursepilot.services.workflow_tracking import (
    finish_graph_invocation,
    merge_llm_metadata,
    start_graph_invocation,
)
from coursepilot.validators import QuestionValidator


class ExamService:
    def __init__(self, session: Session):
        self.session = session
        self.validator = QuestionValidator(settings.COURSEPILOT_DUPLICATE_THRESHOLD)

    def create_blueprint(
        self,
        course_id: str,
        params: ExamGenerationParams,
    ) -> ExamBlueprintResponse:
        course = self.session.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course not found: {course_id}")

        task = GenerationTask(
            course_id=course_id,
            task_type="generate_exam_blueprint",
            status="running",
            input_params_json=params.model_dump(mode="json"),
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        config = new_workflow_config(namespace="exam-blueprint", course_id=course_id)
        thread_id = workflow_thread_id(config)
        task.intermediate_outputs_json = start_graph_invocation(
            task_outputs=task.intermediate_outputs_json,
            namespace="exam-blueprint",
            thread_id=thread_id,
        )
        self.session.commit()

        collector = None
        try:
            with collect_coursepilot_llm_metadata(thread_id=thread_id) as collector:
                result = coursepilot_exam_agent.invoke(
                    {
                        "course_id": course_id,
                        "workflow_phase": "blueprint",
                        "exam_params": {
                            **params.model_dump(mode="json"),
                            "course_name": course.course_name,
                        },
                    },
                    config=config,
                )
            contexts = [
                KBSearchResult.model_validate(item)
                for item in result.get("retrieved_contexts", [])
            ]
            if not contexts:
                raise ValueError(
                    "No course knowledge base context found. "
                    "Build course documents before generating an exam."
                )
            blueprint_content = ExamBlueprintContent.model_validate(result["exam_blueprint"])
            outputs = dict(task.intermediate_outputs_json or {})
            outputs.update(
                {
                    "retrieved_contexts": [c.model_dump(mode="json") for c in contexts],
                    "knowledge_points": blueprint_content.knowledge_points,
                }
            )
            outputs = finish_graph_invocation(
                task_outputs=outputs,
                thread_id=thread_id,
                status="success",
            )
            task.status = "completed"
            task.intermediate_outputs_json = merge_llm_metadata(outputs, collector)

            blueprint = ExamBlueprint(
                course_id=course_id,
                task_id=task.id,
                chapter_range=params.chapter_range,
                status="draft",
                blueprint_json=blueprint_content.model_dump(mode="json"),
            )
            self.session.add(blueprint)
            self.session.commit()
            self.session.refresh(blueprint)

            return ExamBlueprintResponse(
                blueprint_id=blueprint.id,
                task_id=task.id,
                status=blueprint.status,
                blueprint=blueprint_content,
            )
        except Exception as exc:
            task.status = "failed"
            task.error_message = str(exc)
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

    def confirm_blueprint(self, blueprint_id: str) -> ExamBlueprint | None:
        blueprint = self.session.get(ExamBlueprint, blueprint_id)
        if blueprint is None:
            return None
        blueprint.status = "confirmed"
        self.session.commit()
        self.session.refresh(blueprint)
        return blueprint

    def get_blueprint(self, blueprint_id: str) -> ExamBlueprint | None:
        return self.session.get(ExamBlueprint, blueprint_id)

    def generate_questions(self, blueprint_id: str) -> QuestionGenerationResponse | None:
        blueprint = self.get_blueprint(blueprint_id)
        if blueprint is None:
            return None
        if blueprint.status != "confirmed":
            raise BlueprintNotConfirmedError(
                "Exam blueprint must be confirmed before generating questions"
            )

        content = ExamBlueprintContent.model_validate(blueprint.blueprint_json)
        course = self.session.get(Course, blueprint.course_id)
        config = new_workflow_config(namespace="exam-questions", course_id=blueprint.course_id)
        thread_id = workflow_thread_id(config)
        task = self.session.get(GenerationTask, blueprint.task_id)
        if task is not None:
            task.intermediate_outputs_json = start_graph_invocation(
                task_outputs=task.intermediate_outputs_json,
                namespace="exam-questions",
                thread_id=thread_id,
            )
            self.session.commit()

        collector = None
        try:
            with collect_coursepilot_llm_metadata(thread_id=thread_id) as collector:
                result = coursepilot_exam_agent.invoke(
                    {
                        "course_id": blueprint.course_id,
                        "blueprint_id": blueprint.id,
                        "workflow_phase": "questions",
                        "exam_blueprint": content.model_dump(mode="json"),
                    },
                    config=config,
                )
            questions = [QuestionItem.model_validate(item) for item in result.get("questions", [])]
            report = ExamValidationReport.model_validate(result["validation_report"])

            self.session.execute(delete(Question).where(Question.exam_blueprint_id == blueprint.id))
            for question in questions:
                self.session.add(
                    Question(
                        course_id=blueprint.course_id,
                        exam_blueprint_id=blueprint.id,
                        question_type=question.question_type,
                        knowledge_point=question.knowledge_point,
                        difficulty=question.difficulty,
                        score=question.score,
                        question_text=question.question_text,
                        options_json=question.options,
                        correct_answer=question.correct_answer,
                        explanation=question.explanation,
                        references_json=[
                            ref.model_dump(mode="json") for ref in question.references
                        ],
                        status="draft" if report.passed else "needs_review",
                    )
                )
            blueprint.status = "questions_generated" if report.passed else "needs_review"
            if task is not None:
                outputs = finish_graph_invocation(
                    task_outputs=task.intermediate_outputs_json,
                    thread_id=thread_id,
                    status="success",
                )
                task.status = "completed" if report.passed else "needs_review"
                task.validation_report_json = report.model_dump(mode="json")
                task.intermediate_outputs_json = merge_llm_metadata(outputs, collector)
            self.session.commit()
            return QuestionGenerationResponse(
                blueprint_id=blueprint.id,
                status=blueprint.status,
                questions=questions,
                validation_report=report,
            )
        except Exception as exc:
            if task is not None:
                task.status = "failed"
                task.error_message = str(exc)
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

    def list_questions(self, blueprint_id: str) -> list[QuestionRead] | None:
        if self.get_blueprint(blueprint_id) is None:
            return None
        stmt = (
            select(Question)
            .where(Question.exam_blueprint_id == blueprint_id)
            .order_by(Question.created_at)
        )
        return [QuestionRead.model_validate(question) for question in self.session.scalars(stmt)]

    def export_exam_files(self, blueprint_id: str) -> ExamExportResponse | None:
        blueprint = self.get_blueprint(blueprint_id)
        if blueprint is None:
            return None
        question_reads = self.list_questions(blueprint_id)
        if not question_reads:
            raise ValueError("No generated questions found for this blueprint")

        content = ExamBlueprintContent.model_validate(blueprint.blueprint_json)
        course = self.session.get(Course, blueprint.course_id)
        questions = [
            QuestionItem(
                question_type=question.question_type,
                knowledge_point=question.knowledge_point,
                difficulty=question.difficulty,
                score=question.score,
                question_text=question.question_text,
                options=question.options_json,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                references=[Reference.model_validate(ref) for ref in question.references_json],
            )
            for question in question_reads
        ]
        export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / blueprint.course_id
        exporter = ExamDocxExporter()
        outputs = [
            ("student_exam", "student_exam.docx", exporter.export_student_exam),
            ("teacher_answer", "teacher_answer.docx", exporter.export_teacher_answer),
            ("detailed_explanation", "detailed_explanation.docx", exporter.export_explanation),
            ("answer_sheet", "answer_sheet.docx", exporter.export_answer_sheet),
        ]
        files: list[dict] = []
        for role, suffix, export_func in outputs:
            file_name = readable_export_filename(
                course_name=course.course_name if course else content.course_name,
                topic=content.chapter_range,
                role=role,
                unique_id=blueprint.id,
                extension=suffix.rsplit(".", 1)[-1],
            )
            path = export_func(content, questions, export_dir / file_name)
            export_file = ExportFile(
                course_id=blueprint.course_id,
                task_id=blueprint.task_id,
                file_type="docx",
                file_name=file_name,
                file_path=str(path),
                file_role=role,
            )
            self.session.add(export_file)
            self.session.flush()
            files.append(
                {
                    "id": export_file.id,
                    "file_type": export_file.file_type,
                    "file_name": export_file.file_name,
                    "file_path": export_file.file_path,
                    "file_role": export_file.file_role,
                }
            )
        self.session.commit()
        return ExamExportResponse(blueprint_id=blueprint.id, files=files)


class BlueprintNotConfirmedError(ValueError):
    pass
