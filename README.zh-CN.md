# CoursePilot

CoursePilot 是面向教师备课场景的课程资源生成助手，采用 workflow-first 的 Agent 架构。它可以把教材、教学大纲、知识图谱等课程资料构建为课程私有知识库，并在此基础上生成教学设计、试卷/作业、答案解析和 PPT 大纲，支持来源追溯、结构化校验、文件导出、教师审核和审核内容写回。

[English README](README.md)

版本化 CourseRAG 子系统的稳定 API、增量/索引架构、可信网关边界和运行限制见
[`docs/courserag/`](docs/courserag/README.md)。

## 核心能力

- 动态课程知识库：上传课程资料，完成解析、切分、向量化，并写入按课程隔离的 Chroma collection。
- Workflow-first Agent：使用三条 LangGraph 工作流分别处理教学设计、试卷/作业生成和 PPT 大纲生成。
- 结构化 LLM 生成：要求模型输出 JSON，用 Pydantic schema 校验，并在失败时执行 repair 或 deterministic fallback。
- 来源可追溯：教学设计、题目和 PPT 大纲会保留检索到的课程资料引用。
- 文件导出：DOCX 和 PPTX 由 exporter 根据结构化数据渲染生成，LLM 不直接生成 Office 文件。
- 教师审核闭环：审核通过的教学设计、题目和 PPT 大纲可以写回 verified 知识库，供后续检索和生成使用。
- 工程元数据：GenerationTask 会记录 workflow thread id、prompt hash、LLM attempt、token usage 估算、fallback 次数和校验报告。

## 产品工作流

```text
创建课程
  -> 上传教材 / 教学大纲 / 知识图谱文件
  -> 构建按课程隔离的 Chroma 知识库
  -> 检索带来源引用的课程上下文
  -> 生成教学设计、试卷蓝图/题目、PPT 大纲
  -> 校验结构化 JSON，必要时修复
  -> 导出 DOCX/PPTX 文件
  -> 教师审核生成内容
  -> 将审核通过的内容写回 verified 知识库
```

## 系统架构

```text
FastAPI service
  -> 最小 prompt-entry Agent API
  -> /api/coursepilot/* 产品 API
  -> CoursePilot service 层与数据库事务
  -> LangGraph lesson / exam / PPT 工作流
  -> PostgreSQL 业务表
  -> Chroma 向量集合
  -> 本地上传与导出文件存储

Streamlit app
  -> CoursePilotClient
  -> CoursePilot 工作流页面
```

主要实现分层：

- `src/coursepilot/`：产品 API、services、schemas、ORM models、RAG、LLM helper、validators、exporters 和 Streamlit UI 模块。
- `src/agents/coursepilot/`：教学设计、试卷/作业、PPT 三条 LangGraph 工作流。
- `src/service/`：FastAPI 应用、鉴权、prompt-entry agent 端点，以及 CoursePilot router 挂载。
- `src/client/`：用于产品 API 的 `CoursePilotClient`，以及用于 prompt-entry agent 的最小 `AgentClient`。
- `alembic/`：CoursePilot 业务数据库迁移。

## API 边界

CoursePilot 有两类刻意分开的 API。

### 产品 API

`/api/coursepilot/*` 是正式产品 API，负责结构化输入、数据库写入、文件导出、审核和知识库写回。

代表性接口：

| 模块 | Endpoint | 用途 |
| --- | --- | --- |
| 课程 | `POST /api/coursepilot/courses` | 创建课程 |
| 文档 | `POST /api/coursepilot/courses/{course_id}/documents/upload` | 上传课程资料 |
| 知识库 | `POST /api/coursepilot/documents/{document_id}/build-kb` | 解析、切分、向量化并入库 |
| 知识库 | `POST /api/coursepilot/courses/{course_id}/kb/search` | 检索课程上下文 |
| 教学设计 | `POST /api/coursepilot/courses/{course_id}/lessons/generate` | 生成教学设计 |
| 教学设计 | `POST /api/coursepilot/lessons/{lesson_id}/export` | 导出教学设计 DOCX |
| 试卷 | `POST /api/coursepilot/courses/{course_id}/exams/blueprint` | 生成试卷蓝图 |
| 试卷 | `POST /api/coursepilot/exams/{blueprint_id}/generate` | 蓝图确认后生成题目 |
| 试卷 | `POST /api/coursepilot/exams/{blueprint_id}/export` | 导出学生卷、答案、解析和答题卡 |
| PPT | `POST /api/coursepilot/lessons/{lesson_id}/ppt/generate` | 基于教学设计生成 PPT 大纲 |
| PPT | `POST /api/coursepilot/ppt/{outline_id}/export` | 导出可编辑 PPTX |
| 审核 | `POST /api/coursepilot/reviews` | 记录教师审核状态 |
| 审核 | `POST /api/coursepilot/reviews/{review_id}/write-back` | 将审核通过内容写回 verified 知识库 |
| 文件 | `GET /api/coursepilot/files/{file_id}/download` | 下载导出文件 |

服务启动后，完整交互式接口文档可在 FastAPI `/docs` 查看。

### Prompt-Entry Agent API

通用 Agent API 只作为兼容和提示入口保留：

- `GET /info`
- `POST /invoke` 和 `POST /{agent_id}/invoke`
- `POST /stream` 和 `POST /{agent_id}/stream`
- `POST /history`
- `GET /health`

当前只注册三个 prompt-entry agent：

- `coursepilot-lesson-agent`，默认 agent
- `coursepilot-exam-agent`
- `coursepilot-ppt-agent`

这些端点不承载 CoursePilot 的教学设计、试卷或 PPT 结构化业务参数。正式业务流程请使用 `/api/coursepilot/*`。

## 快速开始

### 环境要求

- Python 3.11、3.12 或 3.13
- `uv`
- PostgreSQL，用于 CoursePilot 产品业务数据库
- Docker 和 Docker Compose，用于容器化启动

### 本地启动

安装依赖：

```powershell
uv sync --frozen
```

创建本地配置：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中配置 CoursePilot 使用的 PostgreSQL。可以直接设置 `COURSEPILOT_DATABASE_URL`，也可以填写 `POSTGRES_*` 变量。

执行业务数据库迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
```

启动 FastAPI 服务：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

另开一个终端启动 Streamlit：

```powershell
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py
```

访问：

- Streamlit 页面：`http://localhost:8501`
- FastAPI 文档：`http://localhost:8080/docs`
- 健康检查：`http://localhost:8080/health`

### Docker Compose

启动 PostgreSQL、FastAPI 和 Streamlit：

```powershell
docker compose up --build
```

如果数据库 volume 是新建的，需要对 Compose 数据库执行迁移：

```powershell
docker compose exec agent_service python -m alembic upgrade head
```

打开 `http://localhost:8501` 使用前端页面。

## 配置说明

复制 `.env.example` 为 `.env`，并按当前环境填写必要配置。

### 服务与鉴权

- `HOST`、`PORT`、`MODE`、`LOG_LEVEL`：Web 服务运行配置。
- `AUTH_SECRET`：可选 bearer token。设置后，prompt-entry API 和 CoursePilot 产品 API 都需要 `Authorization: Bearer <AUTH_SECRET>`。

### 模型

CoursePilot 支持 OpenAI、DeepSeek、OpenAI-compatible endpoint，以及用于本地测试的 fake model。

生产风格的 OpenAI-compatible 生成配置示例：

```env
COMPATIBLE_BASE_URL=https://your-compatible-endpoint/v1
COMPATIBLE_MODEL=your-chat-model
COMPATIBLE_API_KEY=your-key
COURSEPILOT_GENERATION_MODE=llm
```

生成模式：

- `auto`：有真实模型配置时使用 LLM，否则使用 deterministic fallback。
- `llm`：强制走真实 LLM，并在服务启动时执行健康检查。
- `deterministic`：强制使用本地确定性生成，适合测试和 smoke demo。

### 数据库与存储

- `DATABASE_TYPE` 和 `SQLITE_DB_PATH` 用于 LangGraph prompt-agent persistence，也就是 `/history`。
- CoursePilot 业务数据使用 PostgreSQL，通过 `COURSEPILOT_DATABASE_URL` 或 `POSTGRES_*` fallback 变量配置。
- `COURSEPILOT_STORAGE_DIR` 存放上传文件和导出文件。
- `COURSEPILOT_CHROMA_DIR` 存放 Chroma 向量集合。

### Embedding

生产 embedding 配置示例：

```env
COURSEPILOT_EMBEDDING_PROVIDER=openai-compatible
COURSEPILOT_EMBEDDING_MODEL=your-embedding-model
COURSEPILOT_EMBEDDING_BASE_URL=https://your-compatible-endpoint/v1
COURSEPILOT_EMBEDDING_API_KEY=your-key
```

未配置 embedding 时，CoursePilot 使用确定性的 hashing embedding，便于测试和本地 smoke demo。

### LLM 可靠性与用量统计

- `COURSEPILOT_LLM_TIMEOUT_SECONDS`：单次 LLM 调用超时时间，默认 `120` 秒。
- `COURSEPILOT_LLM_MAX_RETRIES`：进入 fallback 前的重试次数。
- `COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK`：真实评测时设为 `true`，禁止失败后使用 deterministic fallback。
- `COURSEPILOT_LLM_HEALTH_CHECK_MODE`：`llm` 生成模式下的启动健康检查方式。
- `COURSEPILOT_TOKENIZER_PATH`：DeepSeek tokenizer 路径，用于 provider 未返回 usage metadata 时估算 token usage。
- `COURSEPILOT_EMBEDDING_MAX_RETRIES`：Embedding 429 限流后的最大重试次数，默认 `4`。
- `COURSEPILOT_EMBEDDING_RETRY_BASE_SECONDS`：Embedding 429 首次退避时间，默认 `15` 秒。
- `COURSEPILOT_EMBEDDING_RETRY_MAX_SECONDS`：Embedding 429 单次退避上限，默认 `120` 秒。
- `COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE`：文档入库时 chunk 知识点抽取模式，支持 `auto`、`llm`、`deterministic`。
- `COURSEPILOT_IDEMPOTENCY_LEASE_SECONDS`：幂等请求记录的执行保护窗口，默认 `14400` 秒。
- `COURSEPILOT_ASYNC_WORKER_ENABLED`：是否在 API 进程中启动数据库任务 worker，默认 `true`。
- `COURSEPILOT_ASYNC_WORKER_POLL_SECONDS`：worker 空闲轮询间隔，默认 `1` 秒。
- `COURSEPILOT_ASYNC_TASK_LEASE_SECONDS`：worker 任务租约长度，默认 `300` 秒；执行期间会自动续租。
- `COURSEPILOT_ASYNC_WORKER_SHUTDOWN_TIMEOUT_SECONDS`：服务关闭时等待 worker 的时间，默认 `10` 秒。

### P0 异步任务与幂等

知识库构建、lesson 生成、exam 蓝图/题目生成和 PPT 大纲生成接口使用数据库异步任务。对应 POST 只负责入队并快速返回 `202 Accepted`：

```json
{
  "task_id": "...",
  "status": "pending",
  "status_url": "/api/coursepilot/tasks/..."
}
```

客户端通过 `GET /api/coursepilot/tasks/{task_id}` 轮询 `pending`、`running`、`completed`、`needs_review` 或 `failed` 状态。终态响应包含 `result` 或 `error_message`。数据库 worker 使用租约和心跳领取任务；服务异常退出后，租约过期的 `running` 任务可以重新领取。

这些接口和课程创建接口支持可选的 `Idempotency-Key`。同一接口使用相同 key 和参数时会返回同一个任务；参数不同返回 `409`。已完成任务会持续重放；明确失败的异步任务在下一次同 key 请求时重新入队，便于评测 `--resume` 重试。`CoursePilotClient` 的高层方法会自动完成“入队、轮询、返回最终结果”，直接调用 HTTP API 的客户端需要自行轮询。

升级后先执行 `python -m alembic upgrade head`，创建幂等表并为 `coursepilot_generation_tasks` 增加队列、租约和结果字段。

## 样例数据

样例课程文件位于 `data/coursepilot_sample/`，当前包含：

- 教材 / 教学资料
- 知识图谱 XLSX

这些文件可用于本地上传、知识库构建、检索和生成 smoke test。

## 测试与评估

运行主测试套件：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

运行格式、lint 和类型检查：

```powershell
.\.venv\Scripts\python.exe -m ruff format --check
.\.venv\Scripts\python.exe -m ruff check
.\.venv\Scripts\python.exe -m mypy src/
```

运行确定性评估指标：

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m coursepilot.evals.run_sample_eval --output storage\coursepilot_eval_report.json
```

使用 `data/sample_files/` 中用户提供、内容不同且相互独立的一个 DOCX 和一个 PDF
运行 P00 本地 B0 Smoke：

```powershell
$env:PYTHONPATH='src'
uv run python -m coursepilot.evals.run_b0_smoke `
  --sample-dir data/sample_files `
  --output docs/refactor/baselines/b0/05_b0_smoke_report.json
```

B0 Runner 使用隔离的 SQLite/Chroma、deterministic 生成和 hashing embedding，不调用
外部 Provider；报告只保存文件指纹与结构结果，不保存教材正文。检索 Probe 仅用于非 Gold
连通性检查，不得作为质量指标发布。运行 gated 样例专项测试时设置
`COURSEPILOT_RUN_B0_SAMPLE_SMOKE=1`。

### 真实 LLM 评测完整流程

真实评测使用独立的 PostgreSQL database、`storage_eval/` 和 `chroma_db_eval/`，不会写入默认 demo 数据。评测依次执行课程创建、样例文件上传、知识库构建、检索测试、lesson/exam/PPT 生成与导出，最后汇总数据库、Chroma、引用、schema 和导出指标。

知识库构建会对每个 chunk 调用真实 LLM 抽取知识点，并调用显式配置的 embedding Provider。大型样例教材可能产生数百个 chunk 和数百次模型调用。开始前应确认模型账户余额、限流和预计成本；不要用真实评测命令做连通性 smoke test。

#### 1. 准备评测配置

在项目根目录打开 PowerShell。如果 `.env.eval` 尚不存在，从模板创建；已经存在时不要再次复制，以免覆盖真实密钥：

```powershell
if (-not (Test-Path .env.eval)) {
  Copy-Item .env.eval.example .env.eval
}
```

编辑 `.env.eval`，至少确认下列配置。不要把真实 API key 提交到 Git；`.env.eval` 已在 `.gitignore` 中忽略。

```env
# OpenAI-compatible chat/structured-output endpoint
COMPATIBLE_BASE_URL=https://your-chat-endpoint/v1
COMPATIBLE_MODEL=your-chat-model
COMPATIBLE_API_KEY=your-chat-api-key
USE_FAKE_MODEL=false
DEFAULT_MODEL=openai-compatible

# 强制真实 LLM，并禁止 deterministic fallback
COURSEPILOT_GENERATION_MODE=llm
COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK=true
COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE=llm

# OpenAI-compatible embedding endpoint
COURSEPILOT_EMBEDDING_PROVIDER=openai-compatible
COURSEPILOT_EMBEDDING_MODEL=your-embedding-model
COURSEPILOT_EMBEDDING_BASE_URL=https://your-embedding-endpoint/v1/
COURSEPILOT_EMBEDDING_API_KEY=your-embedding-api-key

# 数据库异步任务 worker
COURSEPILOT_ASYNC_WORKER_ENABLED=true
COURSEPILOT_ASYNC_WORKER_POLL_SECONDS=1
COURSEPILOT_ASYNC_TASK_LEASE_SECONDS=300

# 单次 LLM 请求和评测客户端轮询上限
COURSEPILOT_LLM_TIMEOUT_SECONDS=120
COURSEPILOT_LLM_MAX_RETRIES=2
COURSEPILOT_EVAL_BUILD_KB_TIMEOUT_SECONDS=7200
COURSEPILOT_EVAL_GENERATION_TIMEOUT_SECONDS=1800

# Embedding 429 限流重试：15、30、60、120 秒
COURSEPILOT_EMBEDDING_MAX_RETRIES=4
COURSEPILOT_EMBEDDING_RETRY_BASE_SECONDS=15
COURSEPILOT_EMBEDDING_RETRY_MAX_SECONDS=120
```

`COURSEPILOT_LLM_TIMEOUT_SECONDS` 控制一次 LLM HTTP 调用；`COURSEPILOT_EVAL_BUILD_KB_TIMEOUT_SECONDS` 和 `COURSEPILOT_EVAL_GENERATION_TIMEOUT_SECONDS` 控制评测客户端等待整个异步任务的总时间，二者不是同一层超时。

#### 2. 构建镜像、迁移数据库并启动服务

先定义本次终端使用的 Compose 参数：

```powershell
$composeArgs = @(
  '--env-file', '.env.eval',
  '-f', 'compose.yaml',
  '-f', 'compose.eval.yaml'
)
```

PowerShell 变量不会跨终端共享；后续在新的终端执行 Docker 命令时，需要先重复上面的 `$composeArgs` 定义。

首次运行、源码或依赖发生变化时，按当前工作区源码重建镜像。`--no-cache` 耗时较长，但可以避免使用旧源码层：

```powershell
docker compose @composeArgs pull postgres
docker compose @composeArgs build --pull --no-cache agent_service streamlit_app
```

先只启动评测数据库，执行迁移，再启动 API 和 Streamlit。该顺序可以避免新 worker 在旧表结构上启动：

```powershell
docker compose @composeArgs up -d --wait postgres
docker compose @composeArgs run --rm --no-deps agent_service python -m alembic upgrade head
docker compose @composeArgs up -d --force-recreate --wait agent_service streamlit_app
docker compose @composeArgs ps
```

如果源码、镜像和 `.env.eval` 均未变化，后续恢复时不需要重新 build，只需执行：

```powershell
docker compose @composeArgs up -d --wait postgres agent_service streamlit_app
```

#### 3. 运行前检查

三个服务都应显示为 `healthy`，API 和 UI 健康检查应分别返回 `ok`：

```powershell
docker compose @composeArgs ps
Invoke-RestMethod http://localhost:8080/health
(Invoke-WebRequest -UseBasicParsing http://localhost:8501/_stcore/health).Content
```

以下命令只打印非敏感配置，用于确认容器实际加载了真实 LLM、配置的 embedding Provider、严格 fallback 和异步 worker 设置：

```powershell
docker compose @composeArgs exec -T agent_service python -c "from core.settings import settings as s; print({'generation_mode': s.COURSEPILOT_GENERATION_MODE, 'fallback_disabled': s.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK, 'knowledge_points_mode': s.COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE, 'embedding_provider': s.COURSEPILOT_EMBEDDING_PROVIDER, 'embedding_model': s.COURSEPILOT_EMBEDDING_MODEL, 'embedding_base_url': str(s.COURSEPILOT_EMBEDDING_BASE_URL), 'embedding_key_configured': bool(s.COURSEPILOT_EMBEDDING_API_KEY), 'fake_model': s.USE_FAKE_MODEL, 'default_model': str(s.DEFAULT_MODEL), 'async_worker': s.COURSEPILOT_ASYNC_WORKER_ENABLED})"
```

预期关键值为：`generation_mode=llm`、`fallback_disabled=True`、`knowledge_points_mode=llm`、`embedding_provider=openai-compatible`、`embedding_key_configured=True`、`fake_model=False` 和 `async_worker=True`。如果 API 启动失败，先看日志，不要启动评测：

```powershell
docker compose @composeArgs logs --tail=200 agent_service
```

#### 4. 首次启动真实评测

保持 Docker 服务在后台运行，在第二个 PowerShell 终端进入项目根目录并执行：

```powershell
$env:PYTHONPATH='src'
$env:COURSEPILOT_EVAL_ENV_FILE='.env.eval'
$env:COURSEPILOT_CHROMA_DIR='chroma_db_eval'

.\.venv\Scripts\python.exe -m coursepilot.evals.run_real_eval `
  --base-url http://localhost:8080 `
  --sample-dir data\coursepilot_sample `
  --chroma-dir chroma_db_eval `
  --build-kb-timeout 7200 `
  --generation-timeout 1800 `
  --checkpoint storage_eval\coursepilot_real_eval_checkpoint.json `
  --output storage_eval\coursepilot_real_eval_report.json
```

首次运行不要添加 `--resume`。checkpoint 在第一个 API 请求前就会创建；如果指定路径已经存在，脚本会拒绝覆盖，并提示恢复或开始新评测。

评测客户端为课程创建、知识库构建和各生成步骤发送由 checkpoint `run_id + step_id` 派生的稳定 `Idempotency-Key`。知识库构建和生成 POST 会快速返回 `202 + task_id`，客户端随后轮询 `/api/coursepilot/tasks/{task_id}`。

#### 5. 边测边查看进度

评测会在每个步骤开始、成功或失败时，原子更新以下两个文件：

- `storage_eval/coursepilot_real_eval_checkpoint.json`：恢复执行所需的完整步骤状态、上下文和稳定 `run_id`。
- `storage_eval/coursepilot_real_eval_report.json`：运行期间是带有 `partial: true` 的部分报告，完成后原子替换为最终报告。

Windows 上如果进度读取、IDE 或杀毒软件恰好短暂占用 JSON，原子替换会对 `PermissionError/WinError 5` 自动进行约 3 秒的短指数重试；持续占用超过重试窗口时仍会保留错误并安全退出。

因为文件使用原子替换，不建议用 `Get-Content -Wait`。可以在第三个 PowerShell 终端轮询 checkpoint：

```powershell
$checkpointPath = 'storage_eval\coursepilot_real_eval_checkpoint.json'
while ($true) {
  if (Test-Path $checkpointPath) {
    $checkpoint = Get-Content -Raw -Encoding utf8 $checkpointPath | ConvertFrom-Json
    [pscustomobject]@{
      run_id       = $checkpoint.run_id
      status       = $checkpoint.status
      current_step = $checkpoint.current_step
      updated_at   = $checkpoint.updated_at
    } | Format-List
    $checkpoint.steps.PSObject.Properties | ForEach-Object {
      [pscustomobject]@{
        step    = $_.Name
        status  = $_.Value.status
        attempt = $_.Value.attempt
      }
    } | Format-Table -AutoSize
  }
  Start-Sleep -Seconds 20
}
```

按 `Ctrl+C` 停止监视循环不会影响评测。另一个终端可持续查看 API/worker 日志：

```powershell
docker compose @composeArgs logs -f --tail=100 agent_service
```

需要核对服务端异步任务时，可以查询评测数据库。下面命令使用模板中的默认数据库用户名和库名；如果修改过 `POSTGRES_USER` 或 `POSTGRES_DB`，相应替换参数：

```powershell
docker compose @composeArgs exec -T postgres psql -U postgres -d coursepilot_eval -c "select id, task_type, status, attempt_count, updated_at, error_message from coursepilot_generation_tasks order by created_at desc limit 20;"
```

#### 6. 正常完成

正常结束时，checkpoint 的 `status` 为 `completed`，最终报告的 `run.status` 也为 `completed`。查看核心结果：

```powershell
$report = Get-Content -Raw -Encoding utf8 storage_eval\coursepilot_real_eval_report.json | ConvertFrom-Json
$report.run
$report.strict_fallback_passed
$report.retrieval.metrics
$report.generation.metrics
```

如果发现 fallback 使用记录，状态会是 `completed_with_fallback_violations`，且严格评测以非零退出码结束。真实评测默认设置 `COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK=true`；LLM 调用、结构化解析或 schema 校验失败时，任务应失败并计入报告，不应生成 deterministic 结果。

保留最终报告和对应 checkpoint。checkpoint 包含本次评测的运行身份和步骤证据，不要只保留报告。

#### 7. 客户端超时或评测终端意外中断

如果评测终端被关闭、按了 `Ctrl+C`、网络响应丢失，或者出现 `CoursePilot task timed out`：

1. 不要使用 `--overwrite-checkpoint`，也不要删除 checkpoint。
2. 如果 API 容器仍在运行，不要急于重启；服务端异步任务通常仍会继续执行。
3. 检查 checkpoint、API 日志和数据库任务状态。
4. 使用完全相同的样例目录、Chroma 目录、checkpoint 和 output 路径重新运行，并添加 `--resume`。

```powershell
$env:PYTHONPATH='src'
$env:COURSEPILOT_EVAL_ENV_FILE='.env.eval'
$env:COURSEPILOT_CHROMA_DIR='chroma_db_eval'

.\.venv\Scripts\python.exe -m coursepilot.evals.run_real_eval `
  --base-url http://localhost:8080 `
  --sample-dir data\coursepilot_sample `
  --chroma-dir chroma_db_eval `
  --build-kb-timeout 7200 `
  --generation-timeout 7200 `
  --checkpoint storage_eval\coursepilot_real_eval_checkpoint.json `
  --output storage_eval\coursepilot_real_eval_report.json `
  --resume
```

恢复时会跳过所有 `succeeded` 步骤。未成功步骤会再次执行，但相同 checkpoint 会生成相同幂等键：如果服务端任务仍在运行或已经成功，客户端会取得原来的 `task_id` 和结果并继续轮询，不会再次创建同一生成任务；明确标记为 `failed` 的任务会重新入队重试。

如果只是客户端等待时间不足，可以在恢复命令中增大 `--build-kb-timeout` 或 `--generation-timeout`。这两个参数不参与恢复 fingerprint，不需要 `--force-resume`，也不会终止或缩短服务端任务：

```powershell
# 例：最多等待知识库构建 4 小时、每个生成任务 1 小时
--build-kb-timeout 14400 `
--generation-timeout 3600 `
--resume
```

#### 8. Docker 或主机中断后的恢复

PostgreSQL 使用 `postgres_eval_data` 命名卷，上传/导出文件和 Chroma 使用宿主机目录，因此普通容器重启不会丢失评测数据。Docker Desktop 或主机恢复后执行：

```powershell
$composeArgs = @(
  '--env-file', '.env.eval',
  '-f', 'compose.yaml',
  '-f', 'compose.eval.yaml'
)
docker compose @composeArgs up -d --wait postgres
docker compose @composeArgs run --rm --no-deps agent_service python -m alembic upgrade head
docker compose @composeArgs up -d --wait agent_service streamlit_app
docker compose @composeArgs ps
```

worker 会重新领取 `pending` 任务；异常退出时遗留的 `running` 任务在租约到期后也会重新领取，默认租约为 300 秒。服务恢复健康后，再使用上一节的 `--resume` 命令恢复评测客户端。

客户端中断而服务端未中断时，稳定幂等键可避免重复生成。服务端如果恰好在一次 LLM 请求完成后、任务结果写入数据库前崩溃，租约恢复可能重新执行该任务，外部模型调用仍存在重复的可能；成本敏感时应结合 provider 用量记录核对。

#### 9. 配置修复、fingerprint 不一致和重新开始

如果只修改 API key、增加客户端轮询时限或修复网络，通常可以直接 `--resume`。修改以下内容会改变恢复 fingerprint：

- chat 模型名称；
- embedding provider、模型或 Base URL；
- 样例文件内容；
- `--sample-dir`、`--chroma-dir`、`--top-k`、`--skip-generation` 或 `--allow-fallback`。

chat Base URL 和 API key 当前不进入 fingerprint。API key 轮换后可以恢复；如果 Base URL 指向了不同 provider 或模型实现，即使脚本没有拒绝，也应开始新评测，避免混合结果。

配置变化后，默认应使用新的 checkpoint/output 文件开始一轮独立评测，避免把不同模型或数据的结果混在一起。只有明确接受混合结果时才使用：

```powershell
--resume --force-resume
```

`--force-resume` 会在 checkpoint 中写入警告。不要仅为绕过报错而使用。

已有 checkpoint 时，未指定 `--resume` 会拒绝启动。需要保留旧结果并开始新评测时，推荐使用带时间戳的新文件名：

```powershell
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss'
# 在首次运行命令中改用：
--checkpoint "storage_eval\coursepilot_real_eval_checkpoint_$runTag.json" `
--output "storage_eval\coursepilot_real_eval_report_$runTag.json"
```

确认不再需要旧恢复点和旧报告时，才在原首次运行命令末尾添加 `--overwrite-checkpoint`。该选项会创建新的 `run_id`，不会复用旧幂等键，可能重新产生全部 LLM 调用。

#### 10. 停止或彻底清理评测环境

评测完成后可以停止服务，数据仍会保留：

```powershell
docker compose @composeArgs stop
```

删除容器和网络但保留 PostgreSQL 命名卷、报告和 Chroma 数据：

```powershell
docker compose @composeArgs down
```

不要在服务端任务为 `pending` 或 `running` 时停止服务，除非准备之后按租约恢复。需要彻底清理时，先停止容器并确认评测卷名称：

```powershell
docker compose @composeArgs down
docker volume ls --filter label=com.docker.compose.volume=postgres_eval_data
```

默认项目目录名为 `agent_coursepilot` 时，评测卷名通常是 `agent_coursepilot_postgres_eval_data`。确认列表中的名称确实属于本项目后，才执行以下删除命令。不要删除 `agent_coursepilot_postgres_data`，它是默认 demo 数据卷：

```powershell
docker volume rm agent_coursepilot_postgres_eval_data
Remove-Item -Recurse -Force storage_eval
Remove-Item -Recurse -Force chroma_db_eval
```

上述命令会永久删除独立评测数据库、checkpoint、报告、上传文件和向量库，仅在确认不需要任何评测数据时使用。如果 Compose project name 不是 `agent_coursepilot`，应使用上一条 `docker volume ls` 实际显示的评测卷名。

#### 常见错误判断

- `500 Internal Server Error`：先检查 `agent_service` 日志、PostgreSQL 健康状态和 Alembic 迁移版本，不要直接重跑整个评测。
- `CoursePilot task timed out`：这是客户端轮询上限，不代表服务端失败；先查任务状态，再用更长时限和 `--resume`。
- `400 ... validation failed`：这是生成结果校验失败，不是请求时限太短；检查任务的 `validation_report_json` 和模型输出。
- `checkpoint already exists`：继续原评测使用 `--resume`；新评测使用新文件名；只有放弃旧恢复点时才使用 `--overwrite-checkpoint`。
- `fingerprint does not match`：检查模型、endpoint、样例和目录是否变化；通常应开始新评测，不要默认使用 `--force-resume`。
- embedding Provider 返回认证、限流或模型错误：修复 `.env.eval`，执行 `docker compose @composeArgs up -d --force-recreate --wait agent_service` 重新加载环境变量，确认健康后再 `--resume`。

真实 LLM integration test 默认跳过。只有配置好兼容模型 endpoint 和 API key 后，才建议显式开启；它与上述完整真实评测不是同一个命令。

## 文档资料

更详细的产品和工程文档位于 `CoursePilot_markdown_docs/`：

- PRD 与 MVP 验收标准
- 技术架构设计
- 开发计划
- 阶段审计记录
- LLM 工程化、trace、fallback 和 usage 统计说明

README 是项目入口文档；更细的设计依据和阶段记录以该目录为准。

## 目录结构

```text
src/coursepilot/          产品 API、services、schemas、models、RAG、validators、exporters
src/agents/coursepilot/   LangGraph 教学设计、试卷、PPT 工作流
src/service/              FastAPI 应用、鉴权、prompt-entry endpoints
src/client/               CoursePilot 产品 client 和最小 Agent client
src/memory/               LangGraph checkpoint/store persistence
alembic/                  CoursePilot PostgreSQL migrations
data/coursepilot_sample/  样例课程资料
tests/coursepilot/        CoursePilot 产品和工作流测试
CoursePilot_markdown_docs/ PRD、架构、阶段审计和实现说明
```

## License

本项目使用 MIT License，详见 `LICENSE`。
