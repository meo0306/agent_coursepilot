# CoursePilot Agent 工程技术改造方案

**文档版本：** v1.0  
**文档状态：** 冻结执行版
**冻结日期：** 2026-07-22
**上位文档：**
- `01_CoursePilot_CourseRAG_Split_and_Refactor_Plan_v1.0.md`
- `02_CourseRAG_PRD_v1.0.md`
- `04_CourseRAG_Technical_Refactor_Plan_v1.0.md`

**适用仓库：** `meo0306/agent_coursepilot`  
**项目定位：** 面向高校教师备课的工作流型 Agent 系统  
**改造重心：** 工作流编排、结构化生成、分层校验、定向修复、Human-in-the-loop、Checkpoint、模板化导出和可观测性  
**与 CourseRAG 的关系：** CoursePilot 只通过稳定 Port/Client 使用知识点、Context、Evidence、QA 和审核写回能力

---

## 1. 文档目的

本文档将总体拆分方案中确定的 CoursePilot Agent 工程目标转化为可执行的技术架构、模块拆分、状态合同、LangGraph 工作流、验证与修复机制、模板系统、模型路由、持久化恢复、导出、审核、安全和迁移方案。

本文档重点回答：

1. 当前教案、试卷和 PPT 三条工作流应如何重构；
2. CoursePilot 如何消费 CourseRAG，而不再自行处理知识点抽取和底层检索；
3. 如何把简单布尔校验升级为结构化 `ValidationIssue`；
4. 如何只修复错误局部，而不是整件内容反复重生成；
5. 如何使用 LangGraph Checkpoint、Interrupt 和稳定 Thread 恢复任务；
6. 如何并行生成试题并控制重复、分值和知识点覆盖；
7. 如何实现可版本化的教案、试卷和 PPT 模板；
8. 如何让 PPTX 成为可编辑、可引用、可校验的教学初稿；
9. 如何划分 PostgreSQL、LangSmith 和 CourseRAG 的数据职责；
10. 如何在保持现有 API 可用的前提下渐进迁移。

CoursePilot 不追求完全自治的开放式多 Agent。默认采用：

> **Workflow-first + Structured Generation + Deterministic Validation + Targeted Repair + Explicit Human Approval**

---

## 2. 当前实现基线

现有实现必须保留为 CoursePilot 评测基线，不应直接覆盖后失去对比对象。

### 2.1 当前代码位置

| 能力 | 当前文件 |
|---|---|
| 教案 Graph | `src/agents/coursepilot/graphs/lesson_graph.py` |
| 试卷 Graph | `src/agents/coursepilot/graphs/exam_graph.py` |
| PPT Graph | `src/agents/coursepilot/graphs/ppt_graph.py` |
| 教案节点 | `src/agents/coursepilot/nodes/lesson_nodes.py` |
| 试卷节点 | `src/agents/coursepilot/nodes/exam_nodes.py` |
| PPT 节点 | `src/agents/coursepilot/nodes/ppt_nodes.py` |
| State | `src/agents/coursepilot/states/` |
| LLM 入口 | `src/coursepilot/llm.py` |
| 教案服务 | `src/coursepilot/services/lesson_service.py` |
| 试卷服务 | `src/coursepilot/services/exam_service.py` |
| PPT 服务 | `src/coursepilot/services/ppt_service.py` |
| 审核写回 | `src/coursepilot/services/review_service.py` |
| Validator | `src/coursepilot/validators/` |
| 导出 | `src/coursepilot/exporters/` |
| 任务与幂等 | `src/coursepilot/services/async_task_service.py` |
| Workflow Metadata | `src/coursepilot/services/workflow_tracking.py` |

### 2.2 当前工作流

#### 教案

```text
retrieve_course_context
→ 再次从 Context 抽取知识点
→ plan_sessions
→ generate_lesson_design
→ validate
→ reflect_and_revise
```

#### 试卷

```text
retrieve_course_context
→ plan_exam_blueprint
→ 人工确认 Blueprint
→ 按题型串行生成问题
→ validate
→ repair_exam_questions
```

#### PPT

```text
读取 Lesson Design
→ generate_slide_outline
→ validate
→ repair_slide_outline
→ 使用默认 PPT 布局导出
```

### 2.3 当前优势

现有系统已经具备：

- 三条独立 LangGraph 工作流；
- Pydantic Structured Output；
- 生成任务与业务对象分离；
- 数据库后台任务、租约和幂等键；
- 基础生成元数据、Prompt Hash 和 Token 统计；
- 试卷 Blueprint 人工确认；
- DOCX/PPTX 导出；
- 审核记录与写回入口；
- Deterministic Fallback 和真实模型评测隔离开关。

### 2.4 当前主要限制

1. Graph 直接 `compile()`，没有业务工作流 Checkpointer；
2. 每次调用随机生成新 `thread_id`，不能稳定恢复同一任务；
3. State 使用松散 `dict[str, Any]`，阶段边界和版本不明确；
4. 教案在 CourseRAG 已抽取知识点后仍重新从 Context 抽取；
5. 三条流程总体线性，缺少可恢复的阶段 Artifact；
6. 试题按 Group 串行生成，延迟随题型和题量线性增加；
7. Validator 主要返回布尔值和字符串错误，无法定位具体字段与对象；
8. Repair 通常把完整 Artifact 和完整 Validation Report 交给模型重写；
9. 引用仍依赖 `chunk_id`，没有统一 Evidence Contract；
10. LLM 全局硬编码相同 Temperature、High Reasoning 和 Thinking 参数；
11. Deterministic Fallback 在生产生成中可能掩盖模型或 Prompt 错误；
12. PPT 只使用默认标题页和标题+正文页布局；
13. PPT 没有 Template/Master、版式映射、溢出检查和渲染后检查；
14. 审核写回可以把整个教案和整份 PPT 大纲写入知识库，范围过宽；
15. 业务状态、Agent 执行状态、审批状态和导出状态尚未形成统一状态机。

---

## 3. 改造目标与原则

### 3.1 核心目标

#### G1：可控工作流

每个生成任务具有明确的计划、阶段、输入、输出、校验结果、修复记录和人工决策。

#### G2：局部可修复

Validator 能定位错误对象和字段，Repair 只修改受影响部分，并执行无回归复验。

#### G3：可恢复

任务在进程中断、模型超时、人工暂停后可基于同一 `task_id/thread_id` 恢复，不重复已经成功的高成本节点。

#### G4：证据驱动

Agent 不自行猜测 CourseRAG 内部数据，通过 Knowledge Point、Context Package 和 Evidence ID 生成与校验内容。

#### G5：模板化

教案、试卷和 PPT 的输入、Prompt、Schema、Validator、Repair 和 Exporter 均通过版本化 Template/Profile 配置。

#### G6：可观测

能够从一个 Task 追踪 CourseRAG 请求、模型调用、Graph Node、Validator Issue、Repair 和导出结果。

#### G7：可独立评测

三条 Agent 流程可使用 Mock CourseRAG、固定 Context、真实 CourseRAG 和故障注入分别评测。

### 3.2 设计原则

- 业务编排放在 Application Service 与 LangGraph，底层能力通过 Port 调用；
- State 保存结构化 Artifact 和引用，不保存无界聊天历史；
- 长文本通过 Artifact/Context Reference 传递，不在每个节点复制；
- 规则能确定的问题优先本地修复；
- LLM Repair 必须有明确 Scope 和 Allowed Paths；
- Human Approval 是业务事件，不是普通布尔字段；
- Side Effect 节点必须幂等；
- LangSmith 用于 Trace，不作为业务状态和恢复事实源；
- 正式评测不允许静默使用 Deterministic Fallback；
- CoursePilot 不导入 CourseRAG 的 Parser、Vector Store、BM25 或 ORM。

---

## 4. 目标架构

```text
CoursePilot UI
    ↓
CoursePilot API
    ↓
Application Services
    ├── LessonApplicationService
    ├── ExamApplicationService
    ├── PPTApplicationService
    ├── ReviewApplicationService
    └── ExportApplicationService
    ↓
Agent Runtime
    ├── Graph Registry
    ├── PostgreSQL Checkpointer
    ├── Model Router
    ├── Template Registry
    ├── Validator Registry
    ├── Repair Planner
    └── LangSmith Observability
    ↓
CourseRAGServicePort
    ├── KnowledgeBasePort
    ├── RetrievalPort
    ├── QuestionAnsweringPort
    ├── EvidencePort
    └── VerifiedContentPort
```

### 4.1 目标代码结构

```text
src/coursepilot/
├── api/
│   ├── lessons.py
│   ├── exams.py
│   ├── ppt.py
│   ├── tasks.py
│   ├── reviews.py
│   ├── templates.py
│   └── exports.py
├── application/
│   ├── lesson_service.py
│   ├── exam_service.py
│   ├── ppt_service.py
│   ├── task_service.py
│   ├── review_service.py
│   └── export_service.py
├── domain/
│   ├── artifacts.py
│   ├── tasks.py
│   ├── approvals.py
│   ├── templates.py
│   ├── validation.py
│   └── repair.py
├── agents/
│   ├── registry.py
│   ├── runtime.py
│   ├── common/
│   │   ├── state.py
│   │   ├── nodes.py
│   │   ├── routing.py
│   │   └── interrupts.py
│   ├── lesson/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── policies.py
│   ├── exam/
│   │   ├── graph.py
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── fanout.py
│   └── ppt/
│       ├── graph.py
│       ├── state.py
│       ├── nodes.py
│       └── layouts.py
├── courserag/
│   ├── ports.py
│   ├── local_adapter.py
│   ├── http_client.py
│   └── mock.py
├── models/
│   ├── gateway.py
│   ├── router.py
│   ├── profiles.py
│   ├── structured_generation.py
│   └── usage.py
├── templates/
│   ├── registry.py
│   ├── definitions.py
│   ├── builtins/
│   └── loaders.py
├── validators/
│   ├── registry.py
│   ├── common/
│   ├── lesson/
│   ├── exam/
│   └── ppt/
├── repairs/
│   ├── planner.py
│   ├── deterministic.py
│   ├── llm_repair.py
│   └── regression.py
├── exporters/
│   ├── lesson_docx/
│   ├── exam_docx/
│   └── pptx/
├── persistence/
│   ├── models/
│   ├── repositories/
│   └── migrations/
├── observability/
│   ├── langsmith.py
│   ├── redaction.py
│   ├── events.py
│   └── metrics.py
├── security/
│   ├── authorization.py
│   ├── prompt_injection.py
│   ├── output_safety.py
│   └── file_policy.py
└── evals/
```

原 `src/agents/coursepilot/` 可先作为兼容层，逐条 Graph 迁移至新结构后删除。

---

## 5. CourseRAG 集成边界

### 5.1 知识点来源

CoursePilot 不再在教案节点中对 Context 重复抽取知识点。

改为：

```text
CoursePilot Task Params
→ CourseRAG 获取课程/章节知识点
→ Knowledge Point Selection
→ CourseRAG 按 Purpose 构建 Context
→ Agent Planning
```

CoursePilot 使用：

- `knowledge_point_id`；
- Canonical Name；
- Alias；
- Parent；
- Review Status；
- Evidence IDs；
- Content Role；
- CourseRAG Version。

Agent State 中不得把知识点退化为无法追踪的字符串列表。

### 5.2 Context Request

三条工作流使用不同 Purpose：

| 工作流 | Purpose |
|---|---|
| 教案 | `lesson_generation` |
| 试卷 | `exam_generation` |
| PPT | `ppt_generation` |

CoursePilot 可以指定：

- 目标 Knowledge Point IDs；
- Section/Document Filter；
- Content Role；
- Token Budget；
- Source Tier；
- 是否允许未审核知识点。

### 5.3 引用

新 Artifact 统一引用：

```python
class ArtifactReference(BaseModel):
    evidence_id: str
    document_id: str
    document_version_id: str
    section_path: list[str]
    page_label: str | None
    physical_page_index: int | None
    source_tier: str
    knowledge_point_ids: list[str]
```

兼容期可同时返回 Legacy `chunk_id`，但新 Validator 和 Exporter 只以 `evidence_id` 为可信引用主键。

### 5.4 写回

CoursePilot 只能在用户明确批准后写回白名单对象：

- `verified_question`；
- `verified_answer_explanation`；
- `verified_lesson_fragment`。

不得把整份 Lesson Design、整套 Exam 或整份 PPT 自动写回。

---

## 6. 统一 Task 与 State 合同

### 6.1 业务 Task

```python
class AgentTask(BaseModel):
    task_id: str
    course_id: str
    workflow_type: Literal["lesson", "exam", "ppt"]
    status: TaskStatus
    current_stage: str
    thread_id: str
    template_id: str
    template_version: str
    input_version: int
    artifact_version: int
    active_run_id: str | None
    created_at: datetime
    updated_at: datetime
```

`TaskStatus`：

```text
queued
running
waiting_human
needs_review
completed
failed
cancelled
```

### 6.2 Stable Thread

当前随机 Thread 改为：

```text
thread_id = coursepilot:{workflow_type}:{task_id}
checkpoint_ns = workflow_type
```

重试和恢复同一 Task 必须复用 Thread；重新开始的新任务才创建新 Task ID。

### 6.3 Common Graph State

```python
class CommonWorkflowState(TypedDict, total=False):
    task_context: TaskContext
    request: dict
    template_snapshot: dict
    model_profiles: dict
    courserag_snapshot: dict
    artifacts: dict[str, ArtifactRef]
    validation_report: dict
    repair_plan: dict
    approval: dict
    node_runs: list[dict]
    warnings: list[dict]
    error: dict | None
```

State 中保存 Snapshot/Reference，不把完整原始课程文件和无限中间文本重复写入每个 Checkpoint。

### 6.4 ArtifactRef

```python
class ArtifactRef(BaseModel):
    artifact_id: str
    artifact_type: str
    artifact_version: int
    storage_kind: Literal["state", "postgres", "object"]
    storage_uri: str | None
    content_hash: str
    schema_version: str
```

较小结构化内容可保存在 State；大 Context、渲染文件和详细 Trace 保存至 PostgreSQL JSONB 或文件存储，只在 State 中保存引用。

### 6.5 NodeResult

```python
class NodeResult(BaseModel):
    node_name: str
    status: Literal["succeeded", "failed", "skipped", "waiting_human"]
    input_fingerprint: str
    output_artifacts: list[ArtifactRef]
    model_run_ids: list[str]
    warnings: list[dict]
    started_at: datetime
    ended_at: datetime
```

节点根据 Input Fingerprint 判断恢复时是否可以复用结果。

---

## 7. LangGraph Runtime、Checkpoint 与 Interrupt

### 7.1 Checkpointer

三条业务 Graph 必须从：

```python
graph.compile()
```

迁移为：

```python
graph.compile(
    checkpointer=postgres_checkpointer,
)
```

使用独立 PostgreSQL Checkpoint Schema，与 CoursePilot 业务表分离但使用同一数据库实例即可。

### 7.2 Interrupt 点

MVP 将以下 Interrupt 作为正式业务节点，而不是仅用于调试的可选暂停。每个 Interrupt 必须保存待审核 Artifact、Validation Summary、允许修改的字段和恢复入口。

#### 教案

1. **Session Plan Review**
   - 触发时机：`plan_lesson_blueprint` 完成后、Session 内容生成前；
   - 审核对象：知识点选择与分配、课时划分、每课时目标、重点难点、时间预算和活动类型；
   - 允许操作：批准、修改指定 Session Plan、重新规划、取消；
   - 目的：避免在课时结构错误时继续生成全部教案正文。

2. **Final Draft Review**
   - 触发时机：最终 Draft 完成分层校验和定向修复后、正式导出或 Verified Writeback 前；
   - 审核对象：完整教案、剩余 Validation Issues、修复 Diff 和引用；
   - 允许操作：批准导出、批准白名单片段写回、仅导出不写回、请求局部修改、拒绝；
   - 正式导出和写回分别记录 Approval Scope，不得使用一个模糊的 `approved=true` 同时授权两类副作用。

#### 试卷

1. **Blueprint Review**
   - 触发时机：Blueprint 完成并通过确定性校验后、题目生成前；
   - 审核对象：题型、题量、分值、难度、知识点覆盖、内容角色和生成批次；
   - 允许操作：批准、修改 Blueprint、重新规划、取消。

2. **Global Validation Review**
   - 触发时机：全部题目聚合、全局重复度/覆盖度/分值/引用校验及定向修复后、正式导出前；
   - 审核对象：整套试卷、答案解析、全局指标、重复题对和剩余 Issues；
   - 允许操作：批准正式导出、批准指定题目/解析写回、仅导出不写回、请求局部重生成、拒绝；
   - 正式导出前必须经过该 Interrupt，不再另外设置内容完全重复的第三个暂停点。

#### PPT

1. **Slide Architecture Review**
   - 触发时机：Slide Architecture 和 Layout Plan 完成后、逐页内容生成前；
   - 审核对象：页序、页型、课时来源、知识点覆盖、版式分配、图表/素材占位和页数预算；
   - 允许操作：批准、调整页序和页型、增删页面、重新规划、取消。

2. **Final PPT Review**
   - 触发时机：PPT 内容、Notes、引用和渲染校验完成后、PPTX 导出或 Verified Writeback 前；
   - 审核对象：大纲预览、渲染预览、溢出告警、引用和剩余 Issues；
   - 允许操作：批准导出、批准白名单片段写回、仅导出不写回、请求指定页面修改、拒绝。

### 7.2.1 Interrupt 数据合同

```python
class InterruptPayload(BaseModel):
    interrupt_type: Literal[
        "lesson_session_plan_review",
        "lesson_final_review",
        "exam_blueprint_review",
        "exam_global_review",
        "ppt_architecture_review",
        "ppt_final_review",
    ]
    task_id: str
    checkpoint_id: str
    artifact_ref: ArtifactRef
    artifact_summary: dict
    validation_summary: dict
    editable_paths: list[str]
    allowed_actions: list[str]
    export_requires_approval: bool
    writeback_requires_separate_approval: bool
```

人工在 UI 中修改结构化字段后，系统先创建新 Artifact Version，再通过 `Command(resume=...)` 恢复，不直接篡改旧 Checkpoint 内容。

### 7.3 Human Decision

```python
class HumanDecision(BaseModel):
    decision_id: str
    task_id: str
    checkpoint_id: str
    action: Literal[
        "approve",
        "request_changes",
        "reject",
        "cancel",
        "continue_without_writeback",
    ]
    feedback: str | None
    target_paths: list[str]
    actor_id: str
    created_at: datetime
```

所有人工决策写入 PostgreSQL，再通过 `Command(resume=...)` 恢复 Graph。

### 7.4 副作用原则

Graph 内的以下节点属于副作用节点：

- 保存正式 Artifact Version；
- 导出文件；
- 写回 CourseRAG；
- 发送外部通知。

每个副作用节点必须有：

- Idempotency Key；
- Side Effect Record；
- `pending/running/succeeded/failed` 状态；
- 可重复读取的 Result；
- 恢复时不重复执行已成功操作。

---

## 8. 通用 Agent 工作流模式

```text
Validate Request
→ Load Template Snapshot
→ Load User/Course Preferences
→ Acquire Knowledge Points
→ Build Context Package
→ Plan Artifact
→ Optional Human Interrupt
→ Generate Components
→ Aggregate Artifact
→ Layered Validation
→ Build Repair Plan
→ Targeted Repair Loop
→ No-regression Validation
→ Persist Draft Version
→ Human Review
→ Export and/or Verified Writeback
```

### 8.1 Plan 与 Generate 分离

所有流程至少拆成：

1. **Plan Artifact**：确定结构、知识点分配、内容角色、目标数量和引用需求；
2. **Generate Components**：按 Plan 生成局部内容；
3. **Aggregate**：合并并处理跨组件一致性；
4. **Validate/Repair**。

不得让一次模型调用同时决定结构、生成全部内容、分配引用并自我校验。

### 8.2 Graph 路由

路由只依据结构化状态：

- 当前 Workflow Phase；
- Validation Issue Severity；
- Repair Attempts；
- Human Decision；
- Provider Error Category；
- Budget Remaining。

不得从自然语言错误文本中用字符串匹配决定关键业务流向。

---

## 9. 教案工作流改造

### 9.1 目标流程

```text
validate_lesson_request
→ load_lesson_template
→ fetch_course_knowledge_points
→ select_target_knowledge_points
→ build_lesson_context
→ plan_lesson_blueprint
→ optional_interrupt_blueprint
→ fanout_generate_sessions
→ aggregate_sessions
→ validate_lesson
→ plan_repairs
→ repair_targeted_sessions
→ validate_no_regression
→ persist_lesson_draft
→ interrupt_final_review
→ export/writeback
```

### 9.2 Lesson Blueprint

```python
class LessonBlueprint(BaseModel):
    course_id: str
    chapter_scope: str
    total_sessions: int
    session_duration: int
    selected_knowledge_points: list[KnowledgePointAllocation]
    session_plans: list[LessonSessionBlueprint]
    coverage_policy: dict
    template_snapshot_id: str
```

每个 Session Blueprint 明确：

- Session Index/Title；
- Knowledge Point IDs；
- 教学目标类型；
- 重点和难点；
- Context/Evidence Requirements；
- 时间预算；
- 活动类型；
- 评价方式。

### 9.3 Session 并行生成

课时相对独立时，可使用 LangGraph `Send` 按 Session Fan-out：

```text
Lesson Blueprint
├── Generate Session 1
├── Generate Session 2
└── Generate Session N
        ↓
Aggregate
```

并发必须受模型 Provider 限流和总 Token Budget 控制。默认并发上限建议 3。

### 9.4 跨课时一致性

Aggregate 后检查：

- 知识点是否遗漏或重复过多；
- 前后课时目标是否递进；
- 时间分配是否正确；
- 术语是否一致；
- 教学活动是否重复；
- 作业与目标是否对应；
- 每个关键教学 Claim 是否有 Evidence。

### 9.5 Revision

用户修改教案时：

1. 解析 `target_scope` 为稳定 JSON Path；
2. 只读取目标 Session、相关 Blueprint 和 Context；
3. 生成 Patch；
4. 应用 Patch；
5. 重新执行目标 Session 校验和跨课时无回归校验；
6. 创建新 Artifact Version，不覆盖旧版本。

---

## 10. 试卷工作流改造

### 10.1 目标流程

```text
validate_exam_request
→ load_exam_template
→ fetch_knowledge_points
→ build_exam_context
→ plan_exam_blueprint
→ validate_blueprint
→ interrupt_blueprint_confirmation
→ expand_question_jobs
→ fanout_generate_question_batches
→ validate_each_batch
→ repair_failed_questions
→ aggregate_questions
→ global_exam_validation
→ global_duplicate_repair
→ persist_exam_draft
→ final_review
→ export/writeback
```

### 10.2 Blueprint

Blueprint 必须确定：

- 题型和数量；
- 每题分值；
- 知识点分配；
- 难度分配；
- 内容角色；
- 引用要求；
- 题目生成批次；
- 可接受重复阈值；
- 答案和解析要求。

### 10.3 Fan-out/Fan-in

不再在单节点内对所有题型串行循环。

推荐最小并行单元：

```text
Question Batch = 同题型 + 同知识点组 + 1～5 道题
```

每个 Batch 有稳定：

- `question_job_id`；
- Input Fingerprint；
- Provider Attempt；
- Generated Question IDs；
- Validation Issues。

### 10.4 局部修复

按 Issue 精确处理：

| Issue | Repair |
|---|---|
| 缺少题目 | 只生成缺失题目 |
| 分值不匹配 | 确定性调整或重分配 |
| 选项数量错误 | 只修复该题选项 |
| 正确答案不在选项中 | 修复该题答案/选项 |
| 解析缺失 | 只补解析 |
| 引用缺失 | 重新检索目标知识点证据并补引用 |
| 重复题 | 只重生成重复度较高的一题 |
| 知识点覆盖不足 | 只补缺失知识点题目 |

### 10.5 重复检测

分为：

- 文本近似重复；
- 语义重复；
- 相同答案模式；
- 相同选项结构；
- 跨历史题库重复。

MVP 可先实现文本/Embedding 相似度和规则；正式判定阈值通过 Dev 调整。

### 10.6 写回

审核通过后按题目粒度写回：

- 题干；
- 选项；
- 正确答案；
- 解析；
- Knowledge Point IDs；
- Evidence IDs；
- Approval Record ID。

不得把整个 Exam Blueprint 或试卷文档作为单一知识块写回。

---

## 11. PPT 工作流改造

### 11.1 产品边界

PPT 输出定位为：

> **可编辑、结构合理、有讲者备注和引用的教学演示初稿。**

不承诺自动生成商业级视觉设计，也不默认生成复杂插画。

### 11.2 目标流程

```text
validate_ppt_request
→ load_ppt_template
→ load_lesson_and_evidence
→ plan_slide_architecture
→ optional_interrupt_architecture
→ fanout_generate_slide_content
→ aggregate_slide_deck
→ validate_content_and_grounding
→ render_pptx_draft
→ validate_rendered_layout
→ targeted_slide_repair
→ persist_ppt_draft
→ final_review
→ export
```

### 11.3 Slide Architecture

```python
class SlidePlan(BaseModel):
    slide_id: str
    slide_index: int
    slide_type: str
    layout_key: str
    title: str
    source_session_index: int | None
    knowledge_point_ids: list[str]
    evidence_ids: list[str]
    content_budget: SlideContentBudget
    asset_requests: list[AssetRequest]
```

### 11.4 Slide Types

MVP 建议：

- `title`；
- `agenda`；
- `objectives`；
- `concept`；
- `process`；
- `comparison`；
- `example`；
- `activity`；
- `summary`；
- `references`。

不同 Slide Type 映射不同 Layout，不再统一使用“标题 + 正文”。

### 11.5 PPTX Template

使用真实 `.pptx` 模板文件：

- Slide Master；
- Layout；
- Theme Font；
- Placeholder；
- 页脚和页码；
- Notes 规范；
- Citation Area。

`PPTTemplateProfile` 保存：

```python
class PPTTemplateProfile(BaseModel):
    template_id: str
    version: str
    pptx_uri: str
    slide_type_layout_map: dict[str, str]
    max_title_chars: dict[str, int]
    max_bullets: dict[str, int]
    max_chars_per_bullet: dict[str, int]
    citation_style: str
    notes_style: str
```

### 11.6 教学素材

MVP 支持：

- CourseRAG 原文表格；
- 原文图片占位；
- 流程图/概念图占位；
- 教师后续替换的 Asset Placeholder。

未验证版权或来源的网络图片不得自动嵌入。

### 11.7 版式校验

导出前确定性检查：

- 标题长度；
- Bullet 数量；
- 单 Bullet 长度；
- Placeholder 是否缺失；
- Slide Type/Layout 是否匹配；
- 引用是否存在；
- Notes 是否存在；
- 内容密度；
- 空白页；
- Slide Index 连续性。

导出后建议使用固定 LibreOffice Renderer 将 PPTX 渲染为 PDF，再检查：

- 页数一致；
- 文本是否落在页面边界；
- Placeholder 是否成功填充；
- 渲染是否失败。

复杂视觉美观度保留人工 Checklist，不使用 LLM-as-a-Judge。

### 11.8 定向修复

- 内容溢出：缩短 Bullet、拆分 Slide 或切换 Layout；
- 引用缺失：只修复该 Slide；
- Slide 类型错误：只更新 Architecture 和该页；
- 重复内容：删除或重写低优先级 Slide；
- Notes 缺失：补充 Notes，不重生成整页。

---

## 12. 模板系统

### 12.1 TemplateDefinition

```python
class TemplateDefinition(BaseModel):
    template_id: str
    name: str
    artifact_type: Literal["lesson", "exam", "ppt"]
    version: str
    status: Literal["draft", "active", "deprecated"]
    input_schema_version: str
    output_schema_version: str
    planner_prompt: PromptProfile
    generator_profiles: dict[str, PromptProfile]
    validator_profile: str
    repair_profile: str
    model_routing_profile: str
    exporter_profile: str
    default_config: dict
```

### 12.2 Snapshot

任务启动时冻结完整 Template Snapshot：

- Template ID/Version；
- Prompt Hash；
- Schema Version；
- Validator Profile；
- Model Profile；
- Exporter Profile；
- 用户覆盖参数。

任务恢复时不得自动切换到最新 Template。

### 12.3 内置模板

MVP 的内置模板由系统随代码仓库提供，不要求用户在实现开始前自行准备全部模板。模板分为两层：

1. **逻辑模板**：定义输入字段、规划规则、Prompt、输出 Schema、Validator、Repair、Model Routing 和默认参数；
2. **物理导出模板**：DOCX 样式文件或 PPTX Master/Layout 文件，决定最终文件的视觉与排版。

系统先提供可直接运行的通用内置模板：

#### 教案

- `lesson_standard_university_v1`：标准高校教案；
- `lesson_seminar_v1`：研讨课；
- `lesson_lab_practice_v1`：实验/实践课。

#### 试卷

- `exam_chapter_assignment_v1`：章节作业；
- `exam_unit_quiz_v1`：单元测验；
- `exam_midterm_final_v1`：期中/期末试卷。

#### PPT

- `ppt_standard_lecture_v1`：标准讲授；
- `ppt_concept_explanation_v1`：概念解释；
- `ppt_case_seminar_v1`：案例研讨。

### 12.3.1 用户是否需要提供模板

用户材料不是 MVP 启动的前置条件。实现阶段默认由系统创建：

- 通用教案 DOCX 样式；
- 通用试卷及答案 DOCX 样式；
- 三套简洁、可编辑的 PPTX Master/Layout；
- 对应的逻辑 TemplateDefinition。

但在以下场景中，建议用户后续提供真实模板或样例：

- 需要匹配学校、学院或课程组的固定表格；
- 需要使用校徽、品牌色、页眉页脚；
- 教案存在指定栏目和审批格式；
- 试卷存在固定密封线、答题区或卷头；
- PPT 必须严格复用既有母版。

用户提供的文件先进入 Template Import/Mapping 流程，不直接作为 Prompt：

```text
用户 DOCX/PPTX 模板
→ 检测 Style / Master / Layout / Placeholder
→ 建立 Exporter Mapping
→ 人工确认字段映射
→ 创建 Custom TemplateDefinition
→ 版本化发布
```

因此建议的实施顺序是：

1. 先用系统内置模板完成端到端能力；
2. 再选取 1 套用户真实教案模板和 1 套 PPT 模板验证可扩展性；
3. 不在 MVP 中维护大量高度相似模板。

### 12.3.2 模板资源目录

```text
resources/templates/
├── lesson/
│   ├── standard_university_v1.yaml
│   ├── seminar_v1.yaml
│   └── lab_practice_v1.yaml
├── exam/
│   ├── chapter_assignment_v1.yaml
│   ├── unit_quiz_v1.yaml
│   └── midterm_final_v1.yaml
├── ppt/
│   ├── standard_lecture_v1.yaml
│   ├── concept_explanation_v1.yaml
│   └── case_seminar_v1.yaml
└── exporters/
    ├── lesson_default.docx
    ├── exam_default.docx
    ├── ppt_standard_lecture.pptx
    ├── ppt_concept_explanation.pptx
    └── ppt_case_seminar.pptx
```

模板数量不宜过多，重点展示版本化、导入、映射和扩展机制。

---

## 13. 模型网关与路由

### 13.1 当前问题

当前所有 Structured Generation 共用同一模型实例，并统一使用：

- Temperature 0.2；
- Non-streaming；
- High Reasoning；
- Thinking Enabled。

这会导致简单分类、修复和规划也承担不必要延迟和成本，并可能与部分 OpenAI-compatible Provider 不兼容。

### 13.2 Model Gateway

```python
class ModelRequest(BaseModel):
    capability: Literal[
        "planning",
        "structured_generation",
        "classification",
        "repair",
        "compression",
    ]
    profile_id: str
    prompt_name: str
    output_schema: str
    payload_ref: str
    timeout_seconds: int
    max_attempts: int
```

```python
class ModelProfile(BaseModel):
    provider: str
    model: str
    base_url_ref: str
    temperature: float
    reasoning_effort: str | None
    thinking_enabled: bool
    max_output_tokens: int | None
    timeout_seconds: int
    max_retries: int
```

### 13.3 默认路由

模型路由按“任务风险和能力需求”选择 Profile，不在业务节点中硬编码具体模型名称。

#### 13.3.1 MVP 最小部署：两个实际模型

MVP 默认只要求配置两类实际模型：

1. **Main Model**
   - 用于用户可见的核心内容生成和高风险内容修复；
   - 要求中文表达、长上下文、结构化输出和复杂指令遵循能力稳定。

2. **Light Model**
   - 用于分类、字段抽取、简单规划辅助、压缩和低风险结构修复；
   - 优先考虑延迟、成本和结构化输出稳定性。

逻辑上仍定义多个 Profile，但允许映射到同一个实际模型：

```text
planner_profile  ─┐
generator_profile ├─→ Main Model
content_repair    ┘

classifier_profile ─┐
compression_profile ├─→ Light Model
json_repair_profile ┘
```

当只有一个可用模型时，全部 Profile 可以临时映射到同一模型，但仍必须保留独立参数和运行记录。

#### 13.3.2 默认节点路由

| 节点/任务 | 首选执行方式 | 默认 Profile |
|---|---|---|
| 请求校验、显式路由 | 确定性规则 | 无模型 |
| 简单分类、Scope 解析 | 规则优先，失败后模型 | `classifier_light` |
| Lesson/Exam/PPT Blueprint | Main Model，低温度 | `planner_main` |
| Session 内容生成 | Main Model | `generator_main` |
| Question Batch 生成 | Main Model | `generator_main` |
| Slide 内容与 Notes 生成 | Main Model | `generator_main` |
| JSON/Schema 小修复 | 本地规则优先 | `json_repair_light` |
| 缺失字段补全且不涉及事实改写 | Light Model | `json_repair_light` |
| 内容错误、引用错误、教学逻辑错误 | Main Model | `content_repair_main` |
| Context Compression | 确定性裁剪/去重优先 | `compression_light` |
| Validation Summary | 程序聚合 | 无模型 |
| Export/Layout | 确定性代码 | 无模型 |

#### 13.3.3 Repair 路由

```text
L0 Schema / L1 Deterministic
→ 本地规则修复

L2 Cross-field，且只涉及格式或缺失字段
→ Light Model

L2 业务逻辑冲突、L3 Grounding、L4 Pedagogy
→ Main Model

Critical Issue
→ Main Model + 修复后人工审核，不允许降级为模板填充
```

#### 13.3.4 模型配置

建议通过独立 Profile 配置文件管理，不把全部参数塞进一个全局 `.env`：

```yaml
profiles:
  planner_main:
    provider: ${COURSEPILOT_MAIN_PROVIDER}
    model: ${COURSEPILOT_MAIN_MODEL}
    base_url: ${COURSEPILOT_MAIN_BASE_URL}
    api_key_ref: COURSEPILOT_MAIN_API_KEY
    temperature: 0.1
    reasoning_effort: medium
    thinking_enabled: provider_default
    max_output_tokens: 6000
    timeout_seconds: 120
    max_retries: 1

  generator_main:
    inherits: planner_main
    temperature: 0.2
    reasoning_effort: medium
    max_output_tokens: 8000

  content_repair_main:
    inherits: planner_main
    temperature: 0.1
    max_output_tokens: 4000

  classifier_light:
    provider: ${COURSEPILOT_LIGHT_PROVIDER}
    model: ${COURSEPILOT_LIGHT_MODEL}
    base_url: ${COURSEPILOT_LIGHT_BASE_URL}
    api_key_ref: COURSEPILOT_LIGHT_API_KEY
    temperature: 0
    reasoning_effort: low
    thinking_enabled: false
    max_output_tokens: 1000
    timeout_seconds: 30
    max_retries: 1

  json_repair_light:
    inherits: classifier_light
    max_output_tokens: 2000

  compression_light:
    inherits: classifier_light
    max_output_tokens: 2500
```

对应环境变量：

```env
COURSEPILOT_MAIN_PROVIDER=openai-compatible
COURSEPILOT_MAIN_MODEL=
COURSEPILOT_MAIN_BASE_URL=
COURSEPILOT_MAIN_API_KEY=

COURSEPILOT_LIGHT_PROVIDER=openai-compatible
COURSEPILOT_LIGHT_MODEL=
COURSEPILOT_LIGHT_BASE_URL=
COURSEPILOT_LIGHT_API_KEY=
```

#### 13.3.5 选型标准

Main Model 重点评估：

- 中文教案、试题、PPT 文案质量；
- 复杂 Schema 的一次生成通过率；
- 长上下文和多约束遵循；
- 引用 ID 保留与 Evidence Grounding；
- 修复时保持未授权字段不变；
- 延迟、Token 和成本。

Light Model 重点评估：

- 分类准确率；
- JSON/Structured Output 成功率；
- Scope/Filter 提取准确率；
- 短文本压缩的信息保留；
- P95 延迟和单次成本。

模型不能仅凭通用榜单选择。应在 CoursePilot Dev Set 上比较：

```text
结构通过率
+ 人工内容评分
+ Grounding/Citation 指标
+ Repair 成功率
+ P95 延迟
+ 平均 Token/成本
```

#### 13.3.6 路由升级条件

MVP 不预设独立“规划模型”。仅在评测证明以下情况成立时，才增加第三个 Planner/Reasoning Model：

- Main Model 的 Blueprint 质量明显不足；
- 高推理配置能显著提高规划通过率；
- 质量收益能够抵消额外延迟和成本；
- Provider 支持稳定的按调用 Reasoning 参数。

否则 `planner_main` 继续复用 Main Model。

#### 13.3.7 显式升级与降级

- Light Model 失败可显式升级到 Main Model；
- 每次升级记录 `requested_profile`、`resolved_profile` 和原因；
- Main Generation 失败不允许静默降级成低质量模板；
- 正式评测中模型切换视为独立实验配置；
- Provider 不支持 `reasoning_effort` 或 `thinking` 时不发送相应参数，不能硬编码。

### 13.4 Fallback

- Local/Smoke：允许 Deterministic Fallback；
- Production：结构性小问题允许规则修复，但生成节点失败不得用低质量模板伪装成功；
- Evaluation：禁止 Deterministic Fallback；
- Provider 失败应记录稳定 Error Category；
- 模型切换必须显式记录，不能静默。

---

## 14. 上下文工程与状态压缩

### 14.1 Context 获取

统一采用 CourseRAG：

```text
Retrieve 30
→ Rerank 8
→ Evidence Dedup
→ Parent Expansion
→ Purpose-aware Token Packing
```

CoursePilot 不再把原始 Query 和所有检索结果直接塞入每个 Prompt。

### 14.2 ContextPackageRef

```python
class ContextPackageRef(BaseModel):
    context_id: str
    purpose: str
    course_id: str
    index_version: str
    evidence_ids: list[str]
    token_count: int
    content_hash: str
    trace_id: str
```

### 14.3 Prompt 输入最小化

每个节点只获得：

- 当前组件的 Plan；
- 目标 Knowledge Points；
- 必需 Evidence；
- 相关用户/课程偏好；
- 当前 Validation Issues。

不得把整个教案、全部试题或所有历史 Repair 内容反复放入局部生成 Prompt。

### 14.4 State Compaction

完成阶段后：

- 保留结构化 Artifact Ref；
- 保留 Summary 和 Hash；
- 移除无必要 Raw Model Message；
- 完整 Prompt/Response 由 LangSmith 和 Invocation Record 保存；
- Checkpoint 中不保存 Secret。

---

## 15. 分层校验体系

### 15.1 ValidationIssue

```python
class ValidationIssue(BaseModel):
    issue_id: str
    code: str
    severity: Literal["info", "warning", "error", "blocking"]
    layer: Literal["L0", "L1", "L2", "L3", "L4"]
    scope_type: str
    scope_id: str
    json_path: str | None
    message: str
    expected: object | None
    actual: object | None
    evidence_ids: list[str]
    repair_strategy: str
    auto_repairable: bool
```

### 15.2 ValidationReport

```python
class ValidationReport(BaseModel):
    artifact_id: str
    artifact_version: int
    validator_profile: str
    issues: list[ValidationIssue]
    passed: bool
    blocking_count: int
    error_count: int
    warning_count: int
    coverage_metrics: dict[str, float]
    created_at: datetime
```

### 15.3 五层校验

#### L0：Schema

- Pydantic；
- Enum；
- Required Field；
- 类型和长度。

#### L1：确定性局部规则

- 数量；
- 分值；
- 时间；
- Slide Type；
- 选项；
- Answer Format；
- Citation ID 存在。

#### L2：跨字段与跨组件一致性

- Blueprint 与实际数量；
- 知识点分配与覆盖；
- Lesson Plan 与 Session；
- Slide 与 Session；
- 总分、总时长；
- 术语一致性；
- 重复度。

#### L3：Grounding 与证据

- Evidence 可解析；
- 引用属于当前 Course/Version；
- 引用与目标 Knowledge Point 有关联；
- 事实性内容有来源；
- 题目答案和解析具备证据；
- Source Tier 满足策略。

L3 的语义支持不能完全由 ID 校验替代。MVP 采用规则 + 人工 Gold 评测；不引入 LLM-as-a-Judge。

#### L4：教学与业务质量

- 教学目标可测量；
- 目标—活动—评价一致；
- 难度梯度；
- 题目清晰度；
- 干扰项合理性；
- Slide 信息密度；
- 教学可用性。

L4 采用规则可检查项 + 教师人工 Checklist。

### 15.4 Issue Code

示例：

```text
LESSON_SESSION_COUNT_MISMATCH
LESSON_TIME_ALLOCATION_MISMATCH
LESSON_KP_NOT_COVERED
LESSON_OBJECTIVE_NOT_MEASURABLE
EXAM_SCORE_MISMATCH
EXAM_OPTION_COUNT_INVALID
EXAM_ANSWER_NOT_IN_OPTIONS
EXAM_KP_COVERAGE_MISSING
EXAM_DUPLICATE_QUESTION
PPT_LAYOUT_MISMATCH
PPT_CONTENT_OVERFLOW_RISK
PPT_CITATION_MISSING
PPT_SESSION_SOURCE_INVALID
GROUNDING_EVIDENCE_NOT_FOUND
GROUNDING_SOURCE_TIER_INVALID
```

---

## 16. Repair Planner 与定向修复

### 16.1 RepairPlan

```python
class RepairPlan(BaseModel):
    artifact_id: str
    source_version: int
    repair_round: int
    actions: list[RepairAction]
    max_model_calls: int
    allowed_json_paths: list[str]
    requires_full_regeneration: bool
```

```python
class RepairAction(BaseModel):
    issue_ids: list[str]
    strategy: Literal[
        "deterministic_patch",
        "regenerate_component",
        "retrieve_more_evidence",
        "model_patch",
        "human_review",
    ]
    target_scope_id: str
    target_json_paths: list[str]
    validator_subset: list[str]
```

### 16.2 Repair 优先级

1. 确定性 Patch；
2. 重新检索 Evidence；
3. 局部模型 Patch；
4. 重生成单个 Component；
5. 全局重生成；
6. Human Review。

全局重生成只能用于 Blueprint 根本无效或 Artifact 广泛损坏的情况。

### 16.3 Patch Contract

模型 Repair 不直接返回完整 Artifact，优先返回：

```python
class ArtifactPatch(BaseModel):
    operations: list[PatchOperation]
    addressed_issue_ids: list[str]
```

允许操作：

- Replace；
- Add；
- Remove；
- Regenerate Component Reference。

应用前验证：

- Path 在 Allowed Paths；
- 不修改 ID 和不可变字段；
- Patch 后 Schema Valid；
- 未触及区域 Hash 不变。

### 16.4 无回归检查

每轮 Repair 后计算：

- 已解决 Issue；
- 新增 Issue；
- 未触及区域变化；
- Artifact Diff；
- 关键指标变化。

只有 Blocking/Error 数量下降且未产生严重回归，Repair 才被接受。

---

## 17. Human Review 与审批

### 17.1 审核对象

- Lesson Blueprint；
- Lesson Draft；
- Exam Blueprint；
- Question；
- Exam Draft；
- Slide Architecture；
- Slide；
- PPT Draft；
- Verified Writeback Fragment。

### 17.2 ApprovalRecord

```python
class ApprovalRecord(BaseModel):
    approval_id: str
    task_id: str
    artifact_id: str
    artifact_version: int
    target_scope_type: str
    target_scope_ids: list[str]
    decision: Literal["approved", "changes_requested", "rejected"]
    comment: str | None
    actor_id: str
    created_at: datetime
```

### 17.3 审核与写回分离

- Artifact 被批准，不代表自动写回；
- 写回必须是第二个显式动作；
- 写回记录必须引用 Approval Record；
- 用户可批准导出但拒绝写回；
- 撤销写回不撤销原 Artifact 审核记录。

---

## 18. 数据持久化

### 18.1 现有业务表保留

现有：

- Course；
- Generation Task；
- Lesson Design；
- Exam Blueprint；
- Question；
- Slide Outline；
- Review Record；
- Export File。

迁移时通过新 Version/Run 表增强，不要求一次性重写所有表。

### 18.2 新增表建议

```text
coursepilot_workflow_runs
coursepilot_artifact_versions
coursepilot_artifact_dependencies
coursepilot_validation_reports
coursepilot_validation_issues
coursepilot_repair_runs
coursepilot_repair_actions
coursepilot_template_definitions
coursepilot_template_versions
coursepilot_model_profiles
coursepilot_approval_records
coursepilot_side_effect_records
coursepilot_context_snapshots
coursepilot_user_preferences
coursepilot_course_preferences
```

LangGraph Checkpointer 使用独立 Checkpoint 表。

### 18.3 Artifact Version

Lesson、Exam、PPT 每次：

- 生成；
- Revision；
- Repair；
- 人工修改；

都创建新 Version。业务主表保存当前 Active Version Pointer。

### 18.4 数据所有权

| 数据 | 所有者 |
|---|---|
| Course 业务信息 | CoursePilot |
| Agent Task/Graph State | CoursePilot |
| Template/Model Profile | CoursePilot |
| Lesson/Exam/PPT Artifact | CoursePilot |
| Approval/Export | CoursePilot |
| 文档解析/Knowledge Point/Evidence/Index | CourseRAG |
| Verified Content 索引 | CourseRAG |
| LangSmith Trace | LangSmith，非事实源 |

---

## 19. API 改造

### 19.1 Task API

```text
POST /api/coursepilot/v2/courses/{course_id}/lessons/tasks
POST /api/coursepilot/v2/courses/{course_id}/exams/tasks
POST /api/coursepilot/v2/lessons/{lesson_id}/ppt/tasks

GET  /api/coursepilot/v2/tasks/{task_id}
GET  /api/coursepilot/v2/tasks/{task_id}/events
POST /api/coursepilot/v2/tasks/{task_id}/resume
POST /api/coursepilot/v2/tasks/{task_id}/cancel
```

### 19.2 Artifact API

```text
GET  /api/coursepilot/v2/artifacts/{artifact_id}
GET  /api/coursepilot/v2/artifacts/{artifact_id}/versions
POST /api/coursepilot/v2/artifacts/{artifact_id}/revisions
GET  /api/coursepilot/v2/artifacts/{artifact_id}/validation
```

### 19.3 Review/Approval

```text
POST /api/coursepilot/v2/tasks/{task_id}/decisions
POST /api/coursepilot/v2/artifacts/{artifact_id}/approvals
POST /api/coursepilot/v2/artifacts/{artifact_id}/writeback
POST /api/coursepilot/v2/writebacks/{writeback_id}/revoke
```

### 19.4 Export

```text
POST /api/coursepilot/v2/artifacts/{artifact_id}/exports
GET  /api/coursepilot/v2/exports/{export_id}
GET  /api/coursepilot/v2/files/{file_id}/download
```

### 19.5 兼容策略

现有 `/api/coursepilot/*` Endpoint 暂时保留，由兼容 Service：

1. 创建 v2 Task；
2. 轮询或读取结果；
3. 映射回旧 Response Schema。

新 UI 直接使用 v2 Task/Event API。

---

## 20. 进度事件与 UI

### 20.1 Event

```python
class TaskEvent(BaseModel):
    event_id: str
    task_id: str
    event_type: str
    stage: str
    message: str
    progress: float | None
    artifact_refs: list[ArtifactRef]
    validation_summary: dict | None
    created_at: datetime
```

### 20.2 传输

- 首版保留 Polling；
- 增加 SSE 作为进度展示；
- 不需要 WebSocket；
- Human Interrupt 由 API 决策恢复，不依赖长连接。

### 20.3 UI 页面

#### 任务详情

- 当前阶段；
- Graph Timeline；
- CourseRAG Context；
- Model 调用；
- Validation Issues；
- Repair Diff；
- 人工操作；
- 导出和写回。

#### 模板

- 选择模板；
- 查看版本；
- 修改允许的参数；
- 不在 UI 中直接编辑 Secret 或底层 Prompt。

---

## 21. 导出工程

### 21.1 Exporter 原则

- LLM 只生成结构化 Artifact；
- Exporter 负责 Office 文件；
- Export 使用冻结 Artifact Version 和 Exporter Profile；
- 导出结果记录 Hash；
- 相同 Artifact Version + Exporter Profile + Idempotency Key 不重复导出。

### 21.2 DOCX

Lesson/Exam DOCX 支持：

- `.docx` 模板；
- 标题、正文、表格和页眉页脚；
- 引用附录；
- 教师版/学生版差异；
- 渲染后页数和文件可打开检查。

### 21.3 PPTX

- 基于真实模板；
- Slide Type/Layout 映射；
- Notes 和 Evidence；
- Citation Footer；
- Asset Placeholder；
- 渲染后结构检查。

---

## 22. 可观测性

### 22.1 LangSmith Trace

每个 Task 至少记录：

- `task_id`；
- `course_id`；
- `thread_id`；
- `workflow_type`；
- `template_id/version`；
- `artifact_id/version`；
- `prompt_name/hash`；
- `model_profile/provider/model`；
- CourseRAG `trace_id/index_version/context_id`；
- Node Input/Output；
- Validation Issue；
- Repair Plan/Patch；
- Token、Latency、Retry、Fallback；
- Human Interrupt；
- Export/Writeback Result。

### 22.2 PostgreSQL

保存：

- 业务状态；
- Checkpoint；
- Artifact；
- Validation；
- Repair；
- Approval；
- Side Effect；
- LangSmith Run ID/URL。

LangSmith Trace 丢失不得影响任务恢复。

### 22.3 Redaction

即使允许上传课程原文，也必须过滤：

- API Key；
- Authorization Header；
- Cookie；
- Database URL；
- Object Storage Credential；
- Internal Secret；
- 用户身份 Token。

---

## 23. 安全与可靠性

### 23.1 Authorization

所有 Task、Artifact、Template 和 Export 必须校验：

- Course 所有权；
- 用户权限；
- Artifact 归属；
- Approval Actor；
- 写回权限。

### 23.2 Prompt Injection

CourseRAG Context 被视为不可信数据：

- Prompt 明确禁止执行资料中的指令；
- Context 使用结构化 Evidence 包裹；
- 生成节点没有任意工具权限；
- 检索材料中的 Prompt Injection 只做内容，不影响 System Policy；
- 输出必须通过 Schema 和 Validator。

### 23.3 资源预算

每个 Task 保存：

- 最大模型调用数；
- 最大 Repair Round；
- 最大 Token；
- 最大 Cost；
- 最大执行时间；
- 最大并发。

预算耗尽时进入 `needs_review` 或失败，不无限循环。

### 23.4 故障分类

- CourseRAG 不可用；
- Model Timeout/Rate Limit；
- Structured Parse；
- Validation Blocking；
- Checkpoint Error；
- Export Error；
- Writeback Error；
- Human Timeout；
- Authorization Error。

每类错误明确：

- 是否可重试；
- 从哪个节点恢复；
- 是否需要人工处理；
- 是否已发生副作用。

---

## 24. 测试体系

### 24.1 Unit

- Model Router；
- Template Snapshot；
- State Fingerprint；
- Validator；
- Repair Planner；
- Patch Apply；
- No-regression；
- Duplicate Detector；
- Slide Layout Policy；
- Approval Policy；
- Idempotency。

### 24.2 Graph

每条 Graph 使用 Mock CourseRAG 和 Fake Model 测试：

- 正常路径；
- Validation Repair；
- Repair 超限；
- Interrupt/Resume；
- Checkpoint Recovery；
- Node Failure；
- Budget Exhausted；
- CourseRAG Empty Context；
- Invalid Evidence。

### 24.3 Contract

CourseRAG：

- Local Adapter；
- Remote Client；
- Mock Service。

三者使用同一 Contract Test。

### 24.4 Integration

- PostgreSQL Checkpointer；
- Background Worker；
- LangSmith Trace；
- Lesson DOCX；
- Exam DOCX；
- PPT Template Export；
- LibreOffice Render；
- Approval；
- Verified Writeback；
- Resume After Crash。

### 24.5 故障注入

- CourseRAG 500/Timeout；
- LLM 429；
- LLM 返回不合法 Schema；
- Reranker 降级；
- Checkpointer 临时不可用；
- Worker 在节点完成后、提交前崩溃；
- Exporter 生成损坏文件；
- Writeback 成功但客户端丢失响应。

---

## 25. 迁移策略

### 25.1 不一次性重写

迁移顺序：

1. 先加入 Port、Runtime 和新 DTO；
2. 保持旧 Graph 可运行；
3. 每次迁移一条工作流；
4. v1/v2 API 并存；
5. 新 UI 切到 v2；
6. 完成评测后删除 Legacy。

### 25.2 Legacy 映射

| Legacy | 新对象 |
|---|---|
| `retrieved_contexts` | `ContextPackageRef` |
| `knowledge_points: list[str]` | `KnowledgePointAllocation` |
| Boolean Validation Report | `ValidationIssue[]` |
| `repair_attempts` | `RepairRun` |
| `chunk_id Reference` | `ArtifactReference.evidence_id` |
| Random Thread | Stable Task Thread |
| 整件修复 | Component Patch |
| `review_status=approved` | Approval Record |
| Whole Artifact Writeback | Whitelisted Fragment Writeback |

### 25.3 旧数据

- 现有 Lesson/Exam/PPT 继续可读取和导出；
- 首次 Revision 时可转换为 Artifact Version v1；
- 旧 Chunk Reference 标记 Legacy；
- 不伪造 Evidence ID；
- 旧 Review Writeback 不自动迁移为新 Verified Content，除非来源和内容类型可确认。

---

## 26. 分阶段实施

### Phase 0：冻结当前 Agent 基线

**修改：**

- 固定当前 Commit 和模型配置；
- 保存当前教案、试卷、PPT 样例；
- 分离结构通过率和人工内容质量；
- 记录每个节点耗时和模型调用。

**验收：**

- 三条 Legacy Graph 可重复运行；
- 可使用固定 CourseRAG Mock；
- 现有导出文件保留。

### Phase 1：CourseRAG Port 与兼容 Adapter

**修改：**

- 引入统一 CourseRAG DTO；
- Local/Remote/Mock；
- 旧 Retrieve Node 改调用 Port；
- 教案停止再次抽取知识点。

**验收：**

- Agent 代码不导入 Chroma；
- Mock 可驱动三条 Graph；
- 旧 API 不变。

### Phase 2：Task、Artifact Version 和 Stable Thread

**修改：**

- 新 Task/Run/Artifact Version；
- Stable Thread；
- ArtifactRef；
- NodeResult/Fingerprint。

**验收：**

- 同一 Task 的重试复用 Thread；
- Artifact Revision 不覆盖旧版本；
- 可查看 Task Timeline。

### Phase 3：模型网关与模板系统

**修改：**

- Main/Light 两模型最小配置；
- Model Profile 与 Capability Router；
- Per-call Reasoning/Thinking 兼容处理；
- 系统内置逻辑模板和物理导出模板；
- Template Definition/Snapshot；
- Custom Template Import/Mapping；
- Fallback/Escalation Policy。

**验收：**

- 轻量分类不使用高推理模型；
- Main/Light Profile 可独立配置，也可映射到同一实际模型；
- 仓库自带可运行的教案、试卷和 PPT 内置模板；
- 任务可复现 Template/Prompt/Model；
- Eval 禁止静默 Fallback 或模型切换。

### Phase 4：统一 ValidationIssue 与 Repair Planner

**修改：**

- 五层 Validator；
- Issue Code；
- Repair Plan；
- Patch；
- No-regression。

**验收：**

- Validator 可定位 Scope/Path；
- Repair 只修改允许路径；
- 结果展示修复前后 Diff。

### Phase 5：教案 Graph v2

**修改：**

- Blueprint；
- CourseRAG Knowledge Points；
- Session Fan-out；
- 跨课时校验；
- Revision Patch。

**验收：**

- 不重复知识点抽取；
- 单课时错误只修复该课时；
- Knowledge Point Coverage 可追踪。

### Phase 6：试卷 Graph v2

**修改：**

- Blueprint 校验；
- Interrupt；
- Question Batch Send；
- Batch Validator；
- 全局 Duplicate/Coverage；
- Question-level Repair。

**验收：**

- 并行生成收益可测；
- 缺失/重复问题局部重生成；
- 总分和覆盖无回归。

### Phase 7：PPT Graph 与模板化导出

**修改：**

- Slide Architecture；
- Layout Mapping；
- Template PPTX；
- Notes/Citations；
- Overflow Rules；
- Render Validation。

**验收：**

- 不再只用两种默认 Layout；
- 每页可编辑；
- 每页引用可解析；
- 导出后可成功渲染。

### Phase 8：Checkpoint、Interrupt 与恢复

**修改：**

- PostgreSQL Checkpointer；
- Stable Thread；
- Human Decision API；
- Side Effect Record；
- Resume。

**验收：**

- 教案 Session Plan、试卷 Blueprint、PPT Slide Architecture 暂停后可编辑并恢复；
- 三类最终审核点均可分别授权导出和白名单写回；
- Worker 崩溃后不重复成功节点；
- 导出/写回不重复。

### Phase 9：审核写回、安全与可观测性

**修改：**

- Approval 与 Writeback 分离；
- 白名单 Fragment；
- Prompt Injection；
- ACL；
- LangSmith Redaction；
- 故障注入。

**验收：**

- 未批准内容不可写回；
- 整件 Artifact 不写回；
- Secret 不进入 Trace；
- 关键故障可恢复或明确失败。

### Phase 10：评测与收尾

- CoursePilot 与系统级评测；
- README；
- 架构图；
- Demo；
- 简历指标；
- 面试问题库。

---

## 27. 推荐 PR 序列

```text
PR-01  Freeze legacy agent baselines
PR-02  Add CourseRAG ports and mock adapter
PR-03  Add task runtime, artifact versions, stable thread IDs
PR-04  Add model gateway and template registry
PR-05  Introduce ValidationIssue and validator registry
PR-06  Add repair planner, patching, and no-regression checks
PR-07  Migrate lesson workflow to v2
PR-08  Migrate exam blueprint and human interrupt
PR-09  Add parallel question generation and targeted repair
PR-10  Add PPT architecture and template-based exporter
PR-11  Add PostgreSQL checkpointer and workflow resume
PR-12  Separate approvals, exports, and verified writeback
PR-13  Add LangSmith tracing, redaction, and fault injection
PR-14  Complete evaluation hooks and v2 APIs
PR-15  Remove legacy agent internals after compatibility window
```

每个 PR 必须：

- 保持 Legacy 或 v2 至少一条可运行路径；
- 有迁移和回滚说明；
- 有 Unit/Graph/Integration Test；
- 更新 Template/Schema/Prompt Version；
- 标明对评测基线的影响。

---

## 28. Definition of Done

### 架构

- CoursePilot 仅通过 Port 使用 CourseRAG；
- 三条 Graph 使用统一 Runtime；
- State、Artifact、Validation、Repair 和 Approval 合同明确；
- Local/Remote/Mock CourseRAG 行为一致。

### 工作流

- 教案具备 Blueprint、Session Component 和局部 Revision；
- 试卷具备 Blueprint Interrupt、并行生成和 Question-level Repair；
- PPT 具备 Slide Architecture、Template Layout 和渲染检查。

### 校验修复

- 五层 Validation；
- 结构化 Issue；
- 定向 Repair；
- No-regression；
- Repair Budget。

### 可靠性

- PostgreSQL Checkpoint；
- Stable Thread；
- Interrupt/Resume；
- Side Effect Idempotency；
- Worker Crash Recovery；
- 故障注入测试。

### 模型工程

- Per-node Model Profile；
- Prompt/Schema/Model 可追溯；
- 评测禁用静默 Fallback；
- Token/Latency/Cost 可统计。

### 模板与导出

- Template Snapshot；
- DOCX/PPTX 模板；
- PPT 多 Layout；
- Notes/Citation；
- Export Idempotency；
- 文件可打开和可渲染。

### 人工闭环

- Approval 与 Writeback 分离；
- 白名单写回；
- 支持撤销；
- 所有人工决策可审计。

### 可观测性和安全

- LangSmith 覆盖完整 Task；
- PostgreSQL 保留业务事实；
- Secret Redaction；
- ACL；
- Prompt Injection 防护。

---

## 29. 当前默认技术结论

- 保持 Workflow-first，不建设自由自治多 Agent；
- 新建统一 Agent Runtime，逐条迁移现有 Graph；
- CoursePilot 不再从检索 Context 抽取课程知识点；
- Stable Thread 使用 `task_id`；
- 三条 Graph 接入 PostgreSQL Checkpointer；
- Exam Blueprint 和最终审批使用 Interrupt；
- Lesson Session 与 Question Batch 可受控并行；
- Validator 使用 `ValidationIssue` 而不是布尔集合；
- Repair 默认返回局部 Patch；
- 全局重生成只作为最后手段；
- Template、Prompt、Schema、Validator、Model、Exporter 全部版本化；
- 模型 Reasoning/Thinking 按节点配置，不全局强制 High；
- 正式评测禁用 Deterministic Fallback；
- Context 通过 CourseRAG Purpose-aware Package 获取；
- 新引用使用 `evidence_id`，Legacy `chunk_id` 仅兼容；
- PPT 使用真实 PPTX Template 和多 Layout；
- PPT 定位为可编辑教学初稿；
- Approval 与 Verified Writeback 分离；
- 只写回题目、答案解析和教案片段；
- LangSmith 是 Trace，不是业务数据库；
- 先完成逻辑改造和独立评测，再物理拆分 CourseRAG。
