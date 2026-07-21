from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from coursepilot.schemas.kb_schema import KBSearchResult


class LessonGenerationParams(BaseModel):
    """生成教学设计时传入的用户配置参数，对应PRD定义的输入项"""

    chapter_range: str = Field(min_length=1)  # 必填字段，表示要生成哪一章或哪一节的教学设计
    total_sessions: int = Field(default=2, ge=1, le=12)  # 必填字段，表示要生成的课时总数
    session_duration: int = Field(default=45, ge=15, le=240)  # 必填字段，表示每个课时的分钟数
    student_level: str | None = None  # 后续个性化设置预留接口
    student_background: str | None = None
    teaching_template: str = "standard"  # 指定模板
    teaching_focus: str | None = None  # 教师指定的重点
    include_interaction: bool = True  # 控制是否生成互动设计
    include_homework: bool = True  # 控制是否生成作业建议
    additional_requirements: str | None = None  # 保存额外要求


class Reference(BaseModel):
    """引用来源，指向 RAG chunk"""

    chunk_id: str
    source_type: str | None = None
    chapter: str | None = None
    page: int | None = None


class TimeAllocation(BaseModel):
    """某一个课时内的每个环节的时间分配"""

    activity: str = Field(min_length=1)
    minutes: int = Field(ge=1)


class TeachingProcessItem(BaseModel):
    """教学环节"""

    stage: str = Field(min_length=1)
    minutes: int = Field(ge=1)
    content: str = Field(min_length=1)


class SessionPlan(BaseModel):
    """一个课时的规划"""

    session_index: int = Field(ge=1)  # 第几课时
    session_title: str = Field(min_length=1)  # 本课时标题
    duration: int = Field(ge=1)  # 本课时总时长
    knowledge_points: list[str] = Field(min_length=1)  # 本课时覆盖的知识点
    teaching_focus: str = Field(min_length=1)  # 教师指定的重点
    difficulty_points: list[str] = Field(default_factory=list)  # 教学难点
    time_allocation: list[TimeAllocation] = Field(min_length=1)  # 课时分配，包含每个环节的时间分配

    # 验证时间分配总和是否等于课时总时长
    @model_validator(mode="after")
    def validate_time_sum(self):
        total_minutes = sum(item.minutes for item in self.time_allocation)
        if total_minutes != self.duration:
            raise ValueError("time_allocation minutes must equal duration")
        return self


class LessonSession(BaseModel):
    """每个课时的教学设计"""

    session_index: int = Field(ge=1)
    session_title: str = Field(min_length=1)
    teaching_objectives: list[str] = Field(min_length=1)
    key_points: list[str] = Field(min_length=1)
    difficult_points: list[str] = Field(default_factory=list)
    teaching_process: list[TeachingProcessItem] = Field(min_length=1)
    interaction_design: list[str] = Field(default_factory=list)
    blackboard_or_slide_suggestions: list[str] = Field(default_factory=list)
    homework_suggestion: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(min_length=1)


class LessonDesignContent(BaseModel):
    """每章课程完整教学设计 JSON，由每个课时的教学设计组成"""

    course_name: str  # 课程名称
    chapter: str  # 章节名称
    total_sessions: int  # 总课时数
    session_duration: int  # 每个课时的分钟数
    retrieved_contexts: list[KBSearchResult] = Field(
        default_factory=list
    )  # RAG 检索结果，方便追溯生成依据
    knowledge_points: list[str] = Field(default_factory=list)  # 从上下文提取出的知识点
    session_plan: list[SessionPlan]  # 课时规划
    sessions: list[LessonSession]  # 真正的教学设计内容


class LessonValidationReport(BaseModel):
    """校验报告"""

    schema_valid: bool = True  #  Pydantic schema 是否通过
    session_count_valid: bool  # 课时数量是否符合参数设置
    time_allocation_valid: bool  # 时间分配是否符合要求
    required_fields_valid: bool  # 必填内容是否存在
    knowledge_coverage_valid: bool  # 知识覆盖是否完整
    citation_valid: bool  # 引用是否完整
    errors: list[str] = Field(default_factory=list)
    repair_attempts: int = 0  # 修复次数

    # 所有检查均为 True 时，表示通过校验
    @property
    def passed(self) -> bool:
        return all(
            [
                self.schema_valid,
                self.session_count_valid,
                self.time_allocation_valid,
                self.required_fields_valid,
                self.knowledge_coverage_valid,
                self.citation_valid,
            ]
        )


class LessonDesignRead(BaseModel):
    """教学设计草稿记录"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    task_id: str
    chapter: str
    status: str
    total_sessions: int
    content_json: dict
    validation_report_json: dict
    created_at: datetime
    updated_at: datetime


class LessonGenerationResponse(BaseModel):
    """生成教学设计的响应"""

    lesson_id: str
    task_id: str
    status: str
    lesson_design: LessonDesignContent
    validation_report: LessonValidationReport


class LessonRevisionRequest(BaseModel):
    """局部修改教学设计的请求"""

    target_scope: str = Field(min_length=1)  # 目标范围，指定要修改的课时或环节
    feedback_text: str = Field(min_length=1)  # 用户反馈要修改的内容
    keep_unchanged_parts: bool = True


class LessonRevisionResponse(BaseModel):
    """局部修改教学设计的响应"""

    lesson_id: str
    modification_summary: str
    lesson_design: LessonDesignContent
    validation_report: LessonValidationReport


class ExportFileRead(BaseModel):
    """导出的 DOCX 文件记录"""

    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    task_id: str | None
    file_type: str
    file_name: str
    file_path: str
    file_role: str
    created_at: datetime
