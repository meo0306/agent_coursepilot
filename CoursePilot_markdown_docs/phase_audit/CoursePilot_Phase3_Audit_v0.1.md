# CoursePilot Phase 3 审核说明 v0.1

本文档用于解释 Phase 3 做了什么、为什么这样做、对应文件在哪里，以及你应该如何运行命令来验收。

对照文件：

- `PLAN.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

## 1. Phase 3 的目标

Phase 3 的目标是“作业/试卷生成 Agent”。

换成新手更容易理解的话，就是在 Phase 1 已有“课程资料入库和检索”、Phase 2 已有“教案生成”的基础上，继续增加一条完整的试卷业务链路：

1. 老师输入章节范围、题型数量、每题分值、难度分布等配置。
2. 系统先生成一份试卷蓝图，也就是本套题的结构规划。
3. 老师确认蓝图后，系统按题型生成题目。
4. 系统自动校验题目数量、分值、选项、答案、解析、知识点、引用和重复度。
5. 系统导出四类 DOCX 文件：学生版试卷、教师答案版、详细解析版、答题卡。
6. 在 Agent Registry、FastAPI API、Streamlit 页面中都可以找到 Phase 3 的入口。

PRD 强调 CoursePilot 要帮助教师从课程资料中生成可交付的教学材料；技术架构强调要通过 `API -> Service -> Model/DB -> Exporter/Validator -> Agent Graph` 的分层方式实现。Phase 3 的核心验收标准就是：试卷不能只是生成一段文本，而要能保存蓝图、生成结构化题目、做质量检查，并导出可打开的教学文件。

## 2. Phase 3 任务对照

| 计划任务 | 计划目标 | 当前实现情况 | 主要文件 |
| --- | --- | --- | --- |
| T3-001 | 试卷/作业参数结构与蓝图 schema | 已实现 | `src/coursepilot/schemas/exam_schema.py` |
| T3-002 | 题目 schema，支持单选、多选、判断、简答 | 已实现 | `src/coursepilot/schemas/question_schema.py` |
| T3-003 | 题目校验和重复检测 | 已实现 | `src/coursepilot/validators/question_validator.py`, `src/coursepilot/validators/duplicate_detector.py` |
| T3-004 | 试卷导出，含学生版、答案版、解析版、答题卡 | 已实现 | `src/coursepilot/exporters/exam_docx_exporter.py` 等 |
| T3-005 | 试卷服务层和 FastAPI 接口 | 已实现 | `src/coursepilot/services/exam_service.py`, `src/coursepilot/api/routes_exams.py` |
| T3-006 | 试卷 Agent 图和 Agent 注册 | 已实现 | `src/agents/coursepilot/graphs/exam_graph.py`, `src/agents/agents.py` |
| T3-007 | Streamlit 最小 UI 入口 | 已实现最小闭环 | `src/coursepilot/ui/knowledge_base_page.py` |

需要注意：当前 Phase 3 是可验收的 MVP。题目生成逻辑是确定性的规则生成，不是完整接入大模型 prompt 后的自由生成。`src/coursepilot/prompts/exam/*.md` 已经准备好模板，但主流程现在主要通过 Python 代码生成稳定测试结果。

## 3. 新增了哪些文件

### 3.1 数据库迁移和 ORM 模型

新增文件：

```text
alembic/versions/2026_06_30_0004-create_exam_tables.py
src/coursepilot/models/exam.py
src/coursepilot/models/question.py
```

动机：

- 蓝图和题目都不是临时数据，必须落库，后续才能查询、确认、重新生成、导出。
- `ExamBlueprint` 存试卷蓝图，代表“本套试卷打算怎么出”。
- `Question` 存具体题目，代表“实际生成出来的题目内容”。
- 单独迁移文件用于创建新表，符合 Phase 0 建好的 Alembic 管理方式。

关键代码解释：

```python
class ExamBlueprint(Base):
    # 对应数据库表 coursepilot_exam_blueprints。
    # 一条记录就是一份试卷/作业蓝图。
    __tablename__ = "coursepilot_exam_blueprints"

    # course_id 让蓝图归属于某门课程。
    # task_id 让蓝图可以追踪到一次生成任务。
    # blueprint_json 保存结构化蓝图内容，避免频繁改表。
    # status 用 draft / confirmed / questions_generated / needs_review 表示流程状态。
```

```python
class Question(Base):
    # 对应数据库表 coursepilot_questions。
    # 一条记录就是一道题。
    __tablename__ = "coursepilot_questions"

    # exam_blueprint_id 让题目归属于某份蓝图。
    # question_type 区分 single_choice / multiple_choice / judgement / short_answer。
    # options_json 保存选择题选项。
    # references_json 保存题目引用到的知识库 chunk，便于追溯来源。
```

### 3.2 试卷和题目 Schema

新增文件：

```text
src/coursepilot/schemas/exam_schema.py
src/coursepilot/schemas/question_schema.py
```

动机：

- FastAPI 不能直接把数据库对象暴露给前端，因此需要 Pydantic schema 定义请求和响应。
- 试卷生成需要强约束字段，例如题型数量必须是非负数、每题分值必须大于 0。
- 题目生成后也要是结构化数据，不能只是一整段文本，否则无法校验、导出和生成答题卡。

`ExamGenerationParams` 负责接收老师输入：

```python
class ExamGenerationParams(BaseModel):
    # 老师希望覆盖的章节范围，例如 Chapter 1-3。
    chapter_range: str

    # 生成 exam 或 homework，两者共用同一套流程。
    generation_type: Literal["homework", "exam"] = "exam"

    # 各题型数量，例如 single_choice: 5。
    question_counts: dict[str, int]

    # 各题型每题分值，例如 short_answer: 10。
    score_per_question: dict[str, int]

    # 难度分布，例如 easy / medium / hard。
    difficulty_distribution: dict[str, float]
```

`QuestionGroupPlan` 负责蓝图中的每个题型分组：

```python
class QuestionGroupPlan(BaseModel):
    # question_type 表示题型。
    # count 表示这一题型要生成几道。
    # score_each 表示每道题多少分。
    # total_score 是这一组小计分数。
    # difficulty 是这一组的主难度。
```

`QuestionItem` 负责单道题：

```python
class QuestionItem(BaseModel):
    # question_text 是题干。
    # options 只给选择题使用。
    # correct_answer 是标准答案。
    # explanation 是解析。
    # references 是来源 chunk id 列表，保证题目能追溯到课程资料。
```

这里的校验逻辑很重要：

- 单选题必须有选项，答案必须是某个选项 key。
- 多选题答案可以是 `A,C` 这种多个 key，但每个 key 都必须存在。
- 判断题答案必须是 true/false 或对应中文真假值。
- 这些 schema 校验属于第一层防线，后面的 `QuestionValidator` 是第二层业务校验。

### 3.3 校验器和重复检测

新增文件：

```text
src/coursepilot/validators/question_validator.py
src/coursepilot/validators/duplicate_detector.py
```

动机：

PRD 里的试卷生成不能只追求“有内容”，还要确保质量可控。Phase 3 因此增加了两类检查：

1. 结构和业务检查：题目数量、总分、选项、答案、解析、知识点、引用。
2. 重复度检查：题干过于相似时标记出来，避免一套题里出现重复题。

`QuestionValidator.validate()` 的核心流程可以理解为：

```python
def validate(blueprint, questions):
    # 1. 按题型统计实际生成了多少题。
    # 2. 和蓝图里的 expected count 对比。
    # 3. 累加所有题目分值，和蓝图总分对比。
    # 4. 检查选择题是否有选项，答案是否存在。
    # 5. 检查每题是否有解析、知识点、引用。
    # 6. 调用 DuplicateDetector 计算重复题比例。
    # 7. 返回 ExamValidationReport，供 API 和测试判断是否通过。
```

`DuplicateDetector` 使用 `HashingEmbeddings` 做轻量向量化：

```python
class DuplicateDetector:
    # 不依赖外部 embedding 服务，所以测试稳定、离线可跑。
    # 两两比较题干向量相似度，超过阈值就认为是疑似重复。
```

当前重复度阈值来自配置项 `COURSEPILOT_DUPLICATE_THRESHOLD`。这符合 Phase 0 对配置集中管理的设计。

### 3.4 DOCX 导出器

新增文件：

```text
src/coursepilot/exporters/exam_docx_exporter.py
src/coursepilot/exporters/answer_docx_exporter.py
src/coursepilot/exporters/explanation_docx_exporter.py
src/coursepilot/exporters/answer_sheet_exporter.py
```

动机：

Phase 3 的验收标准要求导出四类文件：

- 学生版试卷：只给题目和答题空白，不能泄露答案和解析。
- 教师答案版：包含题目和标准答案。
- 详细解析版：包含答案、解析和引用。
- 答题卡：只给题号和作答区域。

主实现放在 `ExamDocxExporter`，另外三个文件目前是轻量包装类，为后续拆分不同导出样式预留位置。

关键代码解释：

```python
class ExamDocxExporter:
    def export_student_exam(...):
        # 写标题、章节范围、总分。
        # 写题干和选项。
        # 不写 correct_answer。
        # 不写 explanation。
        # 给每题保留空白 Answer 行。

    def export_teacher_answer(...):
        # 写题干、选项和标准答案。
        # 不写详细解析，适合教师快速核对。

    def export_explanation(...):
        # 写题干、答案、解析和 references。
        # 适合作为教师备课或讲评材料。

    def export_answer_sheet(...):
        # 只写题号、题型和空白作答区。
        # 不泄露答案。
```

测试里专门检查了学生版 DOCX 不包含正确答案和 `Explanation` 字样，这是本阶段最关键的安全验收点之一。

### 3.5 试卷服务层和 API 路由

新增文件：

```text
src/coursepilot/services/exam_service.py
src/coursepilot/api/routes_exams.py
```

动机：

技术架构要求业务逻辑不要直接写在 FastAPI route 里。Route 只负责接收 HTTP 请求和返回 HTTP 响应，真正的流程编排放在 service 层。

`ExamService` 是 Phase 3 的业务核心。

`create_blueprint()` 做这些事：

```python
def create_blueprint(course_id, params):
    # 1. 检查课程是否存在。
    # 2. 按 chapter_range 从知识库检索课程上下文。
    # 3. 如果没有检索结果，拒绝生成蓝图。
    # 4. 创建 GenerationTask，用于记录这次生成任务。
    # 5. 调用 _build_blueprint() 生成结构化蓝图。
    # 6. 保存 ExamBlueprint 到数据库，初始状态为 draft。
    # 7. 返回 blueprint_id、task_id 和蓝图内容。
```

`generate_questions()` 做这些事：

```python
def generate_questions(blueprint_id):
    # 1. 读取蓝图。
    # 2. 调用 _generate_questions_from_blueprint() 逐题型生成题目。
    # 3. 调用 QuestionValidator 做完整校验。
    # 4. 删除该蓝图下旧题目，避免重复生成后残留旧数据。
    # 5. 保存新题目。
    # 6. 根据校验是否通过，把蓝图状态改成 questions_generated 或 needs_review。
    # 7. 把 validation_report 写回 GenerationTask，便于追踪。
```

`export_exam_files()` 做这些事：

```python
def export_exam_files(blueprint_id):
    # 1. 读取蓝图和题目。
    # 2. 把数据库 Question 转成 QuestionItem。
    # 3. 调用 ExamDocxExporter 导出四个 DOCX。
    # 4. 为每个导出文件创建 ExportFile 记录。
    # 5. 返回四个文件路径和 file_role。
```

`routes_exams.py` 暴露了这些接口：

```text
POST /api/coursepilot/courses/{course_id}/exams/blueprint
GET  /api/coursepilot/exams/{blueprint_id}
POST /api/coursepilot/exams/{blueprint_id}/confirm
POST /api/coursepilot/exams/{blueprint_id}/generate
GET  /api/coursepilot/exams/{blueprint_id}/questions
POST /api/coursepilot/exams/{blueprint_id}/export
```

### 3.6 Prompt 模板

新增文件：

```text
src/coursepilot/prompts/exam/plan_exam_blueprint.md
src/coursepilot/prompts/exam/generate_single_choice.md
src/coursepilot/prompts/exam/generate_multiple_choice.md
src/coursepilot/prompts/exam/generate_judgement.md
src/coursepilot/prompts/exam/generate_short_answer.md
src/coursepilot/prompts/repair/regenerate_missing_questions.md
```

动机：

这些文件为后续接入真实 LLM 生成预留了 prompt 资产。每个题型单独一个 prompt，目的是让后续维护更清晰：

- 蓝图规划一个 prompt。
- 单选、多选、判断、简答各一个 prompt。
- 修复缺失或错误题目一个 prompt。

当前主流程没有直接读取这些 prompt 文件，原因是 Phase 3 先保证离线、稳定、可测试的业务闭环。

### 3.7 CoursePilot Exam Agent 图

新增文件：

```text
src/agents/coursepilot/states/exam_state.py
src/agents/coursepilot/nodes/exam_nodes.py
src/agents/coursepilot/graphs/exam_graph.py
```

动机：

项目原框架是 Agent Service Toolkit，PRD 也要求保留 Agent 能力。Phase 3 因此不仅加 API，还加了一个 LangGraph 试卷 Agent。

`ExamGraphState` 是节点之间传递的数据包：

```python
class ExamGraphState(TypedDict, total=False):
    # messages: 普通聊天入口使用。
    # exam_params: 结构化试卷生成参数。
    # retrieved_contexts: 检索到的课程资料。
    # exam_blueprint: 规划出来的蓝图。
    # questions: 生成出来的题目列表。
    # validation_report: 校验结果。
```

`exam_nodes.py` 里每个函数可以理解成流水线上的一个工位：

```python
chat_response
# 没有 exam_params 时，返回提示信息，告诉用户使用试卷 API。

plan_exam_blueprint
# 把 exam_params 和 retrieved_contexts 转成 ExamBlueprintContent。

generate_exam_questions
# 按蓝图里的每个题型分组生成 QuestionItem。

validate_exam_questions
# 调 QuestionValidator 校验题目集合。

repair_exam_questions
# 当前只补齐缺失数量的题目，属于最小修复能力。
```

`exam_graph.py` 把节点连起来：

```text
route_entry
  -> chat_response -> END
  -> retrieve_course_context
     -> plan_exam_blueprint
     -> generate_exam_questions
     -> validate_exam_questions
     -> repair_exam_questions 或 END
```

也就是说：

- 如果只是普通聊天输入，图会返回“exam agent 可用”的说明。
- 如果传入结构化 `exam_params`，图会走完整生成链路。
- 如果校验不通过且修复次数没超过限制，会进入 repair 节点再校验。

## 4. 修改了哪些已有文件

### 4.1 注册 API 路由

修改文件：

```text
src/coursepilot/api/router.py
```

新增逻辑：

```python
from coursepilot.api.routes_exams import router as exams_router
api_router.include_router(exams_router)
```

动机：如果只写 `routes_exams.py` 但不注册，FastAPI 主应用不会暴露这些接口。这里把 Phase 3 的接口挂到统一前缀 `/api/coursepilot` 下。

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

- 统一导出常用类，减少其他模块的 import 路径混乱。
- `models/__init__.py` 对 Alembic 和 `Base.metadata.create_all()` 很重要，模型不被 import 时表结构可能不会注册。
- `exporters/__init__.py` 目前导出主类 `ExamDocxExporter`。

### 4.3 注册 CoursePilot Exam Agent

修改文件：

```text
src/agents/agents.py
src/agents/coursepilot/graphs/__init__.py
src/agents/coursepilot/states/__init__.py
```

新增 Agent id：

```text
coursepilot-exam-agent
```

动机：Agent Service Toolkit 的服务层会从 Agent Registry 里读取可用 agent。注册后，`/info` 和 agent 调用流程才能发现 Phase 3 的试卷 Agent。

### 4.4 Streamlit 页面增加试卷入口

修改文件：

```text
src/coursepilot/ui/knowledge_base_page.py
```

新增 UI 区域：

```text
Generate exam
  - Exam chapter range
  - Generation type
  - Single choice count/score
  - Multiple choice count/score
  - Judgement count/score
  - Short answer count/score
  - Additional requirements
  - Create exam blueprint
  - Confirm blueprint
  - Generate questions
  - Export exam DOCX
```

动机：给新手和教师演示用户一个不写 API 的入口。这个 UI 是最小可用版本，重点是把后端 Phase 3 流程串起来，而不是做复杂的编辑器。

### 4.5 增加测试

新增或扩展文件：

```text
tests/coursepilot/test_exam_graph.py
tests/coursepilot/test_exam_api.py
tests/coursepilot/test_validators.py
tests/coursepilot/test_exporters.py
```

动机：

- `test_exam_graph.py` 验证 LangGraph 试卷链路。
- `test_exam_api.py` 验证蓝图、确认、生成、查询、导出 API 闭环。
- `test_validators.py` 验证题目校验和重复检测。
- `test_exporters.py` 验证四类 DOCX 导出，尤其学生版不能泄露答案。

## 5. 你应该如何验收

### 5.1 最快验收：跑测试

在项目根目录执行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_exam_graph.py tests\coursepilot\test_exam_api.py tests\coursepilot\test_validators.py tests\coursepilot\test_exporters.py tests\service\test_service.py -q
```

本次审核时实际运行结果：

```text
23 passed, 9 warnings in 1.71s
```

这些测试覆盖的验收点：

- `coursepilot-exam-agent` 能被图调用。
- 试卷蓝图可以创建。
- 蓝图可以确认。
- 题目可以生成。
- 题目数量和总分校验通过。
- 空知识库课程会拒绝生成试卷。
- 四类 DOCX 文件可以导出。
- 学生版 DOCX 不包含答案和解析。

### 5.2 数据库迁移验收

如果你使用真实本地数据库，而不是测试里的临时内存库，先执行迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

验收重点：

- 数据库里应该创建 `coursepilot_exam_blueprints` 表。
- 数据库里应该创建 `coursepilot_questions` 表。
- 这两个表分别保存蓝图和题目。

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
  -Body '{"name":"Phase 3 Demo Course","description":"Course for exam generation audit"}'

$course.id
```

第二步，上传课程资料。你可以使用 `data/coursepilot_sample/` 下的示例资料，也可以换成自己的 `.txt`、`.docx` 或支持的课程文件：

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

如果你的 PowerShell 版本不支持 `-Form`，可以直接用 Streamlit 页面上传，或者用 pytest 做自动验收。

第三步，构建知识库：

```powershell
$build = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/documents/$($doc.id)/build-kb"

$build
```

第四步，创建试卷蓝图：

```powershell
$payload = @{
  chapter_range = "Chapter 1"
  generation_type = "exam"
  question_counts = @{
    single_choice = 2
    multiple_choice = 1
    judgement = 1
    short_answer = 1
  }
  score_per_question = @{
    single_choice = 2
    multiple_choice = 4
    judgement = 1
    short_answer = 10
  }
  difficulty_distribution = @{
    easy = 0.2
    medium = 0.6
    hard = 0.2
  }
} | ConvertTo-Json -Depth 5

$blueprint = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/courses/$($course.id)/exams/blueprint" `
  -ContentType "application/json" `
  -Body $payload

$blueprint.blueprint_id
$blueprint.blueprint.total_score
```

你应该看到：

- 返回 `blueprint_id`。
- `total_score` 应该是 `19`，因为 `2*2 + 1*4 + 1*1 + 1*10 = 19`。

第五步，确认蓝图：

```powershell
$confirmed = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/exams/$($blueprint.blueprint_id)/confirm"

$confirmed.status
```

你应该看到：

```text
confirmed
```

第六步，生成题目：

```powershell
$generated = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/exams/$($blueprint.blueprint_id)/generate"

$generated.questions.Count
$generated.validation_report
```

你应该重点检查：

- 题目数量是 5。
- `question_count_valid` 是 `True`。
- `score_valid` 是 `True`。
- `citation_valid` 是 `True`。
- `duplicate_valid` 是 `True`。

第七步，查询题目：

```powershell
$questions = Invoke-RestMethod `
  -Method Get `
  -Uri "http://localhost:8080/api/coursepilot/exams/$($blueprint.blueprint_id)/questions"

$questions | Select-Object question_type, score, knowledge_point, question_text
```

你应该看到四类题型：

```text
single_choice
multiple_choice
judgement
short_answer
```

第八步，导出 DOCX：

```powershell
$export = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/coursepilot/exams/$($blueprint.blueprint_id)/export"

$export.files | Select-Object file_role, file_path
```

你应该看到四个 `file_role`：

```text
student_exam
teacher_answer
detailed_explanation
answer_sheet
```

再检查文件是否存在：

```powershell
$export.files | ForEach-Object { Test-Path $_.file_path }
```

每一行都应该输出：

```text
True
```

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
4. 找到 `Generate exam` 区域。
5. 填写章节范围、题型数量和分值。
6. 点击 `Create exam blueprint`。
7. 确认返回里有 `blueprint_id`。
8. 点击 `Confirm blueprint`。
9. 点击 `Generate questions`。
10. 点击 `Export exam DOCX`。

UI 验收重点：

- 页面能显示蓝图 JSON。
- 页面能显示题目和校验报告 JSON。
- 页面能显示四个导出文件路径。
- 学生版文件打开后不应出现答案和解析。

## 6. 当前实现边界

这些不是 bug，而是 Phase 3 MVP 的边界，后续阶段可以继续增强：

1. 当前题目生成是规则化生成，不是完整 LLM 生成。
2. Prompt 文件已经准备，但主业务流程暂未读取 prompt。
3. `generate_questions()` 当前不强制要求蓝图必须先处于 `confirmed` 状态；API 和 UI 已提供确认动作，但服务层没有硬性拦截未确认蓝图。
4. `repair_exam_questions()` 当前主要补齐缺失题目数量，不会对所有质量问题做智能重写。
5. Streamlit 入口是最小可用流程，没有做复杂题目编辑、人工改单题或下载按钮美化。
6. `answer_docx_exporter.py`、`explanation_docx_exporter.py`、`answer_sheet_exporter.py` 目前是轻量子类，主要为后续样式拆分预留。

## 7. Phase 3 验收清单

你可以按下面清单逐项确认：

- [ ] `coursepilot-exam-agent` 已注册到 `src/agents/agents.py`。
- [ ] `/api/coursepilot/courses/{course_id}/exams/blueprint` 能创建蓝图。
- [ ] 空知识库课程不能创建蓝图，会提示先构建课程资料。
- [ ] 蓝图里题型、数量、分值、总分符合输入配置。
- [ ] `/confirm` 能把蓝图状态改成 `confirmed`。
- [ ] `/generate` 能生成题目并返回 `validation_report`。
- [ ] 校验报告覆盖数量、分数、选项、答案、解析、知识点、引用、重复度。
- [ ] `/questions` 能列出生成的题目。
- [ ] `/export` 能返回四个 DOCX 文件。
- [ ] 学生版 DOCX 不包含标准答案和解析。
- [ ] `pytest` 命令通过。

如果以上都通过，就可以认为 Phase 3 已经达成当前计划里的 MVP 验收标准。
