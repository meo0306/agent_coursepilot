from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from core.settings import settings
from coursepilot.exporters import ExamDocxExporter
from coursepilot.models import Course, ExamBlueprint, ExportFile, GenerationTask, Question
from coursepilot.schemas.exam_schema import (
    ExamBlueprintContent,
    ExamBlueprintResponse,
    ExamExportResponse,
    ExamGenerationParams,
    QuestionGenerationResponse,
    QuestionGroupPlan,
)
from coursepilot.schemas.kb_schema import KBSearchRequest, KBSearchResult
from coursepilot.schemas.lesson_schema import Reference
from coursepilot.schemas.question_schema import QuestionItem, QuestionRead, QuestionType
from coursepilot.services.kb_service import KnowledgeBaseService
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

        contexts = self._retrieve_contexts(course_id, params)
        if not contexts:
            raise ValueError(
                "No course knowledge base context found. Build course documents before generating an exam."
            )

        task = GenerationTask(
            course_id=course_id,
            task_type="generate_exam_blueprint",
            status="completed",
            input_params_json=params.model_dump(mode="json"),
            intermediate_outputs_json={"retrieved_contexts": [c.model_dump() for c in contexts]},
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        blueprint_content = self._build_blueprint(course, params, contexts)
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

        content = ExamBlueprintContent.model_validate(blueprint.blueprint_json)
        questions = self._generate_questions_from_blueprint(content)
        report = self.validator.validate(content, questions)

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
                    references_json=[ref.model_dump(mode="json") for ref in question.references],
                    status="draft" if report.passed else "needs_review",
                )
            )
        blueprint.status = "questions_generated" if report.passed else "needs_review"
        task = self.session.get(GenerationTask, blueprint.task_id)
        if task is not None:
            task.status = "completed" if report.passed else "needs_review"
            task.validation_report_json = report.model_dump(mode="json")
        self.session.commit()
        return QuestionGenerationResponse(
            blueprint_id=blueprint.id,
            status=blueprint.status,
            questions=questions,
            validation_report=report,
        )

    def list_questions(self, blueprint_id: str) -> list[QuestionRead] | None:
        if self.get_blueprint(blueprint_id) is None:
            return None
        stmt = select(Question).where(Question.exam_blueprint_id == blueprint_id).order_by(Question.created_at)
        return [QuestionRead.model_validate(question) for question in self.session.scalars(stmt)]

    def export_exam_files(self, blueprint_id: str) -> ExamExportResponse | None:
        blueprint = self.get_blueprint(blueprint_id)
        if blueprint is None:
            return None
        question_reads = self.list_questions(blueprint_id)
        if not question_reads:
            raise ValueError("No generated questions found for this blueprint")

        content = ExamBlueprintContent.model_validate(blueprint.blueprint_json)
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
            file_name = f"{blueprint.id}_{suffix}"
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

    def _retrieve_contexts(
        self,
        course_id: str,
        params: ExamGenerationParams,
    ) -> list[KBSearchResult]:
        results = KnowledgeBaseService(self.session).search(
            course_id,
            KBSearchRequest(query=params.chapter_range, top_k=8),
        )
        return results

    def _build_blueprint(
        self,
        course: Course,
        params: ExamGenerationParams,
        contexts: list[KBSearchResult],
    ) -> ExamBlueprintContent:
        knowledge_points = self._knowledge_points_from_contexts(contexts)
        groups: list[QuestionGroupPlan] = []
        for question_type, count in params.question_counts.items():
            if count <= 0:
                continue
            score_each = params.score_per_question[question_type]
            groups.append(
                QuestionGroupPlan(
                    question_type=question_type,
                    count=count,
                    score_each=score_each,
                    total_score=count * score_each,
                    knowledge_points=knowledge_points[: max(1, min(len(knowledge_points), count))],
                    difficulty=self._dominant_difficulty(params.difficulty_distribution),
                )
            )
        total_score = params.total_score or sum(group.total_score for group in groups)
        if params.total_score and total_score != sum(group.total_score for group in groups):
            total_score = sum(group.total_score for group in groups)
        return ExamBlueprintContent(
            course_name=course.course_name,
            chapter_range=params.chapter_range,
            generation_type=params.generation_type,
            total_score=total_score,
            question_groups=groups,
            retrieved_contexts=contexts,
            knowledge_points=knowledge_points,
        )

    def _generate_questions_from_blueprint(self, blueprint: ExamBlueprintContent) -> list[QuestionItem]:
        questions: list[QuestionItem] = []
        references = self._references_from_contexts(blueprint.retrieved_contexts)
        for group in blueprint.question_groups:
            for index in range(1, group.count + 1):
                point = group.knowledge_points[(index - 1) % len(group.knowledge_points)] if group.knowledge_points else blueprint.chapter_range
                reference = references[(len(questions)) % len(references)]
                questions.append(
                    self._make_question(
                        question_type=group.question_type,
                        index=index,
                        point=point,
                        difficulty=group.difficulty,
                        score=group.score_each,
                        reference=reference,
                    )
                )
        return questions

    def _make_question(
        self,
        *,
        question_type: QuestionType,
        index: int,
        point: str,
        difficulty: str,
        score: int,
        reference: Reference,
    ) -> QuestionItem:
        stem = f"关于“{point}”的第 {index} 题"
        if question_type == "single_choice":
            return QuestionItem(
                question_type=question_type,
                knowledge_point=point,
                difficulty=difficulty,
                score=score,
                question_text=f"{stem}：以下哪一项最符合该知识点？",
                options={"A": f"{point} 的核心含义", "B": "无关概念", "C": "随机猜测", "D": "错误表述"},
                correct_answer="A",
                explanation=f"根据课程资料，{point} 是本题考查的核心知识点。",
                references=[reference],
            )
        if question_type == "multiple_choice":
            return QuestionItem(
                question_type=question_type,
                knowledge_point=point,
                difficulty=difficulty,
                score=score,
                question_text=f"{stem}：下列哪些说法与该知识点相关？",
                options={"A": f"理解 {point}", "B": f"应用 {point}", "C": "完全无关", "D": "明显错误"},
                correct_answer="A,B",
                explanation=f"A 和 B 分别覆盖 {point} 的理解与应用。",
                references=[reference],
            )
        if question_type == "judgement":
            return QuestionItem(
                question_type=question_type,
                knowledge_point=point,
                difficulty=difficulty,
                score=score,
                question_text=f"{stem}：{point} 可以结合课程资料中的案例进行分析。",
                correct_answer="正确",
                explanation=f"课程资料提供了与 {point} 相关的上下文，可用于分析。",
                references=[reference],
            )
        return QuestionItem(
            question_type=question_type,
            knowledge_point=point,
            difficulty=difficulty,
            score=score,
            question_text=f"{stem}：请简述该知识点的含义，并结合一个课程案例说明。",
            correct_answer=f"应说明 {point} 的定义、适用场景和课程案例。",
            explanation=f"答案需要覆盖概念解释、应用场景和基于资料的案例。",
            references=[reference],
        )

    def _references_from_contexts(self, contexts: list[KBSearchResult]) -> list[Reference]:
        return [
            Reference(
                chunk_id=context.chunk_id,
                source_type=context.source_type,
                chapter=context.chapter,
                page=context.page,
            )
            for context in contexts
        ] or [Reference(chunk_id="manual-context")]

    def _knowledge_points_from_contexts(self, contexts: list[KBSearchResult]) -> list[str]:
        import re

        points: list[str] = []
        seen: set[str] = set()
        for context in contexts:
            for token in re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", context.content):
                if token in seen:
                    continue
                seen.add(token)
                points.append(token)
                if len(points) >= 20:
                    return points
        return points

    def _dominant_difficulty(self, distribution: dict[str, float]) -> str:
        if not distribution:
            return "medium"
        return max(distribution.items(), key=lambda item: item[1])[0]

