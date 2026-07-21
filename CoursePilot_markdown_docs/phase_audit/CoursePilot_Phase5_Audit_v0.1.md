# CoursePilot Phase 5 审核说明 v0.1

本文档用于解释 Phase 5 做了什么、为什么这样做、对应文件在哪里，以及你应该如何运行命令来验收。

对照文件：

- `PLAN.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

## 1. Phase 5 的目标

Phase 5 的目标是“测试、评估、README 与 Demo 固化”。

换成新手更容易理解的话，Phase 0 到 Phase 4 已经把 CoursePilot 的主要业务能力做出来了：

1. 课程、资料上传、知识库构建和检索。
2. 教学设计生成和 DOCX 导出。
3. 试卷蓝图、题目生成、校验和四类 DOCX 导出。
4. PPT 大纲、PPTX 导出、审核和 approved 内容写回知识库。

Phase 5 不再重点新增某个业务功能，而是把前面这些能力固化成一个可以展示、可以回归测试、可以本地复现、可以写进简历的 MVP：

1. 补齐 `tests/coursepilot/` 业务测试。
2. 保证原 Agent Service Toolkit 的关键测试不被破坏。
3. 增加确定性的评估指标和样例评估脚本。
4. 放入示例课程资料，方便演示和复现。
5. 更新 README，说明项目背景、AST 改造关系、Chatchat 参考边界、启动方式、Demo 流程、评估结果和简历亮点。
6. 通过 Docker Compose 配置固化 FastAPI、Streamlit、PostgreSQL、storage、Chroma 的 Demo 运行方式。

PRD 里强调本项目既是教师备课系统，也是 Agent / 大模型应用开发方向的简历项目。技术架构文档也要求最终能通过 README 复现实验流程，并能用测试和评估指标证明系统质量。因此 Phase 5 的核心判断标准不是“又多了一个接口”，而是“这个项目能不能被别人可靠地跑起来、测起来、看懂并评估”。

## 2. Phase 5 任务对照

| 计划任务 | 计划目标 | 当前实现情况 | 主要文件 |
| --- | --- | --- | --- |
| T5-001 | 迁移并扩展原测试体系 | 已实现 | `tests/coursepilot/`, `tests/service/test_service.py`, `tests/agents/test_agent_loading.py`, `tests/core/test_settings.py` |
| T5-002 | 实现评估脚本 | 已实现 | `src/coursepilot/evals/metrics.py`, `src/coursepilot/evals/run_sample_eval.py` |
| T5-003 | 完成 README 与 Demo | 已实现 | `README.md`, `README.zh-CN.md`, `data/coursepilot_sample/`, `compose.yaml` |
| 计划补充 | 示例课程资料 | 已实现 | `data/coursepilot_sample/` |
| 计划补充 | Docker Compose Demo 配置 | 已配置并通过配置解析 | `compose.yaml`, `.env.example` |
| 计划补充 | Agent workflow 展示图 | 已提供 lesson workflow 图 | `src/agents/coursepilot/workflow.mmd` |

需要注意：Phase 5 的评估脚本是确定性样例评估，不是调用真实 LLM 的在线 benchmark。这样做的动机是让评估结果在本地、测试和 CI 里稳定复现。

## 3. 新增了哪些文件

### 3.1 CoursePilot 全量业务测试

新增或扩展目录：

```text
tests/coursepilot/
```

当前包含：

```text
conftest.py
test_phase0_setup.py
test_course_api.py
test_document_upload.py
test_parser.py
test_chunker.py
test_retriever.py
test_lesson_api.py
test_lesson_graph.py
test_exam_api.py
test_exam_graph.py
test_ppt_api.py
test_ppt_graph.py
test_validators.py
test_exporters.py
test_write_back.py
test_evals.py
```

动机：

- Phase 0 到 Phase 4 产生了很多业务模块，只靠手工点 UI 很难长期保证不回退。
- 这些测试按模块覆盖 CoursePilot 的关键链路：API、parser、chunker、retriever、Agent graph、validator、exporter、审核写回和评估指标。
- 原 Agent Service Toolkit 的测试也继续保留，避免 CoursePilot 改造破坏底座。

`tests/coursepilot/conftest.py` 是测试基础设施：

```python
@pytest.fixture
def coursepilot_client(tmp_path, monkeypatch):
    # 1. 创建一个 SQLite 内存数据库。
    #    这样测试不会污染你的真实数据库。
    engine = create_engine("sqlite://", ...)

    # 2. 用 SQLAlchemy metadata 创建所有 CoursePilot 表。
    Base.metadata.create_all(engine)

    # 3. 把 CoursePilot 的 storage 和 chroma 目录临时改到 tmp_path。
    #    这样测试产生的上传文件、导出文件、向量库文件都会在临时目录里。
    monkeypatch.setattr(settings, "COURSEPILOT_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "COURSEPILOT_CHROMA_DIR", str(tmp_path / "chroma"))

    # 4. 覆盖 FastAPI 的 get_session dependency。
    #    测试请求会使用内存数据库 session。
    app.dependency_overrides[get_session] = override_get_session

    # 5. 返回 TestClient，让每个测试可以像发 HTTP 请求一样调用 API。
```

这段 fixture 的价值很大：它让 CoursePilot 的 API 测试变成“近似真实 HTTP 调用”，但又不会依赖真实 Postgres、真实 storage 或真实 Chroma 目录。

各测试文件的覆盖重点：

| 测试文件 | 覆盖内容 |
| --- | --- |
| `test_phase0_setup.py` | CoursePilot 包结构、配置项、数据库 metadata |
| `test_course_api.py` | 课程增删改查 |
| `test_document_upload.py` | 文件上传记录、非法类型拒绝 |
| `test_parser.py` | txt、markdown、xlsx parser |
| `test_chunker.py` | chunk 切分、metadata、知识点提取 |
| `test_retriever.py` | 构建知识库、课程隔离检索、失败状态 |
| `test_lesson_api.py` | 教学设计 API、导出和无资料拒绝 |
| `test_lesson_graph.py` | lesson LangGraph workflow |
| `test_exam_api.py` | 试卷蓝图、确认、题目生成、四类导出 |
| `test_exam_graph.py` | exam LangGraph workflow |
| `test_ppt_api.py` | PPT 生成、导出、审核、写回、verified 检索 |
| `test_ppt_graph.py` | PPT LangGraph workflow |
| `test_validators.py` | Lesson、Question、PPT validator 和重复检测 |
| `test_exporters.py` | Lesson DOCX、Exam DOCX、PPTX 导出 |
| `test_write_back.py` | 非法审核目标和 rejected 不写回 |
| `test_evals.py` | 评估指标计算和样例评估输入 |

### 3.2 评估指标模块

新增文件：

```text
src/coursepilot/evals/__init__.py
src/coursepilot/evals/metrics.py
src/coursepilot/evals/run_sample_eval.py
```

动机：

PRD 第 15 节提出了 RAG、教学设计、试卷和系统工程指标。Phase 5 先实现一组可稳定复现的工程评估指标，用于 README 展示和回归验证。

`metrics.py` 定义了评估输入结构：

```python
class RetrievalCase(BaseModel):
    # 一条 RAG 检索评估样例。
    # expected_chunk_ids 是理想情况下应该被召回的 chunk。
    # retrieved_chunk_ids 是实际检索返回的 chunk。
    query: str
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str] = []


class CitationCase(BaseModel):
    # 一条引用覆盖率样例。
    # 如果 citation_chunk_ids 非空，说明这条生成内容有引用来源。
    item_id: str
    citation_chunk_ids: list[str] = []


class SchemaCase(BaseModel):
    # 一条结构化输出是否通过 schema 校验的样例。
    item_id: str
    schema_valid: bool


class QuestionCountCase(BaseModel):
    # 用于比较预期题量和实际题量。
    expected_counts: dict[str, int]
    actual_counts: dict[str, int]
```

`CoursePilotEvaluator.evaluate()` 汇总生成最终报告：

```python
class CoursePilotEvaluator:
    def evaluate(self, payload):
        # 每个指标由一个单独方法计算，最后汇总到 CoursePilotEvalReport。
        return CoursePilotEvalReport(
            rag_recall_at_k=self.rag_recall_at_k(...),
            citation_coverage=self.citation_coverage(...),
            schema_pass_rate=self.schema_pass_rate(...),
            question_count_accuracy=self.question_count_accuracy(...),
            duplicate_rate=payload.duplicate_rate,
            answer_completeness=self.answer_completeness(...),
            export_success_rate=self.export_success_rate(...),
        )
```

各指标含义：

| 指标 | 代码字段 | 解释 |
| --- | --- | --- |
| RAG Recall@K | `rag_recall_at_k` | 预期 chunk 有多少被检索结果命中 |
| Citation Coverage | `citation_coverage` | 生成内容中带引用的比例 |
| Schema Pass Rate | `schema_pass_rate` | Lesson/Exam/PPT 等结构化输出通过 schema 的比例 |
| Question Count Accuracy | `question_count_accuracy` | 实际题量与配置题量一致的比例 |
| Duplicate Rate | `duplicate_rate` | 重复题比例，直接使用上游检测结果 |
| Answer Completeness | `answer_completeness` | 题目是否同时有答案和解析 |
| Export Success Rate | `export_success_rate` | 导出文件是否存在且非空 |

`run_sample_eval.py` 是样例评估入口：

```python
def build_sample_payload(sample_dir: Path) -> CoursePilotEvalInput:
    # 1. 读取 data/coursepilot_sample/ 下的样例文件。
    # 2. 构造固定的 retrieval/citation/schema/question/export 样例。
    # 3. 返回 CoursePilotEvalInput。


def main():
    # 1. 解析 --sample-dir 和 --output 参数。
    # 2. 调用 CoursePilotEvaluator().evaluate(payload)。
    # 3. 把 JSON 打印到终端。
    # 4. 如果传了 --output，就写入指定 JSON 文件。
```

### 3.3 示例课程资料

新增目录：

```text
data/coursepilot_sample/
```

当前包含：

```text
人工智能：从算法到系统-知识图谱.xlsx
人工智能：从算法到系统教学大纲V3.doc
教材-人工智能：从算法到系统.docx
```

动机：

- README 里的 Demo 不能只写“上传一个文件”，否则新用户不知道用什么资料测试。
- 示例资料让课程创建、上传、构建知识库、检索、教学设计、试卷、PPT 和审核写回都有可演示输入。
- 评估脚本也会读取这个目录，用于计算 `export_success_rate`。

### 3.4 中文 README

新增文件：

```text
README.zh-CN.md
```

动机：

- 项目文档和用户需求主要是中文，中文 README 方便学习、面试讲解和本地复现。
- 英文 `README.md` 保留项目对外说明和原 AST 基础介绍；中文 README 更适合解释 CoursePilot 业务闭环。

中文 README 覆盖：

- 核心能力。
- 目录结构。
- 架构说明。
- 快速启动。
- Demo 复现流程。
- API 概览。
- 测试命令。
- 评估流程。
- 简历亮点。

### 3.5 Agent workflow 图

新增文件：

```text
src/agents/coursepilot/workflow.mmd
```

动机：

- Phase 5 的 README 目标包含 Agent workflow 图。
- Mermaid 文件可以被 README、文档或演示材料引用。
- 当前图主要展示 lesson agent 的 workflow：route、retrieve、extract、plan、generate、validate、repair。

当前边界：

- 这个 Mermaid 图只覆盖 lesson workflow，没有完整画出 exam 和 ppt 两条图。

## 4. 修改了哪些已有文件

### 4.1 README 固化 CoursePilot 项目说明

修改文件：

```text
README.md
```

新增或强化内容：

```text
CoursePilot is a teacher-facing course preparation assistant agent system built on Agent Service Toolkit.
Langchain-Chatchat is used only as a RAG and knowledge-base design reference.
```

动机：

- 明确本项目不是从零重写，而是在 Agent Service Toolkit 上做业务扩展。
- 明确 Chatchat 只是参考 RAG/知识库设计，没有复制它的 WebUI、配置系统、agent executor 或数据库结构。
- 这是 PRD 和技术架构里反复强调的边界，面试时也很重要。

README 中新增的 CoursePilot 主流程：

```text
Create course
  -> upload textbook / syllabus / knowledge graph files
  -> build Chroma knowledge base
  -> search RAG chunks with citations
  -> generate lesson design JSON
  -> export lesson DOCX
  -> generate exam blueprint and questions
  -> export student exam, answer key, explanation, answer sheet
  -> generate PPT outline JSON
  -> export editable PPTX
  -> approve generated content
  -> write approved PPT content back to Chroma with verified=true
```

这段流程对应 Phase 0 到 Phase 4 的完整闭环。

README 中新增的评估命令：

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m coursepilot.evals.run_sample_eval --output storage\coursepilot_eval_report.json
```

README 中新增的回归测试命令：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot tests\service\test_service.py tests\agents\test_agent_loading.py tests\core\test_settings.py -q
```

### 4.2 Streamlit 默认进入 CoursePilot Demo

修改文件：

```text
src/streamlit_app.py
src/coursepilot/ui/knowledge_base_page.py
```

动机：

- 原 Agent Service Toolkit 的 Streamlit 页面主要是聊天 Demo。
- CoursePilot 需要给教师备课场景一个更直接的演示入口。
- 因此侧边栏新增 `App mode`，默认进入 `CoursePilot Knowledge Base`，同时保留原 `Agent Chat`。

关键逻辑：

```python
with st.sidebar:
    app_mode = st.radio(
        "App mode",
        options=["CoursePilot Knowledge Base", "Agent Chat"],
        index=0,
    )

if app_mode == "CoursePilot Knowledge Base":
    render_knowledge_base_page(...)
    return
```

`knowledge_base_page.py` 则承接完整 Demo 流程：

- 创建课程。
- 上传资料。
- 构建知识库。
- 检索知识库。
- 生成和导出教学设计。
- 生成试卷和导出 DOCX。
- 生成 PPT 和导出 PPTX。
- 审核并写回知识库。

### 4.3 Docker Compose Demo 固化

修改文件：

```text
compose.yaml
.env.example
```

动机：

- Phase 5 要求 Demo 可复现，不应该只依赖“我本机刚好能跑”。
- Docker Compose 固定了 `postgres`、`agent_service`、`streamlit_app` 三个服务。
- storage 和 Chroma 目录被挂载出来，避免容器重启后上传文件和向量库数据丢失。

`compose.yaml` 里的关键服务：

```yaml
postgres:
  # 提供 PostgreSQL 数据库。

agent_service:
  # FastAPI 后端，暴露 8080。
  # 挂载 ./storage 和 ./chroma_db。

streamlit_app:
  # Streamlit 前端，暴露 8501。
  # AGENT_URL 指向 http://agent_service:8080。
```

`.env.example` 新增 CoursePilot 配置：

```text
COURSEPILOT_DATABASE_URL=
COURSEPILOT_STORAGE_DIR=./storage
COURSEPILOT_CHROMA_DIR=./chroma_db
COURSEPILOT_MAX_REPAIR_ROUNDS=2
COURSEPILOT_DUPLICATE_THRESHOLD=0.85
COURSEPILOT_ENABLED=true
```

这些配置和 Phase 0 的底座设置一致，Phase 5 把它们写入示例环境文件，方便别人启动项目。

### 4.4 原 AST 测试和 CoursePilot 测试共同保留

修改或保留范围：

```text
tests/service/
tests/agents/
tests/core/
tests/app/
tests/client/
tests/coursepilot/
```

动机：

- CoursePilot 是基于 Agent Service Toolkit 改造，不应该破坏原服务层、agent registry、client、streamlit shell。
- Phase 5 的测试策略是“业务测试新增，底座测试保留”，而不是只测 CoursePilot。

## 5. 你应该如何验收

### 5.1 最快验收：运行 README 推荐回归测试

在项目根目录执行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot tests\service\test_service.py tests\agents\test_agent_loading.py tests\core\test_settings.py -q
```

本次审核时实际运行结果：

```text
75 passed, 10 warnings in 3.22s
```

这个命令覆盖：

- CoursePilot 全部业务测试。
- FastAPI service 基础测试。
- Agent loading 测试。
- core settings 测试。

### 5.2 全量 pytest 验收

如果你想更严格地验证整个仓库，可以执行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest -q
```

本次审核时实际运行结果：

```text
162 passed, 2 skipped, 15 warnings in 27.66s
```

这说明当前工作区里原 AST 测试和 CoursePilot 测试都能跑通。

常见 warnings 说明：

- LangGraph supervisor 的 deprecated import warning：来自依赖包或原示例代码，不影响当前验收。
- `HashingEmbeddings` relevance score warning：本地确定性 embedding 的相关性分数可能小于 0，不影响 `verified=true` 写回检索的功能验收。
- 个别 resource/deprecation warning：测试通过，属于后续清理项。

### 5.3 评估脚本验收

执行：

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m coursepilot.evals.run_sample_eval --output storage\coursepilot_eval_report.json
```

本次审核时实际输出：

```json
{
  "answer_completeness": 1.0,
  "citation_coverage": 1.0,
  "duplicate_rate": 0.0,
  "export_success_rate": 1.0,
  "question_count_accuracy": 1.0,
  "rag_recall_at_k": 1.0,
  "schema_pass_rate": 1.0
}
```

再检查输出文件是否存在：

```powershell
Test-Path storage\coursepilot_eval_report.json
Get-Content storage\coursepilot_eval_report.json
```

`Test-Path` 应该输出：

```text
True
```

### 5.4 Docker Compose 配置验收

先检查 Compose 文件能否被 Docker 正确解析：

```powershell
docker compose config --quiet
```

本次审核时该命令执行成功，无错误输出。

完整启动 Demo 的命令是：

```powershell
docker compose up --build
```

启动后检查服务状态：

```powershell
docker compose ps
```

期望看到：

```text
postgres
agent_service
streamlit_app
```

并且后端和前端可以访问：

```text
http://localhost:8080/info
http://localhost:8501
```

说明：本次审核执行了 `docker compose config --quiet` 来验证配置可解析；没有长时间执行完整 `docker compose up --build` 构建和启动容器。完整 Docker 启动仍建议你在本机 Docker Desktop 正常运行时手工执行。

### 5.5 README Demo 复现验收

按 README 的顺序执行：

1. 启动 FastAPI：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

2. 启动 Streamlit：

```powershell
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py
```

3. 打开：

```text
http://localhost:8501
```

4. 在页面中完成：

```text
创建课程
-> 上传 data/coursepilot_sample/ 中的示例资料
-> 构建知识库
-> 检索知识库
-> 生成教学设计并导出 DOCX
-> 生成试卷 blueprint
-> 确认 blueprint
-> 生成题目并导出四类 DOCX
-> 生成 PPT outline
-> 导出 PPTX
-> approve PPT
-> write back approved PPT
-> 使用 verified_only=true 检索
```

验收重点：

- 能看到 CoursePilot 页面，而不是只看到原聊天页面。
- 上传资料后可以构建知识库。
- 检索结果包含 `chunk_id`、`source_type`、`score`、`verified`。
- DOCX/PPTX 文件能导出。
- `approved` 写回后，`verified_only=true` 能搜到 `source_type=reviewed_ppt` 的内容。

## 6. 当前实现边界

这些不是 bug，而是 Phase 5 当前 MVP 的边界：

1. 评估脚本使用确定性样例输入，不是真实 LLM 在线评测。
2. `run_sample_eval.py` 的样例指标目前偏“展示和回归”，不是严肃学术 benchmark。
3. Mermaid workflow 图目前主要覆盖 lesson graph，没有完整覆盖 exam 和 ppt graph。



## 7. Phase 5 验收清单

你可以按下面清单逐项确认：

- [ ] `tests/coursepilot/` 存在，并覆盖 CoursePilot 主要业务模块。
- [ ] README 推荐回归命令通过。
- [ ] 全量 `pytest -q` 通过。
- [ ] `src/coursepilot/evals/metrics.py` 实现核心评估指标。
- [ ] `src/coursepilot/evals/run_sample_eval.py` 能输出 JSON。
- [ ] `storage/coursepilot_eval_report.json` 能被生成。
- [ ] `data/coursepilot_sample/` 下有示例课程资料。
- [ ] `README.md` 说明 CoursePilot 基于 Agent Service Toolkit 改造。
- [ ] `README.md` 说明 Langchain-Chatchat 只作为 RAG/KB 设计参考。
- [ ] `README.md` 提供本地启动、Streamlit、Docker、Demo 和评估命令。
- [ ] `README.zh-CN.md` 提供中文复现说明。
- [ ] `docker compose config --quiet` 无错误。
- [ ] Streamlit 默认可以进入 CoursePilot Demo 页面。

如果以上都通过，就可以认为 Phase 5 已经达成当前计划里的 MVP 验收标准。
