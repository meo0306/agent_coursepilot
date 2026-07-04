"""
教学设计/教案生成 服务端
"""
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
        """核心服务：生成教学设计"""
        # 1. 绑定已有课程==检查课程是否存在
        course = self.session.get(Course, course_id)
        if course is None:
            raise ValueError(f"Course not found: {course_id}")

        # 2. 创建生成任务记录
        task = GenerationTask(
            course_id=course_id,
            task_type="lesson_design",  # 生成任务类型
            status="running",   # 生成任务初始状态是running
            input_params_json=params.model_dump(),
        )
        # 保存任务记录到数据库
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)

        # 3. 执行任务：检索课程知识库上下文，生成教学设计
        try:
            # 3.1 检索课程知识库上下文
            # 拿到检索结果做上下文
            contexts = self._retrieve_contexts(course_id, params)
            # 如果没有检索到上下文，不允许生成教学设计
            if not contexts:
                raise ValueError(
                    "No course knowledge base context found. Build course documents before generating a lesson design."
                )
            # 3.2 基于检索结果组装结构化教学设计
            lesson_design = self._build_lesson_design(course, params, contexts)
            
            # 3.3 校验
            validation_report = self.validator.validate(
                lesson_design,
                expected_sessions=params.total_sessions,
                session_duration=params.session_duration,
            )
            # 3.4 结构化教学设计和校验报告写入数据库
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
            task.intermediate_outputs_json = {"retrieved_contexts": [c.model_dump() for c in contexts]}
            task.validation_report_json = validation_report.model_dump(mode="json")
            # 保存教学设计记录到数据库
            self.session.add(lesson)
            self.session.commit()
            self.session.refresh(lesson)
            # 3.7 返回响应体
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
            self.session.commit()   # 如果报错，提交以往过程数据
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
        # 获取指定课时的索引和内容
        target_index = self._resolve_target_session(content, request.target_scope)
        target_session = content.sessions[target_index]
        note = f"Revision for {request.target_scope}: {request.feedback_text}"

        # 修改主逻辑
        # TODO：后续替换为 ReAct-style revise node
        if request.keep_unchanged_parts:
            target_session.interaction_design.append(note)
        else:
            target_session.teaching_process.append(
                TeachingProcessItem(stage="Revision", minutes=5, content=note)
            )
        target_session.blackboard_or_slide_suggestions.append(
            f"Update emphasis according to teacher feedback: {request.feedback_text}"
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
            modification_summary=f"Updated session {target_session.session_index}: {request.target_scope}",
            lesson_design=content,
            validation_report=report,
        )

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
        file_name = f"lesson_design_{lesson.id}.docx"
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

    def _retrieve_contexts(
        self,
        course_id: str,
        params: LessonGenerationParams,
    ) -> list[KBSearchResult]:
        # 检索条件：章节范围、教学重点
        queries = [params.chapter_range]
        if params.teaching_focus:
            queries.append(params.teaching_focus)
        # 预定义返回结果列表和去重集合
        results: list[KBSearchResult] = []
        seen: set[str] = set()
        # 执行检索，返回前8个去重后的结果
        kb_service = KnowledgeBaseService(self.session)
        for query in queries:
            for result in kb_service.search(
                course_id,
                KBSearchRequest(query=query, top_k=5),
            ):
                # 跳过重复结果
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
        """核心：基于检索结果组装结构化教学设计"""
        # 1. 从 RAG 检索内容中提取知识点
        knowledge_points = self._knowledge_points_from_contexts(contexts)
        # 2. 将检索结果转换为待引用的对象列表
        references = [
            Reference(
                chunk_id=context.chunk_id,
                source_type=context.source_type,
                chapter=context.chapter,
                page=context.page,
            )
            for context in contexts[: max(1, min(len(contexts), params.total_sessions))]    # 在检索到的相关资料切片数和课时数中取小，至少尝试取 1 条引用
        ]
        # 3. 生成session_plans 和 sessions
        session_plans: list[SessionPlan] = []
        sessions = []
        # 逐课时
        for index in range(1, params.total_sessions + 1):
            # 分配知识点给每个课时
            session_points = self._slice_for_session(knowledge_points, index, params.total_sessions)
            if not session_points:
                # 如果没有足够的知识点，使用章节范围作为默认知识点
                session_points = knowledge_points[:3] or [params.chapter_range]
            
            # 分配引用
            reference = references[(index - 1) % len(references)]   # 用了取模%，意思是：如果课时数多于引用数，就循环复用引用
            
            # 分配时间
            allocation = self._default_time_allocation(params.session_duration)
            
            # 确定课时标题焦点，取session_points的第一个知识点（认为是重点），如果没有知识点，就用章节范围作为标题焦点
            title_focus = session_points[0] if session_points else params.chapter_range
            
            # 为每个课时生成结构化计划
            session_plans.append(
                SessionPlan(
                    session_index=index,
                    session_title=f"{params.chapter_range} - {title_focus}",
                    duration=params.session_duration,
                    knowledge_points=session_points,
                    teaching_focus=params.teaching_focus or f"Understand and apply {title_focus}",  # 如果没有教学重点，就用标题焦点作为默认教学重点
                    difficulty_points=session_points[-2:],  # 取最后两个知识点作为难点
                    time_allocation=allocation,
                )
            )
            # 为每个课时生成完整教学设计
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
        # 4. 返回完整教学设计内容
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
        """提取多段contexts的知识点"""
        points: list[str] = []
        seen: set[str] = set()
        # 扫描内容，提取去重后的知识点
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
        """正则匹配从一段文本中获取关键词/知识点，匹配规则是：中文或英文开头，后续可以包含中文、英文、数字、下划线或短横线，长度在3-20之间的字符串"""
        import re

        return re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", content)

    def _slice_for_session(self, points: list[str], index: int, total_sessions: int) -> list[str]:
        """把知识点切分到不同课时"""
        # 没有知识点就不分配
        if not points:
            return []
        # 每个课时分配的知识点数量，至少为1
        bucket_size = max(1, len(points) // total_sessions)
        # 计算当前课时的切片范围
        start = (index - 1) * bucket_size
        end = len(points) if index == total_sessions else start + bucket_size
        return points[start:end][:5]    # 读取切片，每个课时最多分配5个知识点

    def _default_time_allocation(self, duration: int) -> list[TimeAllocation]:
        # 生成默认时间分配方案，按比例分配给导入、讲解、练习和总结
        intro = max(5, duration // 9)
        practice = max(5, duration // 4)
        summary = 5
        lecture = duration - intro - practice - summary
        # 如果讲解时间太短，调整练习时间
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
        """ 正则匹配，找出目标课时的索引 """
        import re

        match = re.search(r"第?\s*(\d+)\s*(课时|节|session)?", target_scope, re.IGNORECASE)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(content.sessions):
                return index
        return 0

