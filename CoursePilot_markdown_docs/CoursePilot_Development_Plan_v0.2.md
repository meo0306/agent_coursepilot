# CoursePilot 模块级开发任务清单 v0.2

## 基于 Agent Service Toolkit 的 MVP 开发路线

# Phase 0：Fork 主底座与项目初始化

## 目标

基于 Agent Service Toolkit 初始化 CoursePilot 工程，保留可复用的 Agent 服务能力，并建立 CoursePilot 业务模块目录。

## T0-001 Fork Agent Service Toolkit

优先级：P0

任务内容：

1.  Fork 或 clone Agent Service Toolkit；
2.  修改项目名称为 CoursePilot；
3.  更新 README 项目介绍；
4.  保留原 LICENSE；
5.  在 README 中注明项目基于 Agent Service Toolkit 改造。

验收标准：

1.  本地可以启动原 FastAPI 服务；
2.  本地可以启动原 Streamlit app；
3.  README 已改为 CoursePilot 项目说明。

## T0-002 清理和隐藏无关 Demo 功能

优先级：P1

任务内容：

1.  暂时保留原示例 agent；
2.  在 UI 中隐藏无关 agent；
3.  保留 research_assistant、rag_assistant 作为参考；
4.  暂时不启用语音、天气、GitHub MCP 等非必要功能。

验收标准：

1.  UI 默认进入 CoursePilot 页面；
2.  原示例功能不影响主流程；
3.  后续仍可参考原 agent 实现。

## T0-003 新增 CoursePilot 业务目录

优先级：P0

新增目录：

    src/coursepilot/
    ├── api/
    ├── models/
    ├── schemas/
    ├── services/
    ├── rag/
    ├── validators/
    ├── exporters/
    ├── evals/
    ├── ui/
    └── utils/

验收标准：

1.  目录创建完成；
2.  可以被 Python 正常 import；
3.  与原 `src/agents/`、`src/service/` 不冲突。

## T0-004 配置 CoursePilot 环境变量

优先级：P0

任务内容：

1.  修改 `.env.example`；
2.  增加 Chroma 持久化目录；
3.  增加 storage 路径；
4.  增加 max repair rounds；
5.  增加 duplicate threshold；
6.  增加 CoursePilot 开关配置。

示例：

    COURSEPILOT_STORAGE_DIR=./storage
    COURSEPILOT_CHROMA_DIR=./chroma_db
    COURSEPILOT_MAX_REPAIR_ROUNDS=2
    COURSEPILOT_DUPLICATE_THRESHOLD=0.85

验收标准：

1.  配置可读取；
2.  缺失配置时有默认值；
3.  README 中说明配置方式。

## T0-005 修改 Docker Compose

优先级：P0

任务内容：

1.  保留原 Postgres；
2.  保留 agent_service；
3.  保留 streamlit_app；
4.  增加 storage volume；
5.  增加 Chroma 数据目录 volume；
6.  必要时增加 chroma service。

验收标准：

1.  `docker compose up` 可以启动；
2.  上传文件不会因容器重启丢失；
3.  Chroma 数据可持久化。

# Phase 1：课程管理与动态知识库

## 目标

实现 CoursePilot 的课程、资料上传、文档解析、chunk 切分、Chroma 入库和检索能力。

## T1-001 新增 Course 数据模型

优先级：P0

位置：

    src/coursepilot/models/course.py
    src/coursepilot/schemas/course_schema.py

任务内容：

1.  定义 Course ORM 模型；
2.  定义 CourseCreate、CourseRead；
3.  表名使用 `coursepilot_courses`；
4.  支持课程名、课程类型、学生层次、课程说明。

验收标准：

1.  表可创建；
2.  API 可创建课程；
3.  课程可被后续模块引用。

## T1-002 新增 Course API

优先级：P0

接口：

    POST /api/coursepilot/courses
    GET  /api/coursepilot/courses
    GET  /api/coursepilot/courses/{course_id}
    PUT  /api/coursepilot/courses/{course_id}
    DELETE /api/coursepilot/courses/{course_id}

验收标准：

1.  可以创建课程；
2.  可以查询课程；
3.  可以更新课程；
4.  可以删除课程。

## T1-003 新增 Document 数据模型与上传 API

优先级：P0

位置：

    src/coursepilot/models/document.py
    src/coursepilot/api/routes_documents.py

接口：

    POST /api/coursepilot/courses/{course_id}/documents/upload

任务内容：

1.  支持 PDF、DOCX、TXT、MD；
2.  保存到 `storage/uploads`；
3.  创建 `coursepilot_documents` 记录；
4.  标记 parse_status。

验收标准：

1.  文件可上传；
2.  数据库有记录；
3.  文件类型错误时返回清晰错误。

## T1-004 实现 Parser 抽象与具体 Parser

优先级：P0

位置：

    src/coursepilot/rag/parsers/

任务内容：

1.  BaseParser；
2.  PDFParser；
3.  DOCXParser；
4.  MarkdownParser；
5.  TXTParser。

参考：

1.  Chatchat 的 document loader 分层思想；
2.  不直接迁移全部 loader。

验收标准：

1.  文本型 PDF 可解析；
2.  DOCX 可解析；
3.  MD/TXT 可解析；
4.  输出统一 ParsedDocument。

## T1-005 实现 Chunker

优先级：P0

位置：

    src/coursepilot/rag/chunker.py

任务内容：

1.  按标题、段落、长度混合切分；
2.  保留 page、chapter、section；
3.  chunk_size 默认 800-1200 中文字符；
4.  overlap 默认 100-200 中文字符。

验收标准：

1.  长文档可以切分；
2.  chunk 元数据完整；
3.  支持后续向量入库。

## T1-006 实现 Chroma VectorStore

优先级：P0

位置：

    src/coursepilot/rag/vector_store.py

任务内容：

1.  初始化 collection；
2.  写入 chunk；
3.  写入 metadata；
4.  支持 course_id 过滤；
5.  支持 chapter、source_type、verified 过滤。

验收标准：

1.  chunk 可写入 Chroma；
2.  query 可返回相似 chunk；
3.  不同 course_id 不混淆。

## T1-007 实现 KnowledgeBaseService

优先级：P0

位置：

    src/coursepilot/services/kb_service.py

任务内容：

1.  封装 parse；
2.  封装 chunk；
3.  封装 embedding；
4.  封装 vector store 写入；
5.  封装 PostgreSQL metadata 写入；
6.  支持重新构建某个文档。

参考：

1.  Chatchat 的 KBService 抽象；
2.  但只实现 CoursePilot 所需最小能力。

验收标准：

1.  上传文件后可以构建知识库；
2.  构建失败有错误信息；
3.  构建成功后可检索。

## T1-008 实现 KB Search API

优先级：P0

接口：

    POST /api/coursepilot/courses/{course_id}/kb/search

验收标准：

1.  可输入 query；
2.  可选择 top_k；
3.  可按章节过滤；
4.  返回 chunk_id、source_type、chapter、page、score。

## T1-009 实现 Streamlit 知识库页面

优先级：P0

页面内容：

1.  课程选择；
2.  文件上传；
3.  知识库构建按钮；
4.  构建状态展示；
5.  检索测试框；
6.  检索结果引用展示。

验收标准：

1.  用户可完成上传到检索的全流程；
2.  检索结果可视化展示。

# Phase 2：教学设计 Agent

## 目标

实现基于 RAG 的教学设计生成 workflow。

## T2-001 新增 Lesson Schema

优先级：P0

位置：

    src/coursepilot/schemas/lesson_schema.py

包含：

1.  LessonGenerationParams；
2.  RetrievedContext；
3.  KnowledgePoint；
4.  SessionPlan；
5.  LessonDesign；
6.  LessonValidationReport。

验收标准：

1.  Pydantic 校验可用；
2.  能生成 JSON schema；
3.  可用于 LLM structured output。

## T2-002 新增 LessonPlanningGraph

优先级：P0

位置：

    src/agents/coursepilot/graphs/lesson_graph.py

节点：

    load_params
    retrieve_course_context
    extract_knowledge_points
    plan_sessions
    generate_lesson_design
    validate_lesson_design
    reflect_and_revise
    save_lesson_design

验收标准：

1.  graph 可运行；
2.  每个节点输入输出明确；
3.  失败时能写 task 状态。

## T2-003 注册 CoursePilot Lesson Agent

优先级：P0

修改：

    src/agents/agents.py

新增：

    coursepilot-lesson-agent

验收标准：

1.  `/info` 能看到新 agent；
2.  `/coursepilot-lesson-agent/invoke` 可调用；
3.  业务 API 也可直接调用 graph。

## T2-004 实现 Lesson API

优先级：P0

接口：

    POST /api/coursepilot/courses/{course_id}/lessons/generate
    GET  /api/coursepilot/lessons/{lesson_id}
    POST /api/coursepilot/lessons/{lesson_id}/revise
    POST /api/coursepilot/lessons/{lesson_id}/export

验收标准：

1.  可以生成教学设计；
2.  可以查看教学设计；
3.  可以局部修改；
4.  可以导出 docx。

## T2-005 实现 Lesson Validator 与 Repair

优先级：P0

位置：

    src/coursepilot/validators/lesson_validator.py
    src/agents/coursepilot/nodes/repair_nodes.py

校验：

1.  schema；
2.  课时数量；
3.  时间分配；
4.  知识点覆盖；
5.  引用完整性。

验收标准：

1.  生成校验报告；
2.  可自动修复轻微问题；
3.  最多修复 2 轮。

## T2-006 实现教学设计页面

优先级：P0

页面内容：

1.  课程选择；
2.  章节输入；
3.  课时数；
4.  教学模板；
5.  学生层次；
6.  生成按钮；
7.  教学设计展示；
8.  校验报告展示；
9.  局部修改入口；
10. 导出按钮。

验收标准：

1.  用户可从 UI 生成教学设计；
2.  可查看引用；
3.  可下载教学设计 docx。

# Phase 3：试卷/作业生成 Agent

## 目标

实现考点规划、blueprint、分题型生成、题目校验、补题修复和 docx 导出。

## T3-001 新增 Exam Schema

优先级：P0

位置：

    src/coursepilot/schemas/exam_schema.py
    src/coursepilot/schemas/question_schema.py

包含：

1.  ExamGenerationParams；
2.  ExamBlueprint；
3.  QuestionGroupPlan；
4.  Question；
5.  QuestionSet；
6.  ExamValidationReport。

验收标准：

1.  题型、题量、分值、难度可表达；
2.  客观题和主观题均可表达；
3.  校验报告可表达错误。

## T3-002 新增 ExamGenerationGraph

优先级：P0

位置：

    src/agents/coursepilot/graphs/exam_graph.py

节点：

    load_exam_params
    retrieve_exam_context
    plan_exam_blueprint
    save_blueprint
    generate_questions_by_type
    validate_questions
    repair_questions
    save_questions
    export_exam_files

验收标准：

1.  可生成 blueprint；
2.  可按题型生成题目；
3.  可校验和修复；
4.  可导出文件。

## T3-003 实现 Exam API

优先级：P0

接口：

    POST /api/coursepilot/courses/{course_id}/exams/blueprint
    POST /api/coursepilot/exams/{blueprint_id}/confirm
    POST /api/coursepilot/exams/{blueprint_id}/generate
    GET  /api/coursepilot/exams/{blueprint_id}/questions
    POST /api/coursepilot/exams/{blueprint_id}/export

验收标准：

1.  blueprint 可生成；
2.  blueprint 可确认；
3.  题目可生成；
4.  文件可导出。

## T3-004 实现题目 Validator

优先级：P0

位置：

    src/coursepilot/validators/question_validator.py

校验：

1.  schema_valid；
2.  question_count_valid；
3.  score_valid；
4.  option_valid；
5.  answer_valid；
6.  explanation_valid；
7.  knowledge_coverage_valid；
8.  citation_valid。

验收标准：

1.  能识别题量不足；
2.  能识别答案缺失；
3.  能识别选项格式错误；
4.  能生成修复建议。

## T3-005 实现 Duplicate Detector

优先级：P0

位置：

    src/coursepilot/validators/duplicate_detector.py

任务内容：

1.  计算题干 embedding；
2.  计算题目相似度；
3.  阈值默认 0.85；
4.  输出重复题列表。

验收标准：

1.  能发现高度相似题目；
2.  能返回 duplicate_rate；
3.  可触发替换或补题。

## T3-006 实现四类 DOCX 导出

优先级：P0

位置：

    src/coursepilot/exporters/exam_docx_exporter.py

输出：

1.  学生版试卷；
2.  教师版答案；
3.  详细解析；
4.  答题卡。

验收标准：

1.  文件可打开；
2.  题号一致；
3.  答案不泄露到学生版；
4.  解析版包含引用。

## T3-007 实现试卷生成页面

优先级：P0

页面内容：

1.  课程选择；
2.  章节范围；
3.  题型配置；
4.  题量配置；
5.  分值配置；
6.  难度配置；
7.  blueprint 展示与确认；
8.  题目展示；
9.  校验报告；
10. 文件下载。

验收标准：

1.  用户可完成从配置到导出的完整流程；
2.  校验报告可读；
3.  文件可下载。

# Phase 4：PPT 生成与审核写回

## 目标

实现基于教学设计的 PPT 大纲生成、pptx 导出、教师审核与知识库写回。

## T4-001 新增 PPT Schema

优先级：P1

位置：

    src/coursepilot/schemas/ppt_schema.py

包含：

1.  PPTGenerationParams；
2.  SlideOutline；
3.  SlideItem；
4.  SlideValidationReport。

验收标准：

1.  可描述 slide_type；
2.  可描述标题、要点、备注和引用；
3.  可校验 LLM 输出。

## T4-002 新增 PPTGenerationGraph

优先级：P1

位置：

    src/agents/coursepilot/graphs/ppt_graph.py

节点：

    load_lesson_design
    generate_slide_outline
    validate_slide_outline
    repair_slide_outline
    build_pptx
    save_export_file

验收标准：

1.  可生成 PPT 大纲；
2.  可校验大纲；
3.  可导出 pptx。

## T4-003 实现 PPT API

优先级：P1

接口：

    POST /api/coursepilot/lessons/{lesson_id}/ppt/generate
    GET  /api/coursepilot/ppt/{outline_id}
    POST /api/coursepilot/ppt/{outline_id}/export

验收标准：

1.  可基于教学设计生成 PPT；
2.  可导出 pptx；
3.  PPT 内容与教学设计一致。

## T4-004 实现 PPTX Exporter

优先级：P1

位置：

    src/coursepilot/exporters/pptx_exporter.py

任务内容：

1.  根据 slide_type 选择模板布局；
2.  写入标题、要点、备注；
3.  添加引用页；
4.  保存 pptx。

验收标准：

1.  pptx 可打开；
2.  页数与 outline 一致；
3.  内容可编辑。

## T4-005 实现审核与写回

优先级：P1

位置：

    src/coursepilot/services/review_service.py

任务内容：

1.  审核教学设计；
2.  审核题目；
3.  approved 内容写回 Chroma；
4.  metadata 设置 verified=true。

验收标准：

1.  draft 内容可审核；
2.  rejected 不写回；
3.  approved 可写回知识库；
4.  后续检索可返回 verified 内容。

# Phase 5：测试、评估与简历展示

## T5-001 迁移并扩展原测试体系

优先级：P0

新增测试：

    tests/coursepilot/
    ├── test_course_api.py
    ├── test_document_upload.py
    ├── test_parser.py
    ├── test_chunker.py
    ├── test_retriever.py
    ├── test_lesson_graph.py
    ├── test_exam_graph.py
    ├── test_validators.py
    ├── test_exporters.py
    └── test_write_back.py

验收标准：

1.  pytest 可运行；
2.  核心业务模块有测试；
3.  原 Agent Service Toolkit 基础测试不被破坏。

## T5-002 实现评估脚本

优先级：P1

位置：

    src/coursepilot/evals/

指标：

1.  RAG Recall@K；
2.  Citation Coverage；
3.  Lesson Schema Pass Rate；
4.  Question Count Accuracy；
5.  Duplicate Rate；
6.  Answer Completeness；
7.  Export Success Rate。

验收标准：

1.  可对示例课程生成评估结果；
2.  结果可写入 README。

## T5-003 完成 README 与 Demo

优先级：P0

README 内容：

1.  项目背景；
2.  为什么选择 Agent Service Toolkit；
3.  如何参考 Langchain-Chatchat；
4.  技术架构图；
5.  Agent workflow 图；
6.  快速启动；
7.  示例课程资料；
8.  示例教学设计；
9.  示例试卷；
10. 示例 PPT；
11. 评估结果；
12. 简历亮点。

验收标准：

1.  面试官能快速理解项目；
2.  本地可复现；
3.  能展示完整备课闭环。

# 推荐开发顺序

    Week 1:
    Fork Agent Service Toolkit
    + 跑通原项目
    + 新增 CoursePilot 目录
    + 课程/文档/知识库基础能力

    Week 2:
    教学设计 Agent
    + Lesson Graph
    + 校验修复
    + docx 导出

    Week 3:
    试卷生成 Agent
    + blueprint
    + 分题型生成
    + 题目校验
    + duplicate detector
    + docx 导出

    Week 4:
    PPT 生成
    + 审核写回
    + README
    + Docker Demo
    + 评估脚本

# 最小可交付版本

时间不足时，MVP 最小版为：

    基于 Agent Service Toolkit 启动服务
    + CoursePilot 课程管理
    + 文件上传
    + Chroma 知识库构建
    + RAG 检索
    + 教学设计生成
    + 试卷 blueprint
    + 题目生成
    + 题目校验
    + docx 导出

