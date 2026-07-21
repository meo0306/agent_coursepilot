# CoursePilot Phase 2 审核说明 v0.1

本文档用于解释 Phase 2 做了什么、为什么这样做、相关代码在哪里、每段新增代码大致承担什么职责，以及你应该如何运行命令来验收。

对照文件：
- `PLAN.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

参考文档：
- `CoursePilot_markdown_docs/phase_audit/CoursePilot_Phase0_Audit_v0.1.md`
- `CoursePilot_markdown_docs/phase_audit/CoursePilot_Phase1_Audit_v0.1.md`

## 1. Phase 2 的目标

Phase 2 的目标是“教学设计 Agent”。

换成新手更容易理解的话，就是在 Phase 1 已经跑通“课程资料入库和 RAG 检索”的基础上，继续完成下面这条链路：

```text
课程知识库
  -> 检索相关资料
  -> 提取知识点
  -> 规划课时
  -> 生成结构化教学设计 JSON
  -> 校验教学设计质量
  -> 保存教学设计草稿
  -> 支持局部修改
  -> 导出 Word DOCX 文件
```

PRD 中对应的是：
- FR-005 教学设计参数配置
- FR-006 检索课程资料并生成教学设计
- FR-007 教学设计结构化输出
- FR-008 教学设计校验
- FR-009 教学设计局部修改
- FR-010 教学设计导出

技术架构中对应的是：
- 新增 Lesson schema
- 新增 LessonPlanningGraph
- 注册 `coursepilot-lesson-agent`
- 新增 Lesson API
- 新增 Lesson validator
- 新增 DOCX exporter
- UI 增加教学设计生成和导出入口

当前实现采取的是 MVP 做法：先不用真实 LLM 生成完整教案，而是用 RAG 检索结果和规则化逻辑生成一个结构化教学设计草稿。这样可以先验证“RAG -> schema -> validator -> 数据库存储 -> DOCX 导出”的工程链路，后续再把生成节点替换成真实 LLM prompt。

## 2. Phase 2 任务对照

| PLAN 任务 | 目标 | 当前实现位置 | 状态 |
|---|---|---|---|
| T2-001 Lesson Schema | 定义教学设计参数、课时计划、引用、校验报告等 schema | `src/coursepilot/schemas/lesson_schema.py` | 已实现 |
| T2-002 LessonPlanningGraph | 实现教学设计 workflow 节点和 graph | `src/agents/coursepilot/graphs/lesson_graph.py`, `src/agents/coursepilot/nodes/`, `src/agents/coursepilot/states/lesson_state.py` | 已实现轻量版 |
| T2-003 注册 Lesson Agent | `/info` 能看到 `coursepilot-lesson-agent` | `src/agents/agents.py` | 已实现 |
| T2-004 Lesson API | 生成、读取、局部修改、导出教学设计 | `src/coursepilot/api/routes_lessons.py`, `src/coursepilot/services/lesson_service.py` | 已实现 |
| T2-005 Lesson Validator 和 Repair | 校验课时、时间、必填项、知识点、引用；repair 最多 2 轮 | `src/coursepilot/validators/lesson_validator.py`, `src/agents/coursepilot/nodes/repair_nodes.py` | 已实现基础校验和轻量 repair 计数 |
| T2-006 教学设计页面 | UI 中生成教学设计和导出 DOCX | `src/coursepilot/ui/knowledge_base_page.py` | 已实现基础入口 |

需要特别说明：
- PLAN 里提到的 `prompts/lesson/*.md` 和 `prompts/repair/fix_json.md` 当前没有形成完整 prompt 文件链路。
- 当前 `LessonService` 生成教学设计时没有调用真实 LLM，而是基于检索结果自动组装结构化 JSON。
- 当前局部修改是轻量实现：把教师反馈追加进目标课时的 interaction 或 process 中，不是完整 ReAct-style 重新检索替换。
- 当前 graph 中的 `reflect_and_revise` 只记录 `repair_attempts`，没有真正重写教学设计内容。

这些不是测试失败，而是当前 Phase 2 MVP 的实现边界。

## 3. 新增了哪些文件

### 3.1 教学设计业务表模型

新增：
- `src/coursepilot/models/task.py`
- `src/coursepilot/models/lesson.py`
- `src/coursepilot/models/export_file.py`

动机：

Phase 1 只保存课程、文档和知识库 chunk。Phase 2 开始有“生成任务”和“生成结果”，所以需要新增三类数据：

```text
coursepilot_generation_tasks    保存生成任务状态和中间结果
coursepilot_lesson_designs      保存教学设计草稿 JSON
coursepilot_export_files        保存导出的 DOCX 文件记录
```

这样做的好处：
- 可以知道一次生成任务是 running、completed、needs_review 还是 failed。
- 可以保存 RAG 检索到的上下文和 validator 报告。
- 可以追踪某个 DOCX 文件来自哪个课程、哪个任务。

### 3.2 教学设计 Schema

新增：
- `src/coursepilot/schemas/lesson_schema.py`

动机：

PRD 和技术架构都要求核心生成结果必须是结构化 JSON，并经过 schema 校验。这个文件定义了教学设计的所有输入和输出结构，例如：

- `LessonGenerationParams`：生成教学设计时用户传入的参数。
- `Reference`：引用来源，指向 RAG chunk。
- `SessionPlan`：每个课时的规划。
- `LessonSession`：每个课时的完整教学设计。
- `LessonDesignContent`：完整教学设计 JSON。
- `LessonValidationReport`：校验报告。
- `LessonGenerationResponse`：生成接口返回结构。
- `LessonRevisionRequest` / `LessonRevisionResponse`：局部修改接口结构。
- `ExportFileRead`：导出文件记录结构。

### 3.3 教学设计 Service 和 API

新增：
- `src/coursepilot/services/lesson_service.py`
- `src/coursepilot/api/routes_lessons.py`

修改：
- `src/coursepilot/api/router.py`

动机：

Phase 2 需要产品流程 API，而不是只走聊天式 Agent invoke。新增接口统一挂载在：

```text
/api/coursepilot/*
```

核心接口是：

```text
POST /api/coursepilot/courses/{course_id}/lessons/generate
GET  /api/coursepilot/lessons/{lesson_id}
POST /api/coursepilot/lessons/{lesson_id}/revise
POST /api/coursepilot/lessons/{lesson_id}/export
```

### 3.4 教学设计校验器

新增：
- `src/coursepilot/validators/lesson_validator.py`

修改：
- `src/coursepilot/validators/__init__.py`

动机：

LLM 或规则生成出来的教学设计不能直接当作可信结果，需要检查：
- 课时数量是否正确。
- 每个课时的时间分配是否等于用户要求的时长。
- 目标、重点、教学过程等必填字段是否存在。
- 是否覆盖了知识点。
- 是否带有引用。

### 3.5 DOCX 导出器

新增：
- `src/coursepilot/exporters/lesson_docx_exporter.py`

修改：
- `src/coursepilot/exporters/__init__.py`

动机：

技术架构要求：LLM 不直接生成 Word 文件，而是先生成结构化 JSON，再由 exporter 渲染为 `.docx`。这样做有两个好处：
- 生成内容可以先被 Pydantic 和 validator 检查。
- 文件导出逻辑可测试、可替换、可复用。

### 3.6 CoursePilot Lesson Graph

新增：
- `src/agents/coursepilot/states/lesson_state.py`
- `src/agents/coursepilot/nodes/retrieve_nodes.py`
- `src/agents/coursepilot/nodes/lesson_nodes.py`
- `src/agents/coursepilot/nodes/validation_nodes.py`
- `src/agents/coursepilot/nodes/repair_nodes.py`
- `src/agents/coursepilot/graphs/lesson_graph.py`

动机：

技术架构要求 CoursePilot Agent workflow 放在 `src/agents/coursepilot/`，业务 API 和模型放在 `src/coursepilot/`。这样可以把“Agent 编排”和“业务数据/服务”分开。

当前 graph 支持两种入口：
- 没有 `lesson_params` 时，作为聊天式 agent 返回提示。
- 有 `lesson_params` 时，执行结构化 workflow。

### 3.7 Agent 注册

修改：
- `src/agents/agents.py`

新增注册：

```python
"coursepilot-lesson-agent": Agent(
    description="CoursePilot lesson planning agent with structured lesson workflow.",
    graph_like=coursepilot_lesson_agent,
)
```

动机：

这让原 AST 的 `/info` 可以看到 CoursePilot lesson agent，也让 `/coursepilot-lesson-agent/invoke` 有调试入口。

### 3.8 数据库迁移

新增：
- `alembic/versions/2026_06_22_0003-create_lesson_tables.py`

动机：

Phase 2 需要三张新表：
- `coursepilot_generation_tasks`
- `coursepilot_lesson_designs`
- `coursepilot_export_files`

这个迁移的 `down_revision` 是 `0002_create_phase1_tables`，说明它建立在 Phase 1 的课程和知识库表之上。

### 3.9 Streamlit 页面扩展

修改：
- `src/coursepilot/ui/knowledge_base_page.py`

动机：

为了让用户可以从一个页面走完：

```text
创建课程 -> 上传资料 -> 构建知识库 -> 检索 -> 生成教学设计 -> 导出 DOCX
```

当前页面新增了：
- `Generate lesson design` 表单。
- `Lesson ID` 输入框。
- `Export lesson DOCX` 按钮。

### 3.10 测试

新增：
- `tests/coursepilot/test_lesson_graph.py`
- `tests/coursepilot/test_lesson_api.py`
- `tests/coursepilot/test_validators.py`
- `tests/coursepilot/test_exporters.py`

动机：

这些测试分别验证：
- lesson graph 聊天入口和结构化 workflow。
- lesson API 生成、读取、修改、导出。
- validator 能通过有效教学设计。
- exporter 能写出可打开的 DOCX。

## 4. 修改了哪些已有文件

### 4.1 `src/agents/agents.py`

修改内容：

```python
from agents.coursepilot.graphs.lesson_graph import coursepilot_lesson_agent
...
"coursepilot-lesson-agent": Agent(
    description="CoursePilot lesson planning agent with structured lesson workflow.",
    graph_like=coursepilot_lesson_agent,
)
```

注释式理解：
- 第一行导入 CoursePilot lesson graph。
- registry 里新增 `coursepilot-lesson-agent`。
- 原有 agents 没有删除，符合 PLAN 里“只新增 CoursePilot agents，不删除原 agents”的边界。
- `/info` 会通过 `get_all_agent_info()` 返回这个 agent。

### 4.2 `src/coursepilot/api/router.py`

修改内容：

```python
from coursepilot.api.routes_lessons import router as lessons_router
...
api_router.include_router(lessons_router)
```

注释式理解：
- 把 lesson API 加入 `/api/coursepilot` 总路由。
- 最终路径会变成 `/api/coursepilot/courses/{course_id}/lessons/generate` 等。
- 它复用 Phase 1 已经挂载到主 FastAPI app 的 CoursePilot router。

### 4.3 `src/coursepilot/models/__init__.py`

修改内容：

```python
from coursepilot.models.export_file import ExportFile
from coursepilot.models.lesson import LessonDesign
from coursepilot.models.task import GenerationTask
```

注释式理解：
- 确保 Alembic 和 SQLAlchemy 可以发现 Phase 2 新增表模型。
- 如果这里不导入，`Base.metadata` 可能无法注册这些表。

### 4.4 `src/coursepilot/schemas/__init__.py`

修改内容：

```python
from coursepilot.schemas.lesson_schema import (...)
```

注释式理解：
- 统一导出 lesson 相关 schema。
- 后续其他模块可以从 `coursepilot.schemas` 统一导入。

### 4.5 `src/coursepilot/services/__init__.py`

修改内容：

```python
from coursepilot.services.lesson_service import LessonService
```

注释式理解：
- 统一导出 LessonService。
- 保持 CoursePilot service 层入口一致。

### 4.6 `src/coursepilot/ui/knowledge_base_page.py`

新增教学设计生成区块：

```python
st.subheader("Generate lesson design")
with st.form("generate_lesson"):
    chapter_range = st.text_input("Chapter range", ...)
    total_sessions = st.number_input(...)
    session_duration = st.number_input(...)
    ...
```

注释式理解：
- 让用户从 UI 填写章节、课时数、课时时长、教学模板等参数。
- 点击按钮后调用 lesson generate API。

新增导出区块：

```python
lesson_id = st.text_input(...)
if lesson_id and st.button("Export lesson DOCX"):
    response = httpx.post(
        f"{base_url}/api/coursepilot/lessons/{lesson_id}/export",
        ...
    )
```

注释式理解：
- 保存最近生成的 lesson id。
- 用户可以直接点击导出 DOCX。
- 返回的是导出文件记录 JSON，不是直接下载文件流。

## 5. 关键新增代码解读

### 5.1 `LessonGenerationParams`

位置：`src/coursepilot/schemas/lesson_schema.py`

核心代码：

```python
class LessonGenerationParams(BaseModel):
    chapter_range: str = Field(min_length=1)
    total_sessions: int = Field(default=2, ge=1, le=12)
    session_duration: int = Field(default=45, ge=15, le=240)
    student_level: str | None = None
    student_background: str | None = None
    teaching_template: str = "standard"
    teaching_focus: str | None = None
    include_interaction: bool = True
    include_homework: bool = True
    additional_requirements: str | None = None
```

逐行理解：
- `chapter_range` 是必填字段，表示要生成哪一章或哪一节的教学设计。
- `total_sessions` 是课时数，限制在 1 到 12。
- `session_duration` 是每个课时分钟数，限制在 15 到 240。
- `student_level` 和 `student_background` 给后续个性化生成预留。
- `teaching_template` 表示模板，例如 standard、BOPPPS 等。
- `teaching_focus` 是教师指定的重点。
- `include_interaction` 控制是否生成互动设计。
- `include_homework` 控制是否生成作业建议。
- `additional_requirements` 保存额外要求。

这些字段对应 PRD 中“教学设计参数配置”的输入项。

### 5.2 `SessionPlan`

核心代码：

```python
class SessionPlan(BaseModel):
    session_index: int = Field(ge=1)
    session_title: str = Field(min_length=1)
    duration: int = Field(ge=1)
    knowledge_points: list[str] = Field(min_length=1)
    teaching_focus: str = Field(min_length=1)
    difficulty_points: list[str] = Field(default_factory=list)
    time_allocation: list[TimeAllocation] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_sum(self):
        total_minutes = sum(item.minutes for item in self.time_allocation)
        if total_minutes != self.duration:
            raise ValueError("time_allocation minutes must equal duration")
        return self
```

逐行理解：
- 一个 `SessionPlan` 表示一个课时的计划。
- `session_index` 是第几课时。
- `duration` 是这个课时总时长。
- `knowledge_points` 是本课时覆盖的知识点。
- `time_allocation` 是时间分配，例如导入、讲解、练习、总结。
- `validate_time_sum` 是 Pydantic 层的校验：所有环节分钟数之和必须等于课时总时长。

这属于“结构化输出 + schema 校验”的核心能力。

### 5.3 `LessonDesignContent`

核心代码：

```python
class LessonDesignContent(BaseModel):
    course_name: str
    chapter: str
    total_sessions: int
    session_duration: int
    retrieved_contexts: list[KBSearchResult] = Field(default_factory=list)
    knowledge_points: list[str] = Field(default_factory=list)
    session_plan: list[SessionPlan]
    sessions: list[LessonSession]
```

逐行理解：
- `course_name` 和 `chapter` 是基础信息。
- `retrieved_contexts` 保存 RAG 检索结果，方便追溯生成依据。
- `knowledge_points` 保存从上下文提取出的知识点。
- `session_plan` 是课时规划。
- `sessions` 是真正的教学设计内容。

这里把“中间检索证据”和“最终教学设计”放在同一个 JSON 里，方便后续审查和导出。

### 5.4 `LessonValidationReport`

核心代码：

```python
class LessonValidationReport(BaseModel):
    schema_valid: bool = True
    session_count_valid: bool
    time_allocation_valid: bool
    required_fields_valid: bool
    knowledge_coverage_valid: bool
    citation_valid: bool
    errors: list[str] = Field(default_factory=list)
    repair_attempts: int = 0

    @property
    def passed(self) -> bool:
        return all([...])
```

逐行理解：
- `schema_valid` 表示 Pydantic schema 是否通过。
- `session_count_valid` 表示课时数量是否符合参数。
- `time_allocation_valid` 表示时间分配是否合理。
- `required_fields_valid` 表示必填内容是否存在。
- `knowledge_coverage_valid` 表示是否有知识点覆盖。
- `citation_valid` 表示是否有引用。
- `errors` 保存具体错误。
- `repair_attempts` 记录修复次数。
- `passed` 是一个便捷属性，只要所有检查项都为真才算通过。

### 5.5 `LessonValidator`

位置：`src/coursepilot/validators/lesson_validator.py`

核心代码：

```python
session_count_valid = len(lesson_design.sessions) == expected_sessions
plan_count_valid = len(lesson_design.session_plan) == expected_sessions
```

含义：
- 检查最终教学设计课时数量是否等于用户要求。
- 同时检查 session_plan 数量是否一致。

```python
for plan in lesson_design.session_plan:
    plan_minutes = sum(item.minutes for item in plan.time_allocation)
    if plan.duration != session_duration or plan_minutes != session_duration:
        time_allocation_valid = False
```

含义：
- 每个课时的 `duration` 必须等于用户要求的 `session_duration`。
- 每个课时内部的时间分配加起来也必须等于 `session_duration`。

```python
required_fields_valid = all(
    session.teaching_objectives and session.key_points and session.teaching_process
    for session in lesson_design.sessions
)
```

含义：
- 每个课时必须有教学目标、重点和教学过程。

```python
citation_valid = all(session.references for session in lesson_design.sessions)
```

含义：
- 每个课时都必须带至少一个引用。
- 引用来自 Phase 1 检索返回的 chunk。

### 5.6 `LessonService.generate_lesson`

位置：`src/coursepilot/services/lesson_service.py`

核心代码：

```python
course = self.session.get(Course, course_id)
if course is None:
    raise ValueError(f"Course not found: {course_id}")
```

含义：
- 生成教学设计必须绑定已有课程。
- 如果课程不存在，API 返回 404。

```python
task = GenerationTask(
    course_id=course_id,
    task_type="lesson_design",
    status="running",
    input_params_json=params.model_dump(),
)
```

含义：
- 创建生成任务记录。
- 初始状态是 `running`。
- 把用户输入参数保存下来，方便追踪任务来源。

```python
contexts = self._retrieve_contexts(course_id, params)
if not contexts:
    raise ValueError(
        "No course knowledge base context found. Build course documents before generating a lesson design."
    )
```

含义：
- 先用 Phase 1 的知识库检索课程资料。
- 如果没有检索到上下文，不允许生成教学设计。
- 这是为了避免无依据生成，也符合 PRD 中“生成内容基于课程资料”的要求。

```python
lesson_design = self._build_lesson_design(course, params, contexts)
validation_report = self.validator.validate(...)
```

含义：
- `_build_lesson_design` 基于检索结果组装结构化教学设计。
- `LessonValidator` 对结果做质量检查。

```python
lesson = LessonDesign(
    course_id=course_id,
    task_id=task.id,
    chapter=params.chapter_range,
    status="draft" if validation_report.passed else "needs_review",
    ...
)
```

含义：
- 校验通过则状态是 `draft`。
- 校验不通过则状态是 `needs_review`。
- 内容和校验报告都保存为 JSON。

```python
task.status = "completed" if validation_report.passed else "needs_review"
task.intermediate_outputs_json = {"retrieved_contexts": [c.model_dump() for c in contexts]}
task.validation_report_json = validation_report.model_dump(mode="json")
```

含义：
- 任务状态和 lesson 状态保持一致。
- 把检索上下文保存到任务中，方便后续审核“生成依据是什么”。

### 5.7 `LessonService._retrieve_contexts`

核心代码：

```python
queries = [params.chapter_range]
if params.teaching_focus:
    queries.append(params.teaching_focus)
```

含义：
- 默认用章节范围作为检索 query。
- 如果教师指定了教学重点，再额外检索一次教学重点。

```python
for result in kb_service.search(course_id, KBSearchRequest(query=query, top_k=5)):
    if result.chunk_id in seen:
        continue
    seen.add(result.chunk_id)
    results.append(result)
return results[:8]
```

含义：
- 调用 Phase 1 的 `KnowledgeBaseService.search`。
- 用 `seen` 去重，避免同一个 chunk 重复进入上下文。
- 最多保留 8 条上下文，防止教学设计 JSON 过大。

### 5.8 `LessonService._build_lesson_design`

这是当前 MVP 的“生成器”。

核心代码：

```python
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
```

含义：
- 从 RAG 检索内容中提取知识点。
- 从检索结果中创建引用。
- 每个课时后续会分配至少一个引用。

```python
for index in range(1, params.total_sessions + 1):
    session_points = self._slice_for_session(knowledge_points, index, params.total_sessions)
    allocation = self._default_time_allocation(params.session_duration)
```

含义：
- 按用户要求生成对应数量的课时。
- 把知识点切分到不同课时。
- 自动生成默认时间分配。

```python
SessionPlan(
    session_index=index,
    session_title=f"{params.chapter_range} - {title_focus}",
    duration=params.session_duration,
    knowledge_points=session_points,
    teaching_focus=params.teaching_focus or f"Understand and apply {title_focus}",
    difficulty_points=session_points[-2:],
    time_allocation=allocation,
)
```

含义：
- 为每个课时生成结构化计划。
- 难点默认取当前课时后两个知识点。
- 如果教师没有传 teaching_focus，就自动生成一个默认重点。

```python
"references": [reference],
```

含义：
- 每个课时都带引用。
- 这让 validator 的 `citation_valid` 可以通过，也方便导出 DOCX 时展示来源。

### 5.9 `LessonService.revise_lesson`

核心代码：

```python
content = LessonDesignContent.model_validate(lesson.content_json)
target_index = self._resolve_target_session(content, request.target_scope)
target_session = content.sessions[target_index]
```

含义：
- 从数据库 JSON 恢复成 Pydantic 对象。
- 根据 `target_scope` 找到目标课时。
- 如果没有匹配到具体课时，默认修改第 1 课时。

```python
note = f"Revision for {request.target_scope}: {request.feedback_text}"
if request.keep_unchanged_parts:
    target_session.interaction_design.append(note)
else:
    target_session.teaching_process.append(...)
```

含义：
- 如果要求尽量保持原内容，就把反馈追加到互动设计。
- 如果允许改动结构，就追加一个教学过程环节。

当前边界：
- 这里没有重新调用 RAG 检索。
- 也没有调用 LLM 重写某个段落。
- 它是一个可运行的 MVP 局部修改入口，后续可替换为 ReAct-style revise node。

### 5.10 `LessonService.export_lesson_docx`

核心代码：

```python
content = LessonDesignContent.model_validate(lesson.content_json)
export_dir = Path(settings.COURSEPILOT_STORAGE_DIR) / "exports" / lesson.course_id
file_name = f"lesson_design_{lesson.id}.docx"
output_path = export_dir / file_name
LessonDocxExporter().export(content, output_path)
```

含义：
- 从数据库恢复教学设计 JSON。
- 导出路径放到 `storage/exports/{course_id}`。
- 文件名使用 lesson id，避免覆盖。
- 真正写 Word 的工作交给 `LessonDocxExporter`。

```python
export_file = ExportFile(
    course_id=lesson.course_id,
    task_id=lesson.task_id,
    file_type="docx",
    file_name=file_name,
    file_path=str(output_path),
    file_role="lesson_docx",
)
```

含义：
- 导出后新增一条文件记录。
- 后续历史文件页面或下载接口可以基于这张表扩展。

### 5.11 `LessonDocxExporter`

位置：`src/coursepilot/exporters/lesson_docx_exporter.py`

核心代码：

```python
doc = Document()
doc.add_heading(f"{lesson_design.course_name} - {lesson_design.chapter}", level=0)
```

含义：
- 创建 Word 文档。
- 第一个大标题是课程名和章节。

```python
doc.add_heading("Knowledge Points", level=1)
for point in lesson_design.knowledge_points:
    doc.add_paragraph(point, style="List Bullet")
```

含义：
- 把知识点写成项目符号列表。

```python
for session in lesson_design.sessions:
    doc.add_heading(f"Session {session.session_index}: {session.session_title}", level=1)
    ...
```

含义：
- 每个课时单独一个一级标题。
- 课时内部再写 objectives、key points、difficult points、teaching process、interaction、homework、references。

```python
for ref in session.references:
    doc.add_paragraph(
        f"{ref.source_type or 'source'} | {ref.chapter or '-'} | "
        f"page={ref.page or '-'} | chunk={ref.chunk_id}"
    )
```

含义：
- Word 文档中会保留引用来源。
- 这对应 PRD 中“生成内容具有引用来源和可追溯性”的要求。

### 5.12 Lesson Graph State

位置：`src/agents/coursepilot/states/lesson_state.py`

核心代码：

```python
class LessonGraphState(TypedDict, total=False):
    messages: list[AnyMessage]
    lesson_params: dict[str, Any]
    retrieved_contexts: list[dict[str, Any]]
    knowledge_points: list[str]
    session_plan: list[dict[str, Any]]
    lesson_design: dict[str, Any]
    validation_report: dict[str, Any]
```

含义：
- 这是 LangGraph 节点之间传递的状态结构。
- 每个节点只读写其中一部分字段。
- `total=False` 表示字段不是一开始都必须存在。

### 5.13 Lesson Graph 节点

位置：`src/agents/coursepilot/nodes/lesson_nodes.py`

聊天入口：

```python
def chat_response(state):
    return {
        "messages": [
            AIMessage(
                content=(
                    "CoursePilot lesson agent is available. "
                    "Use /api/coursepilot/courses/{course_id}/lessons/generate "
                    "for product workflow generation."
                )
            )
        ]
    }
```

含义：
- 如果用户通过普通聊天方式调用这个 agent，它不会假装完成复杂产品流程。
- 它会提示用户使用业务 API。

知识点提取：

```python
def extract_knowledge_points(state):
    contexts = state.get("retrieved_contexts", [])
    ...
    return {"knowledge_points": points}
```

含义：
- 从 graph state 中的检索上下文提取关键词。
- 输出给后续 `plan_sessions` 使用。

课时规划：

```python
def plan_sessions(state):
    params = LessonGenerationParams.model_validate(state.get("lesson_params", {}))
    ...
    return {"session_plan": plans}
```

含义：
- 先把输入参数转成 `LessonGenerationParams`。
- 根据课时数和知识点生成 session plan。

教学设计生成：

```python
def generate_lesson_design(state):
    ...
    design = LessonDesignContent(...)
    return {"lesson_design": design.model_dump(mode="json")}
```

含义：
- 把课时规划、知识点、引用组合成完整 `LessonDesignContent`。
- 输出 JSON 给 validator。

### 5.14 Lesson Graph 编排

位置：`src/agents/coursepilot/graphs/lesson_graph.py`

入口分流：

```python
def route_entry(state):
    if "lesson_params" in state:
        return "workflow"
    return "chat"
```

含义：
- 有 `lesson_params` 就走结构化 workflow。
- 没有参数就走聊天提示。

repair 判断：

```python
def should_repair(state):
    report = state.get("validation_report", {})
    passed = all(report.get(key, False) for key in [...])
    if not passed and int(report.get("repair_attempts", 0)) < 2:
        return "repair"
    return "done"
```

含义：
- 如果校验不通过，并且 repair 次数小于 2，则进入 repair 节点。
- 这对应 PLAN 中“最多 2 轮 repair”的设计。
- 当前 repair 节点只增加 `repair_attempts`，没有真正重写内容。

Graph 主线：

```text
route
  -> chat_response
  -> END

route
  -> retrieve_course_context
  -> extract_knowledge_points
  -> plan_sessions
  -> generate_lesson_design
  -> validate_lesson_design
  -> reflect_and_revise 或 END
```

这体现了 workflow-first 的结构。

## 6. API 清单

### 6.1 生成教学设计

```text
POST /api/coursepilot/courses/{course_id}/lessons/generate
```

请求示例：

```json
{
  "chapter_range": "Search",
  "total_sessions": 2,
  "session_duration": 45,
  "teaching_template": "standard",
  "teaching_focus": "heuristic search",
  "include_interaction": true,
  "include_homework": true
}
```

返回核心字段：

```text
lesson_id
task_id
status
lesson_design
validation_report
```

### 6.2 读取教学设计

```text
GET /api/coursepilot/lessons/{lesson_id}
```

用途：
- 查看已经保存的教学设计 JSON。
- 查看状态和校验报告。

### 6.3 局部修改教学设计

```text
POST /api/coursepilot/lessons/{lesson_id}/revise
```

请求示例：

```json
{
  "target_scope": "第1课时",
  "feedback_text": "增加一个贴近生活的案例",
  "keep_unchanged_parts": true
}
```

当前行为：
- 找到目标课时。
- 把反馈追加到 interaction design 或 teaching process。
- 重新运行 validator。
- 保存修改后的 JSON。

### 6.4 导出教学设计 DOCX

```text
POST /api/coursepilot/lessons/{lesson_id}/export
```

返回核心字段：

```text
id
course_id
task_id
file_type
file_name
file_path
file_role
created_at
```

当前会把文件保存到：

```text
storage/exports/{course_id}/lesson_design_{lesson_id}.docx
```

## 7. 哪些内容不是 Phase 2

当前仓库还没有实现 Phase 3、Phase 4 的完整功能。以下内容不应算作 Phase 2 成果：

- Exam schema、Exam graph、试卷 blueprint、试题生成。
- 题目 validator、duplicate detector。
- 试卷 DOCX、答案 DOCX、解析 DOCX、答题卡导出。
- PPT schema、PPT graph、PPTX exporter。
- Review service、approved 内容写回知识库。
- 完整评估脚本和评估指标可视化。

此外，Phase 2 计划中提到的 prompt 文件当前也不是已完成成果：

- `src/coursepilot/prompts/lesson/*.md`
- `src/coursepilot/prompts/repair/fix_json.md`

当前实现没有依赖这些文件。

## 8. 如何运行验收

### 8.1 运行 Phase 2 专项测试

在项目根目录执行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_lesson_graph.py tests\coursepilot\test_validators.py tests\coursepilot\test_exporters.py tests\coursepilot\test_lesson_api.py tests\service\test_service.py -q
```

我本次实际运行结果：

```text
18 passed, 9 warnings in 1.53s
```

这些 warning 来自 LangGraph/SWIG 依赖的弃用提示，不是 Phase 2 测试失败。

### 8.2 检查 Phase 2 表迁移

先启动 Postgres：

```powershell
docker compose up -d postgres
```

设置本地环境变量：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
$env:POSTGRES_USER='postgres'
$env:POSTGRES_PASSWORD='postgres'
$env:POSTGRES_HOST='localhost'
$env:POSTGRES_PORT='5432'
$env:POSTGRES_DB='agent_service'
```

执行到 Phase 2 迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade 0003_create_lesson_tables
```

预期：
- 命令成功执行。
- 数据库中出现 `coursepilot_generation_tasks`。
- 数据库中出现 `coursepilot_lesson_designs`。
- 数据库中出现 `coursepilot_export_files`。

如果你已经执行过更后面的迁移，也没关系；那说明数据库版本已经超过 Phase 2。

### 8.3 启动 FastAPI 服务

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe src\run_service.py
```

服务默认地址：

```text
http://localhost:8080
```

健康检查：

```powershell
Invoke-RestMethod http://localhost:8080/health
```

预期返回：

```text
status: ok
```

检查 agent 注册：

```powershell
$info = Invoke-RestMethod http://localhost:8080/info
$info.agents | Where-Object { $_.key -eq 'coursepilot-lesson-agent' }
```

预期：
- 能看到 `coursepilot-lesson-agent`。

### 8.4 手动跑通 Phase 2 API 流程

因为教学设计生成依赖课程知识库，所以要先走一遍 Phase 1 的创建课程、上传资料、构建知识库。

创建课程：

```powershell
$course = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/api/coursepilot/courses `
  -ContentType 'application/json' `
  -Body '{"course_name":"AI Demo","course_type":"theory","student_level":"undergraduate"}'

$course
```

准备测试资料：

```powershell
New-Item -ItemType Directory -Force .\storage\manual_test | Out-Null
Set-Content -Path .\storage\manual_test\lesson.txt -Value 'state space search heuristic search goal test path cost classroom case' -Encoding UTF8
```

上传资料：

```powershell
$doc = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/documents/upload" `
  -Form @{
    source_type='textbook'
    file=Get-Item .\storage\manual_test\lesson.txt
  }

$doc
```

如果你的 PowerShell 不支持 `-Form` 参数，可以改用：

```powershell
curl.exe -X POST "http://localhost:8080/api/coursepilot/courses/$($course.id)/documents/upload" `
  -F "source_type=textbook" `
  -F "file=@storage/manual_test/lesson.txt"
```

使用 `curl.exe` 时，把返回 JSON 里的 `id` 手动赋值给：

```powershell
$documentId = '<把上传结果里的 id 粘贴到这里>'
```

构建知识库：

```powershell
$build = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/documents/$($doc.id)/build-kb"

$build
```

如果你使用的是 `curl.exe` 上传方式，则改用：

```powershell
$build = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/documents/$documentId/build-kb"

$build
```

预期：
- `parse_status` 是 `built`。
- `chunk_count` 大于等于 1。

生成教学设计：

```powershell
$lesson = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/lessons/generate" `
  -ContentType 'application/json' `
  -Body '{"chapter_range":"Search","total_sessions":2,"session_duration":45,"teaching_template":"standard"}'

$lesson
```

预期：
- 返回 `lesson_id`。
- 返回 `task_id`。
- `status` 通常是 `draft`。
- `lesson_design.total_sessions` 是 2。
- `validation_report.session_count_valid` 是 `True`。
- `validation_report.citation_valid` 是 `True`。

读取教学设计：

```powershell
$read = Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8080/api/coursepilot/lessons/$($lesson.lesson_id)"

$read
```

预期：
- `id` 等于 `$lesson.lesson_id`。
- 能看到 `content_json` 和 `validation_report_json`。

局部修改：

```powershell
$revision = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/lessons/$($lesson.lesson_id)/revise" `
  -ContentType 'application/json' `
  -Body '{"target_scope":"第1课时","feedback_text":"Add a life-like case.","keep_unchanged_parts":true}'

$revision
```

预期：
- 返回 `modification_summary`。
- 通常包含 `Updated session 1`。
- 返回修改后的 `lesson_design`。
- 返回新的 `validation_report`。

导出 DOCX：

```powershell
$export = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/lessons/$($lesson.lesson_id)/export"

$export
```

预期：
- `file_role` 是 `lesson_docx`。
- `file_type` 是 `docx`。
- `file_path` 指向本地生成的 Word 文件。

检查文件是否存在：

```powershell
Test-Path $export.file_path
```

预期输出：

```text
True
```

### 8.5 验证没有知识库时拒绝生成

创建一门没有资料的课程：

```powershell
$emptyCourse = Invoke-RestMethod `
  -Method Post `
  -Uri http://localhost:8080/api/coursepilot/courses `
  -ContentType 'application/json' `
  -Body '{"course_name":"Empty Course"}'
```

尝试生成教学设计：

```powershell
try {
  Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8080/api/coursepilot/courses/$($emptyCourse.id)/lessons/generate" `
    -ContentType 'application/json' `
    -Body '{"chapter_range":"Search","total_sessions":1,"session_duration":45}'
} catch {
  $_.ErrorDetails.Message
}
```

预期：
- 返回 400。
- 错误信息包含 `Build course documents`。

这说明系统不会在没有课程资料依据时生成教学设计。

### 8.6 启动 Streamlit 页面验收

保持 FastAPI 服务运行，再开一个 PowerShell：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
$env:AGENT_URL='http://localhost:8080'
.\.venv\Scripts\python.exe -m streamlit run src\streamlit_app.py
```

打开浏览器中的 Streamlit 地址，通常是：

```text
http://localhost:8501
```

验收步骤：

1. 左侧 `App mode` 选择 `CoursePilot Knowledge Base`。
2. 创建课程。
3. 上传资料。
4. 构建知识库。
5. 在 `Generate lesson design` 区域输入章节和课时参数。
6. 点击 `Generate lesson design`。
7. 页面应显示生成结果 JSON，并保存 `lesson_id`。
8. 点击 `Export lesson DOCX`。
9. 页面应显示导出文件记录。

## 9. Phase 2 验收清单

你可以按下面清单逐项确认：

- `coursepilot_generation_tasks` 表存在。
- `coursepilot_lesson_designs` 表存在。
- `coursepilot_export_files` 表存在。
- `/info` 能看到 `coursepilot-lesson-agent`。
- `coursepilot-lesson-agent` 的 graph 聊天入口能返回可用提示。
- 传入 `lesson_params` 时，lesson graph 能生成 `lesson_design` 和 `validation_report`。
- `POST /api/coursepilot/courses/{course_id}/lessons/generate` 能生成教学设计。
- 没有知识库上下文时，生成接口会拒绝生成并返回可读错误。
- 生成结果包含 `lesson_id`、`task_id`、`lesson_design`、`validation_report`。
- 生成结果是结构化 JSON，不是散文本。
- `LessonValidator` 会检查课时数量、时间分配、必填字段、知识点覆盖和引用。
- 教学设计会保存到 `coursepilot_lesson_designs`。
- 生成任务会保存到 `coursepilot_generation_tasks`。
- `GET /api/coursepilot/lessons/{lesson_id}` 可以读取教学设计。
- `POST /api/coursepilot/lessons/{lesson_id}/revise` 可以做基础局部修改。
- `POST /api/coursepilot/lessons/{lesson_id}/export` 可以导出 DOCX。
- DOCX 文件由 `LessonDocxExporter` 渲染，不是由 LLM 直接生成。
- 导出文件记录会保存到 `coursepilot_export_files`。
- Streamlit 页面可以触发生成和导出流程。

如果这些都满足，Phase 2 就达到了当前 MVP 版本“基于 RAG 的教学设计生成、校验、局部修改和 DOCX 导出”的验收标准。

## 10. 当前实现的边界和后续注意点

1. 当前教学设计生成是规则化 MVP 生成，不是真实 LLM 生成。
2. 当前没有完整 prompt 文件链路，`prompts/lesson/*.md` 和 `prompts/repair/fix_json.md` 仍是后续可补项。
3. 当前 graph 的 repair 节点只增加 `repair_attempts`，没有真正修复 JSON 或重写内容。
4. 当前业务 API 的 `generate_lesson` 会使用 RAG 检索上下文；但 `revise_lesson` 当前没有重新检索 RAG，只是追加教师反馈。
5. 当前 DOCX 导出是基础版，重在内容完整和可打开，不追求复杂排版。
6. 当前引用校验只检查每个课时是否有引用，不检查引用语义是否精确支持每一句内容。
7. 当前测试覆盖了 graph、validator、exporter、API 主流程和无知识库拒绝生成，但没有覆盖真实浏览器中的 Streamlit 交互。
