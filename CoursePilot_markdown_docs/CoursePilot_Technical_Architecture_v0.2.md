# CoursePilot 技术架构设计文档 v0.2

## 基于 Agent Service Toolkit 改造的 Teacher Assistant Agent 系统

# 文档目标

本文档基于 CoursePilot PRD v0.1，从工程实现角度明确 MVP 阶段的技术架构、技术选型、模块边界、数据流、Agent Workflow 设计、存储设计、接口设计、校验机制与部署方案。

本文档用于指导后续技术开发、代码结构设计、任务拆解和项目 README 编写。

# MVP 技术目标

MVP 阶段不追求企业级复杂架构，而追求以下目标：

1.  能完整跑通教师备课主流程；
2.  能上传教材和课程大纲并构建私有知识库；
3.  能基于 RAG 生成教学设计；
4.  能基于教学设计生成 PPT 初稿；
5.  能生成作业/试卷、答案、解析和答题卡；
6.  能导出 docx / pptx 文件；
7.  能体现 workflow-first Agent 架构；
8.  能体现 plan-and-solve、ReAct-style tool use、reflection / critic；
9.  能体现结构化输出、schema 校验、重试、引用溯源和重复度检测；
10. 能作为简历项目完整展示。

# 1. 架构决策

CoursePilot MVP 不再完全从零搭建，而是采用 Agent Service Toolkit 作为主工程底座。

主底座承担：

11. FastAPI Agent Service；
12. Streamlit Demo UI；
13. Python Client；
14. LangGraph Agent 注册与调用；
15. 流式与非流式调用；
16. Pydantic schema；
17. 模型配置；
18. Docker Compose；
19. 测试框架；
20. LangGraph memory / checkpointer 基础能力。

Langchain-Chatchat 不作为主底座，仅作为 RAG/知识库模块的工程参考，重点参考：

1.  文档入库流程；
2.  文件加载器设计；
3.  文本切分器设计；
4.  知识库服务抽象；
5.  本地知识库与临时知识库的区分；
6.  检索结果引用格式；
7.  工具注册与知识库检索工具设计。

# 2. 总体技术选型

| 层级        | 修订后选型                                     | 说明                                                      |
|-------------|------------------------------------------------|-----------------------------------------------------------|
| 主工程底座  | Agent Service Toolkit                          | 直接 fork 改造                                            |
| 前端        | Streamlit，沿用并改造原 `src/streamlit_app.py` | 增加课程管理、资料上传、教学设计、试卷生成、PPT 生成页面  |
| 后端服务    | FastAPI，沿用原 `src/service/service.py`       | 新增 CoursePilot 业务路由                                 |
| Agent 编排  | LangGraph                                      | 在 `src/agents/` 下新增 CoursePilot 相关 graph            |
| Schema 校验 | Pydantic                                       | 沿用原项目 schema 风格，新增业务 schema                   |
| 客户端      | 原 `AgentClient` + CoursePilot API Client      | 原 client 保留，新业务可以增加 client 方法                |
| 关系数据库  | PostgreSQL                                     | 复用原 compose 中 Postgres，新增业务表                    |
| 向量数据库  | Chroma                                         | 沿用原 RAG assistant 的 Chroma 方向，改造为动态课程知识库 |
| 文档解析    | PyMuPDF + python-docx + Markdown/TXT parser    | 可参考 Chatchat loader 设计，但不整体迁移                 |
| Word 导出   | python-docx                                    | 新增 exporter                                             |
| PPT 导出    | python-pptx                                    | 新增 exporter                                             |
| 后台任务    | FastAPI BackgroundTasks + task 表              | MVP 不引入 Celery                                         |
| 部署        | Docker Compose                                 | 复用 Agent Service Toolkit 的 Docker 结构                 |
| 测试        | pytest                                         | 沿用原 tests 结构，新增业务测试                           |

# 3. 改造策略

## 3.1 不重写原服务框架

保留 Agent Service Toolkit 的基础结构：

    src/
    ├── agents/
    ├── client/
    ├── core/
    ├── memory/
    ├── schema/
    ├── service/
    ├── streamlit_app.py
    └── run_service.py

在此基础上新增 CoursePilot 业务模块：

    src/coursepilot/
    ├── api/
    ├── models/
    ├── schemas/
    ├── services/
    ├── rag/
    ├── validators/
    ├── exporters/
    ├── evals/
    └── utils/

同时在原 `src/agents/` 下新增 CoursePilot Agent Graph：

    src/agents/coursepilot/
    ├── graphs/
    │   ├── lesson_graph.py
    │   ├── exam_graph.py
    │   ├── ppt_graph.py
    │   └── kb_build_graph.py
    ├── nodes/
    │   ├── retrieve_nodes.py
    │   ├── lesson_nodes.py
    │   ├── exam_nodes.py
    │   ├── ppt_nodes.py
    │   ├── validation_nodes.py
    │   └── repair_nodes.py
    └── states/
        ├── lesson_state.py
        ├── exam_state.py
        └── ppt_state.py

# 4. 修改后的系统分层

    Streamlit UI Layer
      ├── 原聊天界面
      └── CoursePilot 业务页面

    Client Layer
      ├── 原 AgentClient
      └── CoursePilotClient optional

    FastAPI Service Layer
      ├── 原 /invoke /stream /info /history
      └── 新增 /api/coursepilot/*

    Application Service Layer
      ├── CourseService
      ├── DocumentService
      ├── KnowledgeBaseService
      ├── LessonService
      ├── ExamService
      ├── PPTService
      ├── ReviewService
      └── ExportService

    Agent Workflow Layer
      ├── KBBuildGraph
      ├── LessonPlanningGraph
      ├── ExamGenerationGraph
      └── PPTGenerationGraph

    RAG Layer
      ├── Parser
      ├── Chunker
      ├── MetadataExtractor
      ├── EmbeddingClient
      ├── ChromaVectorStore
      └── Retriever

    Storage Layer
      ├── PostgreSQL
      ├── Chroma
      └── Local storage

    Harness Engineering Layer
      ├── Pydantic schemas
      ├── Validators
      ├── Repair nodes
      ├── Duplicate detector
      ├── Citation checker
      └── Evaluation scripts

# 5. 复用 Agent Service Toolkit 的内容

## 5.1 直接保留

以下模块建议直接保留：

    src/service/service.py
    src/client/client.py
    src/core/settings.py
    src/core/llm.py
    src/memory/
    src/schema/
    src/agents/agents.py
    compose.yaml
    docker/
    tests/

## 5.2 需要改造

| 原模块                   | 改造方式                                                     |
|--------------------------|--------------------------------------------------------------|
| `src/streamlit_app.py`   | 增加 CoursePilot 业务页面，或拆出 `src/coursepilot/ui/` 页面 |
| `src/agents/agents.py`   | 注册 CoursePilot 相关 Agent Graph                            |
| `src/schema/`            | 新增或扩展 CoursePilot 业务 schema                           |
| `src/service/service.py` | 挂载 CoursePilot 业务 router                                 |
| `compose.yaml`           | 增加 Chroma 持久化目录、storage volume、业务环境变量         |
| `.env.example`           | 增加 CoursePilot 相关配置                                    |

## 5.3 可删除或暂时隐藏

为了降低 MVP 复杂度，可以暂时隐藏或不改造：

1.  语音输入输出；
2.  天气工具；
3.  GitHub MCP agent；
4.  与 CoursePilot 无关的示例 agent；
5.  不需要的第三方工具。

建议做法不是立刻删除，而是在 UI 中只展示 CoursePilot 入口，原示例 agent 保留在代码中作为参考。

# 6. CoursePilot API 设计

在原 FastAPI service 中新增业务 router：

    src/coursepilot/api/
    ├── routes_courses.py
    ├── routes_documents.py
    ├── routes_kb.py
    ├── routes_lessons.py
    ├── routes_exams.py
    ├── routes_ppt.py
    ├── routes_reviews.py
    └── routes_files.py

统一前缀：

    /api/coursepilot

核心接口：

    POST /api/coursepilot/courses
    GET  /api/coursepilot/courses
    POST /api/coursepilot/courses/{course_id}/documents/upload
    POST /api/coursepilot/documents/{document_id}/build-kb
    POST /api/coursepilot/courses/{course_id}/kb/search

    POST /api/coursepilot/courses/{course_id}/lessons/generate
    GET  /api/coursepilot/lessons/{lesson_id}
    POST /api/coursepilot/lessons/{lesson_id}/revise
    POST /api/coursepilot/lessons/{lesson_id}/export

    POST /api/coursepilot/courses/{course_id}/exams/blueprint
    POST /api/coursepilot/exams/{blueprint_id}/confirm
    POST /api/coursepilot/exams/{blueprint_id}/generate
    POST /api/coursepilot/exams/{blueprint_id}/export

    POST /api/coursepilot/lessons/{lesson_id}/ppt/generate
    POST /api/coursepilot/ppt/{outline_id}/export

    POST /api/coursepilot/reviews
    POST /api/coursepilot/reviews/{review_id}/write-back
    GET  /api/coursepilot/files/{file_id}/download

# 7. CoursePilot 数据库设计

## 7.1 核心表

复用 Agent Service Toolkit compose 中的 PostgreSQL，新增业务表：

    coursepilot_courses
    coursepilot_documents
    coursepilot_chunks
    coursepilot_generation_tasks
    coursepilot_lesson_designs
    coursepilot_exam_blueprints
    coursepilot_questions
    coursepilot_slide_outlines
    coursepilot_export_files
    coursepilot_review_records

为了避免和原项目已有 memory/checkpointer 表冲突，所有 CoursePilot 业务表统一加 `coursepilot``_` 前缀。

## 7.2 courses

存储课程信息。

主要字段：

    id
    course_name
    course_type
    student_level
    student_background
    description
    created_at
    updated_at

## 7.3 documents

存储上传资料信息。

主要字段：

    id
    course_id
    file_name
    file_path
    file_type
    source_type
    parse_status
    error_message
    created_at
    updated_at

## 7.4 knowledge_chunks

存储 chunk metadata。正文可存 PostgreSQL，也可主要存 Chroma，PostgreSQL 存摘要和 metadata。

主要字段：

    id
    course_id
    document_id
    source_type
    chapter
    section
    page
    title
    content_preview
    knowledge_points_json
    verified
    chroma_collection
    chroma_doc_id
    created_at

## 7.5 generation_tasks

存储生成任务状态。

主要字段：

    id
    course_id
    task_type
    status
    input_params_json
    intermediate_outputs_json
    validation_report_json
    error_message
    created_at
    updated_at

## 7.6 lesson_designs

存储教学设计。

主要字段：

    id
    course_id
    task_id
    chapter
    status
    total_sessions
    content_json
    validation_report_json
    created_at
    updated_at

## 7.7 slide_outlines

存储 PPT 大纲。

主要字段：

    id
    course_id
    task_id
    lesson_design_id
    status
    outline_json
    validation_report_json
    pptx_file_id
    created_at
    updated_at

## 7.8 exam_blueprints

存储试卷蓝图。

主要字段：

    id
    course_id
    task_id
    chapter_range
    status
    blueprint_json
    created_at
    updated_at

## 7.9 questions

存储题目。

主要字段：

    id
    course_id
    exam_blueprint_id
    question_type
    knowledge_point
    difficulty
    score
    question_text
    options_json
    correct_answer
    explanation
    references_json
    status
    created_at
    updated_at

## 7.10 export_files

存储导出文件信息。

主要字段：

    id
    course_id
    task_id
    file_type
    file_name
    file_path
    file_role
    created_at

file_role 示例：

    lesson_docx
    pptx
    student_exam
    teacher_answer
    detailed_explanation
    answer_sheet

## 7.11 review_records

存储审核记录。

主要字段：

    id
    course_id
    target_type
    target_id
    review_status
    comment
    created_at

# 8. RAG 模块设计

## 8.1 基础策略

MVP 采用 Chroma 作为向量库。

与原 Agent Service Toolkit RAG assistant 不同，CoursePilot 不使用静态 `scripts/create_chroma_db.py` 一次性建库，而是改造为动态上传入库：

    Upload document
      → parse document
      → split chunks
      → extract metadata
      → generate embeddings
      → write to Chroma
      → write chunk metadata to PostgreSQL

## 8.2 参考 Langchain-Chatchat 的部分

参考但不直接继承：

1.  `KnowledgeFile` 思路：把上传文件封装为统一对象；
2.  loader 机制：不同文件类型使用不同 parser；

<!-- -->

21. text splitter 思路：
    1.  采用混合切分：
        1.  优先按章节标题切分；
        2.  再按段落切分；
        3.  最后按 token 长度补切；
        4.  保留 page、chapter、section 等 metadata；
        5.  chunk 之间设置 overlap。

<!-- -->

3.  KBService 思路：封装知识库增删改查；
4.  local_kb / temp_kb 思路：长期课程资料与临时材料区分；
5.  引用格式：检索结果统一携带 source、page、chunk_id。

## 8.3 CoursePilot 检索接口

    retriever.search(
        course_id: str,
        query: str,
        chapter: str | None = None,
        source_type: str | None = None,
        verified_only: bool | None = None,
        top_k: int = 5
    )

返回结构：

    {
      "chunk_id": "chunk_001",
      "course_id": "course_001",
      "source_type": "textbook",
      "chapter": "第3章",
      "section": "3.1",
      "page": 45,
      "content": "...",
      "score": 0.83,
      "verified": false
    }

# 9. Agent Workflow 设计

## 9.1 Graph 注册方式

在 `src/agents/agents.py` 中注册：

    "coursepilot-lesson-agent": Agent(...),
    "coursepilot-exam-agent": Agent(...),
    "coursepilot-ppt-agent": Agent(...),

同时，业务 API 可以不直接走聊天式 `/invoke`，而是由 CoursePilot Service 调用对应 Graph。

也就是说，保留两种调用方式：

1.  面向通用演示：`/coursepilot-lesson-agent/invoke`
2.  面向产品流程：`/api/coursepilot/courses/{course_id}/lessons/generate`

## 9.2 LessonPlanningGraph

### 目标

基于课程知识库生成教学设计。

### Graph 节点

    load_lesson_params
      ↓
    retrieve_course_context
      ↓
    extract_knowledge_points
      ↓
    plan_sessions
      ↓
    generate_lesson_design
      ↓
    validate_lesson_design
      ↓
    should_repair?
          ├── yes → reflect_and_revise → validate_lesson_design
          └── no  → save_lesson_design

体现：

1.  Workflow 主干；
2.  Plan-and-Solve：先课时规划，再生成教案；
3.  RAG：检索教材和大纲；
4.  Reflection：校验后修复；
5.  Human-in-the-loop：教师审核。
6.  ReAct-style：局部修改教学设计时动态检索并替换内容

## 9.3 ExamGenerationGraph

### 目标

生成作业/试卷、答案、解析和答题卡。

### Graph 节点

    load_exam_params
      ↓
    retrieve_course_context
      ↓
    plan_exam_blueprint
      ↓
    save_blueprint_for_human_confirm
      ↓
    generate_questions_by_type
      ↓
    validate_questions
      ↓
    should_repair?
          ├── yes → repair_questions → validate_questions
          └── no  → export_exam_files
      ↓
    save_questions

体现：

1.  Plan-and-Solve：先生成 blueprint；
2.  ReAct-style repair：题量不足、考点缺失、引用缺失时重新检索并补题；
3.  Reflection：题目质量校验；
4.  Harness engineering：schema、题量、分值、答案、重复度、引用校验。】
5.  Human-in-the-loop blueprint 确认、题目审核

## 9.4 PPTGenerationGraph

### 目标

基于教学设计生成 PPT 大纲和 pptx 文件。

### Graph 节点

    load_lesson_design
      → generate_slide_outline
      → validate_slide_outline
      → repair_slide_outline_if_needed
      → build_pptx
      → save_export_file

### 设计原则

1.  LLM 只生成 slide outline JSON；

2.  pptx 由 python-pptx 生成；

3.  PPT 模板固定；

4.  MVP 中 PPT 不追求视觉复杂度，只要求可编辑、结构完整、内容与教学设计一致。

# 10. Prompt 管理设计

Prompt 不应散落在业务代码中，建议集中放在单独的目录下，每类任务单独维护：

    lesson/
      extract_knowledge_points.md
      plan_sessions.md
      generate_lesson_design.md
      revise_lesson_design.md

    ppt/
      generate_slide_outline.md
      repair_slide_outline.md

    exam/
      plan_exam_blueprint.md
      generate_single_choice.md
      generate_multiple_choice.md
      generate_judgement.md
      generate_short_answer.md
      repair_questions.md

    repair/
      fix_json.md
      add_missing_references.md
      regenerate_missing_questions.md

Prompt 模板需要支持变量注入：

    {course_name}
    {chapter_range}
    {teacher_params}
    {retrieved_context}
    {schema}
    {existing_questions}
    {validation_errors}

# 11. 结构化输出与校验设计

## 11.1 核心原则

22. LLM 输出必须是 JSON；
23. JSON 必须通过 Pydantic 校验；
24. 校验失败后进入 repair；
25. repair 最多执行 2 轮；
26. 仍失败则返回用户可理解的错误。

## 11.2 教学设计校验

校验项：

    session_count_valid
    time_allocation_valid
    required_fields_valid
    knowledge_coverage_valid
    citation_valid
    schema_valid

## 11.3 PPT 大纲校验

校验项：

    slide_count_valid
    slide_type_valid
    content_not_empty
    source_session_valid
    citation_valid
    schema_valid

## 11.4 试卷题目校验

校验项：

    question_count_valid
    score_valid
    option_valid
    answer_valid
    explanation_valid
    knowledge_coverage_valid
    duplicate_rate
    citation_valid
    schema_valid

# 12. 文件导出设计

新增：

    src/coursepilot/exporters/
    ├── lesson_docx_exporter.py
    ├── exam_docx_exporter.py
    ├── answer_docx_exporter.py
    ├── explanation_docx_exporter.py
    ├── answer_sheet_exporter.py
    └── pptx_exporter.py

原则：

    LLM 输出 JSON
      → Pydantic 校验
      → Exporter 渲染
      → 保存到 storage/exports
      → 生成 download URL

LLM 不直接生成 docx/pptx 文件。

# 13. Streamlit UI 改造

建议新增 CoursePilot 专用页面，而不是继续沿用纯聊天页面。

页面结构：

    CoursePilot Dashboard
    ├── 课程管理
    ├── 资料上传与知识库构建
    ├── 知识库检索测试
    ├── 教学设计生成
    ├── 试卷/作业生成
    ├── PPT 生成
    ├── 审核与写回
    └── 历史任务与文件下载

如果时间紧张，第一版可以仍然放在 `src/streamlit_app.py` 中，通过 sidebar 分页实现。

后续再拆成：

    src/coursepilot/ui/pages/

# 14. Chatchat 参考内容的使用边界

允许参考：

1.  RAG 入库流程；
2.  loader / splitter 设计思想；
3.  KBService 抽象；
4.  本地知识库与临时知识库的分层；
5.  知识库检索工具的接口设计；
6.  引用格式设计。

不建议直接迁移：

1.  完整 WebUI；
2.  完整配置系统；
3.  MCP 管理；
4.  多模型平台管理；
5.  Agent 执行器；
6.  全套数据库结构；
7.  全套知识库管理 API。

# 15. 部署设计

## 15.1 Docker Compose 服务

    coursepilot-api
    coursepilot-frontend
    postgres
    chroma

## 15.2 本地开发启动

    docker-compose up -d postgres chroma
    uvicorn app.main:app --reload
    streamlit run frontend/streamlit_app.py

## 15.3 环境变量

`.``env``.example`：

    DATABASE_URL=postgresql://user:password@localhost:5432/coursepilot
    CHROMA_HOST=localhost
    CHROMA_PORT=8000
    LLM_BASE_URL=
    LLM_API_KEY=
    LLM_MODEL=
    EMBEDDING_MODEL=
    STORAGE_DIR=./storage
    MAX_REPAIR_ROUNDS=2
    DUPLICATE_THRESHOLD=0.85

# 16. 测试设计

## 16.1 单元测试

重点测试：

27. PDF 解析；
28. DOCX 解析；
29. chunk 切分；
30. Pydantic schema；
31. 题目 validator；
32. 引用 validator；
33. 重复度检测；
34. docx exporter；
35. pptx exporter。

## 16.2 集成测试

重点测试：

36. 上传文件 → 构建知识库；
37. 检索知识库；
38. 生成教学设计；
39. 生成试卷；
40. 导出 docx；
41. 生成 PPT；
42. 导出 pptx。

## 16.3 E2E Demo 测试

使用一门示例课程资料，完整跑通：

    上传课程资料
    → 构建知识库
    → 生成教学设计
    → 生成 PPT
    → 生成试卷
    → 导出文件
    → 审核写回知识库

# 17. 修订后的 MVP 完成标准

MVP 完成时需要满足：

1.  基于 Agent Service Toolkit 成功启动 FastAPI + Streamlit；
2.  可以创建课程；
3.  可以上传教材和课程大纲；
4.  可以动态构建 Chroma 课程知识库；
5.  可以检索课程资料并返回 chunk 引用；
6.  可以生成教学设计；
7.  可以执行教学设计校验和修复；
8.  可以生成试卷 blueprint；
9.  可以按题型生成题目；
10. 可以完成题量、分值、答案、解析、重复度校验；
11. 可以导出 docx；
12. 可以生成 PPT 大纲并导出 pptx；
13. 可以审核并写回知识库；

<!-- -->

43. 可以通过 Docker Compose 启动；

<!-- -->

14. 可以通过 README 复现实验流程。
15. README 中说明本项目基于 Agent Service Toolkit 改造，并标注 Chatchat 的参考作用。
