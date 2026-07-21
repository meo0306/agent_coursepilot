# CoursePilot Phase 4 审核说明 v0.1

本文档用于解释 Phase 4 做了什么、为什么这样做、对应文件在哪里，以及你应该如何运行命令来验收。

对照文件：

- `PLAN.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

## 1. Phase 4 的目标

Phase 4 的目标是“PPT 生成与审核写回”。

换成新手更容易理解的话，就是在前几个阶段已经能管理课程资料、生成教学设计和生成试卷后，继续补齐两个能力：

1. 基于某份教学设计生成 PPT 大纲。
2. 用 `python-pptx` 把 PPT 大纲渲染成可编辑的 `.pptx` 文件。
3. 让教师可以审核生成内容。
4. 只有审核通过，也就是 `approved` 的内容，才允许写回知识库。
5. 写回知识库的内容要带 `verified=true`，后续检索时可以区分“原始课程资料”和“教师确认过的生成内容”。

PRD 里把 PPT 初稿和教师审核写回列为 P1 能力。技术架构文档也明确要求：LLM 或生成逻辑只负责生成结构化 slide outline JSON，真正的 `.pptx` 文件由 exporter 渲染，审核写回必须走 human-in-the-loop，不能把未经审核的内容自动污染知识库。

## 2. Phase 4 任务对照

| 计划任务 | 计划目标 | 当前实现情况 | 主要文件 |
| --- | --- | --- | --- |
| T4-001 | 新增 PPT Schema | 已实现 | `src/coursepilot/schemas/ppt_schema.py` |
| T4-002 | 新增 PPTGenerationGraph | 已实现最小工作流 | `src/agents/coursepilot/graphs/ppt_graph.py` |
| T4-003 | 实现 PPT API | 已实现 | `src/coursepilot/api/routes_ppt.py` |
| T4-004 | 实现 PPTX Exporter | 已实现 | `src/coursepilot/exporters/pptx_exporter.py` |
| T4-005 | 实现审核与写回 | 已实现 PPT outline 写回 | `src/coursepilot/services/review_service.py` |
| 计划补充 | 文件下载接口 | 已实现 | `src/coursepilot/api/routes_files.py` |
| 计划补充 | Streamlit PPT/审核入口 | 已实现最小闭环 | `src/coursepilot/ui/knowledge_base_page.py` |
| 计划补充 | Agent Registry 注册 | 已实现 | `src/agents/agents.py` |

需要注意：当前 Phase 4 是可验收的 MVP。PPT 大纲生成逻辑是确定性的规则生成，不是完整调用大模型。`src/coursepilot/prompts/ppt/*.md` 已经准备好 prompt 模板，但主流程现在优先保证稳定、离线、可测试。

## 3. 新增了哪些文件

### 3.1 数据库迁移和 ORM 模型

新增文件：

```text
alembic/versions/2026_07_02_0005-create_ppt_review_tables.py
src/coursepilot/models/slide_outline.py
src/coursepilot/models/review_record.py
```

动机：

- PPT 大纲不是临时响应，需要保存下来，后续才能查询、导出、审核和写回。
- 审核动作也必须留痕，后续才能知道谁审核了什么内容，以及是否已经写回知识库。
- 单独迁移文件创建 Phase 4 所需的两张表，继续沿用 Phase 0 建立的 Alembic 管理方式。

`coursepilot_slide_outlines` 表保存 PPT 大纲：

```python
class SlideOutline(Base):
    # 对应数据库表 coursepilot_slide_outlines。
    # 一条记录就是一份 PPT 大纲。
    __tablename__ = "coursepilot_slide_outlines"

    # course_id：属于哪门课程。
    # task_id：对应哪次生成任务。
    # lesson_design_id：这份 PPT 是基于哪份教学设计生成的。
    # outline_json：保存结构化 slide outline。
    # validation_report_json：保存 PPT 校验报告。
    # pptx_file_id：如果已经导出 pptx，这里关联导出文件记录。
```

`coursepilot_review_records` 表保存审核记录：

```python
class ReviewRecord(Base):
    # 对应数据库表 coursepilot_review_records。
    # 一条记录就是一次教师审核动作。
    __tablename__ = "coursepilot_review_records"

    # target_type：审核对象类型，例如 ppt_outline。
    # target_id：被审核对象的 id。
    # review_status：approved / rejected / needs_revision。
    # write_back_status：not_written / pending / skipped / written。
```

### 3.2 PPT 和审核 Schema

新增文件：

```text
src/coursepilot/schemas/ppt_schema.py
src/coursepilot/schemas/review_schema.py
```

动机：

- FastAPI 请求和响应需要稳定结构。
- PPT 大纲必须可校验，不能只返回一段自然语言。
- 审核写回必须显式区分 `approved`、`rejected` 和 `needs_revision`。

`PPTGenerationParams` 表示用户生成 PPT 时传入的配置：

```python
class PPTGenerationParams(BaseModel):
    # slide_count：希望生成多少页，允许为空；为空时系统按教学设计自动决定。
    slide_count: int | None = Field(default=None, ge=3, le=60)

    # style_template：PPT 样式模板名，当前 MVP 默认 standard。
    style_template: str = "standard"

    # include_references：是否生成引用页。
    include_references: bool = True

    # additional_requirements：预留给教师的额外要求。
    additional_requirements: str | None = None
```

`SlideItem` 表示单页 PPT：

```python
class SlideItem(BaseModel):
    # slide_index：第几页，必须从 1 开始连续。
    # slide_type：页面类型，如 title / objectives / content / activity / summary / references。
    # title：页面标题。
    # bullet_points：页面要点。
    # speaker_notes：讲稿备注，导出时写入 notes。
    # references：引用来源，用于追溯课程资料。
    # source_session_index：这一页对应第几个课时。
```

这里有一个重要校验：

```python
@model_validator(mode="after")
def validate_references_slide(self):
    # 如果页面类型是 references，那么必须至少有一个引用。
    # 这样可以避免生成空的参考资料页。
```

`SlideOutlineContent` 表示整份 PPT 大纲：

```python
class SlideOutlineContent(BaseModel):
    # course_name：课程名。
    # chapter：章节。
    # lesson_id：来源教学设计 id。
    # style_template：样式模板。
    # slides：所有页面。
```

它会检查 `slide_index` 是否连续：

```python
@model_validator(mode="after")
def validate_slide_indices(self):
    # 期望页码是 1, 2, 3...
    # 如果缺页、跳页或乱序，schema 直接报错。
```

`ReviewCreate` 表示创建审核记录时的请求体：

```python
class ReviewCreate(BaseModel):
    # target_type：当前支持 ppt_outline、lesson_design、question 三种记录类型。
    # target_id：被审核对象 id。
    # review_status：approved / rejected / needs_revision。
    # comment：教师审核意见。
```

当前要特别注意：schema 能记录三类对象的审核，但 Phase 4 的“写回知识库”只支持 `ppt_outline`。

### 3.3 PPT 校验器

新增文件：

```text
src/coursepilot/validators/ppt_validator.py
```

动机：

技术架构要求 LLM 或生成逻辑输出 JSON 后必须做 Pydantic 和业务校验。PPT 校验器负责判断这份 outline 是否达到可导出的最低标准。

`PPTValidator.validate()` 主要检查：

```python
def validate(outline, expected_slide_count=None, total_sessions=None):
    # 1. slide_count_valid：
    #    如果用户指定 slide_count，就检查实际页数是否等于指定页数。
    #    如果没指定，就至少要有 3 页。

    # 2. slide_type_valid：
    #    每页 slide_type 必须属于允许集合。

    # 3. content_not_empty：
    #    每页必须有标题和 bullet_points。

    # 4. source_session_valid：
    #    如果知道总课时数，就检查 source_session_index 是否落在 1..total_sessions。

    # 5. citation_valid：
    #    除 title 页外，其他页面都需要 references。

    # 6. 返回 SlideValidationReport。
```

这个校验器是 Phase 4 的质量门槛。只有校验通过的大纲，才应该进入导出。

### 3.4 PPTX 导出器

新增文件：

```text
src/coursepilot/exporters/pptx_exporter.py
```

动机：

PRD 要求导出可编辑 `.pptx` 文件，技术架构要求不能让 LLM 直接生成文件，而是让程序用结构化 outline 渲染文件。这里使用 `python-pptx`。

核心逻辑：

```python
class PPTXExporter:
    def export(self, outline, output_path):
        # 新建 Presentation。
        # 遍历 outline.slides。
        # 每个 SlideItem 添加一页 PPT。
        # 最后保存到 output_path。
```

页面布局逻辑：

```python
def _add_slide(self, presentation, slide_data):
    if slide_data.slide_type == "title":
        # title 页使用 PowerPoint 默认标题页 layout。
    else:
        # 其他页面使用标题 + 正文 layout。
        # bullet_points 写入正文框。
```

备注和引用逻辑：

```python
notes_parts = []
if slide_data.speaker_notes:
    notes_parts.append(slide_data.speaker_notes)

for ref in slide_data.references:
    # 引用信息写入 notes，包含 source_type、chapter、page、chunk_id。
```

这样导出的 PPT 有两个特点：

- 页面内容可编辑，因为它是普通 PowerPoint 文本框，不是图片。
- 引用信息可追溯，因为每页 notes 里保留了 chunk 来源。

### 3.5 PPT 服务层

新增文件：

```text
src/coursepilot/services/ppt_service.py
```

动机：

FastAPI route 不直接写业务逻辑，PPT 生成、校验、保存、导出都放在 service 层。这符合技术架构中的 `API -> Service -> ORM/Exporter/Validator` 分层。

`generate_outline()` 做这些事：

```python
def generate_outline(lesson_id, params):
    # 1. 根据 lesson_id 读取 LessonDesign。
    # 2. 如果教学设计不存在，返回 None，让 API 层转成 404。
    # 3. 创建 GenerationTask，记录本次 PPT 生成任务。
    # 4. 把 lesson.content_json 解析成 LessonDesignContent。
    # 5. 调用 _build_outline() 基于教学设计构造 slide outline。
    # 6. 调用 PPTValidator 校验页数、类型、内容、课时来源和引用。
    # 7. 保存 SlideOutline 到数据库。
    # 8. 返回 outline_id、task_id、outline 和 validation_report。
```

`_build_outline()` 的生成规则：

```python
def _build_outline(lesson_id, lesson, params):
    # 1. 先生成标题页。
    # 2. 每个课时生成 objectives 页。
    # 3. 每个课时生成 key points 内容页。
    # 4. 生成 summary/homework 页。
    # 5. 如果 include_references=True，追加 references 页。
    # 6. 如果用户指定 slide_count，调用 _fit_slide_count() 调整页数。
```

`_fit_slide_count()` 的作用：

```python
def _fit_slide_count(slides, target_count, references):
    # 如果页数太多：
    #   截断到目标页数，尽量保留 references 页。
    # 如果页数太少：
    #   插入 activity 页补齐。
```

`export_pptx()` 做这些事：

```python
def export_pptx(outline_id):
    # 1. 读取 SlideOutline。
    # 2. 把 outline_json 转成 SlideOutlineContent。
    # 3. 再次调用 PPTValidator，避免导出无效大纲。
    # 4. 调用 PPTXExporter 生成 .pptx。
    # 5. 创建 ExportFile 记录。
    # 6. 把 SlideOutline.pptx_file_id 指向导出的文件。
```

### 3.6 审核与写回服务

新增文件：

```text
src/coursepilot/services/review_service.py
```

动机：

PRD 明确要求 human-in-the-loop：系统生成的是草稿，教师审核通过后才可以沉淀进知识库。这样可以避免低质量生成内容污染后续检索。

`create_review()` 做这些事：

```python
def create_review(payload):
    # 1. 根据 target_type 和 target_id 找到被审核对象。
    # 2. 解析出 course_id，确保审核记录归属于正确课程。
    # 3. 创建 ReviewRecord。
    # 4. 如果 review_status 是 approved，write_back_status 设为 pending。
    # 5. 如果不是 approved，write_back_status 设为 not_written。
    # 6. 同步更新目标对象 status。
```

`write_back()` 做这些事：

```python
def write_back(review_id):
    # 1. 读取 ReviewRecord。
    # 2. 如果 review_status 不是 approved：
    #      write_back_status = skipped
    #      不写入 Chroma。
    # 3. 如果 target_type 不是 ppt_outline：
    #      抛出错误，因为 Phase 4 只支持 PPT outline 写回。
    # 4. 读取 SlideOutline。
    # 5. 把每一页 slide 转成一段文本。
    # 6. 调用 ChromaVectorStore.add_verified_texts() 写入向量库。
    # 7. metadata 里设置 verified=True，source_type=reviewed_ppt。
    # 8. 标记 write_back_status=written，outline.status=approved。
```

这一段是 Phase 4 最关键的安全逻辑：

```python
if review.review_status != "approved":
    review.write_back_status = "skipped"
    return ...
```

也就是说，`rejected` 或 `needs_revision` 不会进入知识库。

### 3.7 FastAPI 路由

新增文件：

```text
src/coursepilot/api/routes_ppt.py
src/coursepilot/api/routes_reviews.py
src/coursepilot/api/routes_files.py
```

PPT API：

```text
POST /api/coursepilot/lessons/{lesson_id}/ppt/generate
GET  /api/coursepilot/ppt/{outline_id}
POST /api/coursepilot/ppt/{outline_id}/export
```

审核 API：

```text
POST /api/coursepilot/reviews
POST /api/coursepilot/reviews/{review_id}/write-back
```

文件 API：

```text
GET /api/coursepilot/files/{file_id}
GET /api/coursepilot/files/{file_id}/download
```

动机：

- `routes_ppt.py` 负责 PPT 大纲生成、查询和导出。
- `routes_reviews.py` 负责审核记录和写回。
- `routes_files.py` 负责导出文件信息和下载，后续 docx/pptx 都可以统一走这个入口。

### 3.8 Prompt 模板

新增文件：

```text
src/coursepilot/prompts/ppt/generate_slide_outline.md
src/coursepilot/prompts/ppt/repair_slide_outline.md
```

动机：

- `generate_slide_outline.md` 约束后续 LLM 只生成 `SlideOutlineContent` JSON，不直接生成 PPT 文件。
- `repair_slide_outline.md` 约束后续修复无效大纲时仍返回结构化 JSON。

当前主流程没有直接读取这些 prompt 文件。它们是为后续接入真实 LLM 预留的资产。

### 3.9 PPT Agent 图

新增文件：

```text
src/agents/coursepilot/states/ppt_state.py
src/agents/coursepilot/nodes/ppt_nodes.py
src/agents/coursepilot/graphs/ppt_graph.py
```

动机：

CoursePilot 是基于 Agent Service Toolkit 改造，不只是普通 CRUD 后端。Phase 4 因此增加 `coursepilot-ppt-agent`，让 PPT 生成也能以 LangGraph workflow 的形式存在。

`PPTGraphState` 是节点间传递的数据包：

```python
class PPTGraphState(TypedDict, total=False):
    # messages：普通聊天入口使用。
    # ppt_params：PPT 生成参数。
    # lesson_design：结构化教学设计。
    # slide_outline：生成出的 PPT 大纲。
    # validation_report：校验报告。
```

`ppt_nodes.py` 里的节点：

```python
chat_response
# 没有 lesson_design 时，返回提示信息，告诉用户使用 PPT API。

generate_slide_outline
# 根据 LessonDesignContent 和 PPTGenerationParams 生成 SlideOutlineContent。

validate_slide_outline
# 调 PPTValidator 校验大纲。

repair_slide_outline
# 补齐缺失引用或空 bullet_points，并增加 repair_attempts。
```

`ppt_graph.py` 的流程：

```text
route_entry
  -> chat_response -> END
  -> generate_slide_outline
     -> validate_slide_outline
     -> repair_slide_outline 或 END
```

需要注意：计划里的 `build_pptx`、`save_export_file` 没有放进 LangGraph 图里，而是在产品 API 的 `PPTService.export_pptx()` 中完成。这是当前实现的边界：Agent 图负责 outline 生成和校验，文件导出由服务层负责。

## 4. 修改了哪些已有文件

### 4.1 注册 API 路由

修改文件：

```text
src/coursepilot/api/router.py
```

新增逻辑：

```python
from coursepilot.api.routes_ppt import router as ppt_router
from coursepilot.api.routes_reviews import router as reviews_router
from coursepilot.api.routes_files import router as files_router

api_router.include_router(ppt_router)
api_router.include_router(reviews_router)
api_router.include_router(files_router)
```

动机：只创建 route 文件还不够，必须注册到统一的 `/api/coursepilot` 路由树下，FastAPI 才能暴露这些接口。

### 4.2 注册 schema、model、service、validator、exporter

修改文件：

```text
src/coursepilot/schemas/__init__.py
src/coursepilot/models/__init__.py
src/coursepilot/services/__init__.py
src/coursepilot/validators/__init__.py
src/coursepilot/exporters/__init__.py
```

动机：

- 统一导出 Phase 4 新增类，减少 import 路径混乱。
- `models/__init__.py` 对 SQLAlchemy/Alembic 很重要，模型需要被 import 后才能进入 metadata。
- `exporters/__init__.py` 导出 `PPTXExporter`，让服务层可以 `from coursepilot.exporters import PPTXExporter`。

### 4.3 注册 CoursePilot PPT Agent

修改文件：

```text
src/agents/agents.py
src/agents/coursepilot/graphs/__init__.py
src/agents/coursepilot/states/__init__.py
```

新增 Agent id：

```text
coursepilot-ppt-agent
```

动机：Agent Service Toolkit 的 `/info` 和 agent 调用流程依赖 Agent Registry。注册后，外部才能发现和调用 Phase 4 的 PPT Agent。

### 4.4 知识库检索支持 verified 过滤

修改文件：

```text
src/coursepilot/schemas/kb_schema.py
src/coursepilot/rag/vector_store.py
src/coursepilot/services/kb_service.py
src/coursepilot/rag/retriever.py
```

动机：

Phase 4 需要证明“审核通过内容写回知识库后，后续检索可以区分已审核内容”。因此检索请求新增了：

```python
verified_only: bool | None = None
```

向量库写回新增了：

```python
def add_verified_texts(...):
    # 写入 Chroma 时强制 metadata["verified"] = True。
    # source_type 使用 reviewed_ppt。
```

这样你可以用 `verified_only=true` 只检索教师审核过的内容。

### 4.5 Streamlit 页面增加 PPT 和审核入口

修改文件：

```text
src/coursepilot/ui/knowledge_base_page.py
```

新增 UI 区域：

```text
Generate PPT
  - PPT lesson ID
  - Slide count
  - PPT style template
  - Include references slide
  - Generate PPT outline
  - Export PPTX
  - Approve PPT
  - Write back approved PPT
```

动机：给新手和演示用户一个不写 API 的最小入口。这个页面可以从 lesson_id 开始，完成 PPT outline 生成、pptx 导出、审核和写回。

### 4.6 增加测试

新增或扩展文件：

```text
tests/coursepilot/test_ppt_graph.py
tests/coursepilot/test_ppt_api.py
tests/coursepilot/test_write_back.py
tests/coursepilot/test_exporters.py
tests/coursepilot/test_validators.py
```

动机：

- `test_ppt_graph.py` 验证 PPT Agent 图能走通。
- `test_ppt_api.py` 验证 PPT 生成、导出、审核、写回、verified 检索闭环。
- `test_write_back.py` 验证无效审核目标不会写入向量库。
- `test_exporters.py` 验证 `.pptx` 文件能生成并可读。
- `test_validators.py` 验证 PPT outline 校验器。

## 5. 你应该如何验收

### 5.1 最快验收：跑测试

在项目根目录执行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_ppt_graph.py tests\coursepilot\test_ppt_api.py tests\coursepilot\test_write_back.py tests\coursepilot\test_exporters.py tests\coursepilot\test_validators.py tests\service\test_service.py -q
```

本次审核时实际运行结果：

```text
24 passed, 10 warnings in 1.21s
```

这些测试覆盖的验收点：

- `coursepilot-ppt-agent` 能被调用。
- PPT outline 可以基于教学设计生成。
- outline 页数可以匹配 `slide_count`。
- outline 引用校验通过。
- `.pptx` 文件可以导出，并且页数与 outline 一致。
- `rejected` 审核不会写回知识库。
- `approved` 审核可以写回知识库。
- 写回后的内容可以通过 `verified_only=true` 检索到。

本次测试有一个警告：本地 `HashingEmbeddings` 的 relevance score 可能出现小于 0 的值。这个警告不影响 Phase 4 的验收，因为本阶段验证的是 `verified=true` 元数据写入和检索过滤，不是相似度分数标定。

### 5.2 数据库迁移验收

如果你使用真实本地数据库，而不是测试里的临时内存库，先执行迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

验收重点：

- 数据库里应该创建 `coursepilot_slide_outlines` 表。
- 数据库里应该创建 `coursepilot_review_records` 表。
- `coursepilot_slide_outlines` 用于保存 PPT 大纲。
- `coursepilot_review_records` 用于保存审核记录。

### 5.3 手工 API 验收

先启动 FastAPI 服务：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

默认服务地址通常是：

```text
http://localhost:8080
```

第一步，创建课程：

```powershell
$course = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses" `
  -ContentType "application/json" `
  -Body '{"course_name":"Phase 4 Demo Course","course_type":"AI","student_level":"undergraduate"}'

$course.id
```

第二步，上传课程资料：

```powershell
$doc = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/documents/upload" `
  -Form @{
    source_type = "textbook"
    file = Get-Item "data/coursepilot_sample/教材-人工智能：从算法到系统.docx"
  }

$doc.id
```

如果你的 PowerShell 版本不支持 `-Form`，可以用 Streamlit 页面上传，或者直接跑 pytest 做自动验收。

第三步，构建知识库：

```powershell
$build = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/documents/$($doc.id)/build-kb"

$build
```

第四步，先生成一份教学设计。Phase 4 的 PPT 生成依赖 `lesson_id`：

```powershell
$lessonPayload = @{
  chapter_range = "Search"
  total_sessions = 2
  session_duration = 45
  teaching_template = "standard"
} | ConvertTo-Json -Depth 5

$lesson = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/lessons/generate" `
  -ContentType "application/json" `
  -Body $lessonPayload

$lesson.lesson_id
```

第五步，基于教学设计生成 PPT 大纲：

```powershell
$pptPayload = @{
  slide_count = 6
  style_template = "standard"
  include_references = $true
} | ConvertTo-Json -Depth 5

$ppt = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/lessons/$($lesson.lesson_id)/ppt/generate" `
  -ContentType "application/json" `
  -Body $pptPayload

$ppt.outline_id
$ppt.validation_report
```

你应该重点检查：

- 返回 `outline_id`。
- `validation_report.slide_count_valid` 是 `True`。
- `validation_report.citation_valid` 是 `True`。
- `$ppt.outline.slides.Count` 应该等于 6。

第六步，查询 PPT 大纲：

```powershell
$outline = Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8080/api/coursepilot/ppt/$($ppt.outline_id)"

$outline.status
$outline.outline_json.slides.Count
```

第七步，导出 PPTX：

```powershell
$export = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/ppt/$($ppt.outline_id)/export"

$export.file_id
$export.file_path
Test-Path $export.file_path
```

你应该看到：

```text
True
```

也可以用下载接口：

```powershell
Invoke-WebRequest `
  -Uri "http://localhost:8080/api/coursepilot/files/$($export.file_id)/download" `
  -OutFile ".\phase4_demo.pptx"

Test-Path ".\phase4_demo.pptx"
```

打开 `phase4_demo.pptx` 后，应该能看到：

- PPT 可以正常打开。
- 页数与 outline 一致。
- 页面标题和 bullet points 正常显示。
- 每页内容是可编辑文本。

第八步，验证 rejected 不写回：

```powershell
$rejectedReviewPayload = @{
  target_type = "ppt_outline"
  target_id = $ppt.outline_id
  review_status = "rejected"
  comment = "Needs revision."
} | ConvertTo-Json -Depth 5

$rejected = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/reviews" `
  -ContentType "application/json" `
  -Body $rejectedReviewPayload

$rejectedWriteBack = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/reviews/$($rejected.id)/write-back"

$rejectedWriteBack.write_back_status
```

你应该看到：

```text
skipped
```

第九步，验证 approved 可以写回：

```powershell
$approvedReviewPayload = @{
  target_type = "ppt_outline"
  target_id = $ppt.outline_id
  review_status = "approved"
  comment = "Approved."
} | ConvertTo-Json -Depth 5

$approved = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/reviews" `
  -ContentType "application/json" `
  -Body $approvedReviewPayload

$writeBack = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/reviews/$($approved.id)/write-back"

$writeBack.write_back_status
$writeBack.written_chunk_ids
```

你应该看到：

```text
written
```

并且 `written_chunk_ids` 不是空列表。

第十步，验证写回内容能被 `verified_only` 检索到：

```powershell
$searchPayload = @{
  query = "Session Objectives Search"
  verified_only = $true
  top_k = 5
} | ConvertTo-Json -Depth 5

$search = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/kb/search" `
  -ContentType "application/json" `
  -Body $searchPayload

$search.results | Select-Object chunk_id, source_type, verified, title
```

你应该看到：

- 至少有一条结果。
- `verified` 是 `True`。
- `source_type` 是 `reviewed_ppt`。

### 5.4 Streamlit UI 验收

先启动后端：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

再开另一个终端启动 Streamlit：

```powershell
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py
```

打开：

```text
http://localhost:8501
```

验收步骤：

1. 在 CoursePilot 页面创建课程。
2. 上传课程资料。
3. 构建知识库。
4. 生成教学设计，拿到 `lesson_id`。
5. 找到 `Generate PPT` 区域。
6. 填写 `PPT lesson ID`、`Slide count`、`PPT style template`。
7. 点击 `Generate PPT outline`。
8. 确认页面返回里有 `outline_id` 和 `validation_report`。
9. 点击 `Export PPTX`。
10. 确认页面返回里有 `file_id` 和 `file_path`。
11. 点击 `Approve PPT`。
12. 点击 `Write back approved PPT`。

UI 验收重点：

- 页面可以显示 PPT outline JSON。
- 页面可以显示 PPTX 导出结果。
- 页面可以显示审核记录。
- 页面可以显示写回结果。
- 写回后可通过知识库搜索接口搜到 `verified=true` 的内容。

## 6. 当前实现边界

这些不是 bug，而是 Phase 4 MVP 的边界，后续可以继续增强：

1. 当前 PPT 大纲生成是规则化生成，不是完整 LLM 生成。
2. Prompt 文件已经准备，但主业务流程暂未读取 prompt。
3. LangGraph 的 PPT 图只做 outline 生成、校验和简单修复；`build_pptx` 和 `save_export_file` 放在 `PPTService.export_pptx()` 中完成。
4. 审核记录 schema 支持 `ppt_outline`、`lesson_design`、`question`，但 Phase 4 只有 `ppt_outline` 支持写回知识库。
5. Streamlit 是最小操作入口，没有做复杂的 PPT 页面编辑器、历史列表筛选或批量下载。
6. PPT 模板使用 `python-pptx` 默认 layout，满足可编辑和结构完整，不追求商业级美化。
7. 本地 HashingEmbeddings 的 relevance score 可能出现小于 0 的警告；当前验收重点是元数据过滤和写回闭环。

## 7. Phase 4 验收清单

你可以按下面清单逐项确认：

- [ ] `coursepilot-ppt-agent` 已注册到 `src/agents/agents.py`。
- [ ] `/api/coursepilot/lessons/{lesson_id}/ppt/generate` 能生成 PPT 大纲。
- [ ] PPT 大纲中每页有 `slide_type`、标题、要点。
- [ ] PPT 大纲页码 `slide_index` 连续。
- [ ] `PPTValidator` 能校验页数、类型、内容、来源课时和引用。
- [ ] `/api/coursepilot/ppt/{outline_id}/export` 能导出 `.pptx`。
- [ ] `.pptx` 可以打开，页数与大纲一致，内容可编辑。
- [ ] `/api/coursepilot/reviews` 能创建审核记录。
- [ ] `rejected` 审核写回结果是 `skipped`，不会进入知识库。
- [ ] `approved` 审核写回结果是 `written`，并返回 `written_chunk_ids`。
- [ ] `/api/coursepilot/courses/{course_id}/kb/search` 使用 `verified_only=true` 能搜到 `source_type=reviewed_ppt` 的内容。
- [ ] `pytest` 命令通过。

如果以上都通过，就可以认为 Phase 4 已经达成当前计划里的 MVP 验收标准。
