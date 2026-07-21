# CoursePilot Phase 0 审核说明 v0.1

本文档用于解释 Phase 0 做了什么、为什么这样做、对应文件在哪里，以及你应该如何运行命令来验收。

对照文件：

- `PLAN.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

## 1. Phase 0 的目标

Phase 0 的目标是“项目初始化与底座保护”。

换成新手更容易理解的话，就是先不急着实现课程、上传、RAG、教案这些业务功能，而是先完成这些基础工作：

1. 保留原 Agent Service Toolkit 的 FastAPI、Agent Registry、Streamlit、Docker、测试结构。
2. 新建 CoursePilot 专属目录，避免业务代码和原框架代码混在一起。
3. 增加 CoursePilot 需要的配置项，例如文件存储目录、Chroma 目录、repair 次数、重复度阈值。
4. 增加数据库迁移基础，后续课程表、文档表、chunk 表都可以通过 Alembic 管理。
5. 增加运行时目录和 Docker volume，避免上传文件、向量库数据因为容器重启而丢失。

PRD 和技术架构文档都强调 CoursePilot 是基于 Agent Service Toolkit 改造，而不是从零重写。因此 Phase 0 的核心判断标准是：原系统仍能启动，CoursePilot 有清晰隔离边界，后续业务模块有地方放。

## 2. 新增了哪些文件

### 2.1 CoursePilot 业务包骨架

新增目录：

```text
src/coursepilot/
  api/
  db/
  models/
  schemas/
  services/
  rag/
    parsers/
  validators/
  exporters/
  evals/
  ui/
  utils/
  prompts/
    lesson/
    exam/
    ppt/
    repair/
```

动机：

- `api/`：后续放 `/api/coursepilot/*` 业务接口。
- `db/`：放 SQLAlchemy Base、session、数据库连接。
- `models/`：放数据库 ORM 模型。
- `schemas/`：放 Pydantic 输入输出结构。
- `services/`：放业务逻辑，例如课程管理、文档处理、知识库构建。
- `rag/`：放解析、chunk、embedding、Chroma 检索。
- `validators/`：放教案、试题等结果校验器。
- `exporters/`：放 docx/pptx 导出器。
- `ui/`：放 CoursePilot Streamlit 页面。
- `evals/`：后续放评估脚本。
- `prompts/`：后续集中管理提示词，避免 prompt 散落在代码里。

对应验收：

```powershell
Test-Path src\coursepilot\api
Test-Path src\coursepilot\db
Test-Path src\coursepilot\rag\parsers
Test-Path src\coursepilot\prompts\lesson
```

这些命令都应该输出 `True`。

### 2.2 CoursePilot Agent workflow 骨架

新增目录：

```text
src/agents/coursepilot/
  graphs/
  nodes/
  states/
```

动机：

- `graphs/`：放完整 LangGraph workflow，例如 lesson graph、exam graph。
- `nodes/`：放 graph 中的单个节点，例如 retrieve、validate、repair。
- `states/`：放 graph 状态结构。

这样做符合技术架构文档中的分层：`src/coursepilot/` 放业务模块，`src/agents/coursepilot/` 放 Agent 编排。

### 2.3 数据库基础文件

新增：

- `src/coursepilot/db/base.py`
- `src/coursepilot/db/session.py`
- `alembic.ini`
- `alembic/env.py`
- `alembic/versions/2026_06_20_0001-initial_coursepilot_base.py`

动机：

CoursePilot 需要课程、文档、chunk、生成任务、教案、导出文件等业务表。技术架构文档决定使用：

```text
Postgres + SQLAlchemy + Alembic
```

其中：

- `base.py` 定义所有 CoursePilot ORM model 的共同父类。
- `session.py` 负责创建数据库连接和 FastAPI session dependency。
- `alembic.ini` 是 Alembic 配置入口。
- `alembic/env.py` 告诉 Alembic 如何找到 `src/coursepilot` 和 SQLAlchemy metadata。
- `0001_initial_coursepilot_base.py` 是空基线迁移，证明迁移系统已经跑通，但 Phase 0 还不创建业务表。

注意：

- `0001_initial_coursepilot_base.py` 属于 Phase 0。
- `0002_create_phase1_tables.py` 属于 Phase 1，因为它创建课程、文档、chunk 表。
- `0003_create_lesson_tables.py` 属于 Phase 2，因为它创建教案、生成任务、导出文件表。

## 3. 修改了哪些文件

### 3.1 `pyproject.toml`

修改内容：

- 项目名改为 `coursepilot`。
- 项目描述改为 CoursePilot teacher assistant agent system。
- 增加依赖：
  - `sqlalchemy`
  - `alembic`
  - `python-docx`
  - `python-pptx`
  - `pymupdf`
  - `docx2txt`
  - `openpyxl`
  - `pandas`

动机：

- `sqlalchemy` 和 `alembic` 用于业务数据库和迁移。
- `python-docx` 用于生成 Word 教案、试卷。
- `python-pptx` 用于生成 PPT。
- `pymupdf`、`docx2txt`、`openpyxl`、`pandas` 为后续解析 PDF、DOCX、XLSX 做准备。

### 3.2 `src/core/settings.py`

新增配置：

```python
COURSEPILOT_DATABASE_URL: str | None = None
COURSEPILOT_STORAGE_DIR: str = "./storage"
COURSEPILOT_CHROMA_DIR: str = "./chroma_db"
COURSEPILOT_MAX_REPAIR_ROUNDS: int = 2
COURSEPILOT_DUPLICATE_THRESHOLD: float = 0.85
COURSEPILOT_ENABLED: bool = True
```

动机：

- `COURSEPILOT_DATABASE_URL`：允许 CoursePilot 使用单独数据库 URL。
- `COURSEPILOT_STORAGE_DIR`：上传文件和导出文件的本地目录。
- `COURSEPILOT_CHROMA_DIR`：Chroma 向量库持久化目录。
- `COURSEPILOT_MAX_REPAIR_ROUNDS`：LLM 输出 JSON 失败时最多修复 2 轮。
- `COURSEPILOT_DUPLICATE_THRESHOLD`：试题重复度默认阈值 0.85。
- `COURSEPILOT_ENABLED`：给后续开关 CoursePilot 功能留入口。

### 3.3 `.env.example`

新增 CoursePilot 环境变量示例：

```text
COURSEPILOT_DATABASE_URL=
COURSEPILOT_STORAGE_DIR=./storage
COURSEPILOT_CHROMA_DIR=./chroma_db
COURSEPILOT_MAX_REPAIR_ROUNDS=2
COURSEPILOT_DUPLICATE_THRESHOLD=0.85
COURSEPILOT_ENABLED=true
```

动机：

新用户复制 `.env.example` 到 `.env` 后，就能知道 CoursePilot 有哪些配置项，而不需要读代码猜。

### 3.4 `compose.yaml`

新增或修改：

```yaml
volumes:
  - ./storage:/app/storage
  - ./chroma_db:/app/chroma_db
```

以及 watch：

```yaml
- path: src/coursepilot/
  action: sync+restart
  target: /app/coursepilot/
```

动机：

- `storage` 保存上传文件和导出文件。
- `chroma_db` 保存本地向量库。
- Docker watch 监听 `src/coursepilot/`，开发时修改 CoursePilot 代码后容器能自动同步。

### 3.5 `.gitignore`

新增：

```text
chroma_db/*
!chroma_db/.gitkeep

storage/*
!storage/.gitkeep
```

动机：

- 真实运行数据不应该提交到 git。
- `.gitkeep` 保留空目录，方便新用户 clone 后目录仍存在。

### 3.6 `README.md`

修改为 CoursePilot 项目说明，同时保留 Agent Service Toolkit 来源说明。

动机：

Development Plan 的 T0-001 要求 README 说明项目基于 Agent Service Toolkit 改造，而不是完全原创工程。

## 4. 关键新增代码解释

### 4.1 `src/coursepilot/db/base.py`

核心代码：

```python
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

class Base(DeclarativeBase):
    """Base class for CoursePilot business tables."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
```

逐行理解：

- `NAMING_CONVENTION`：给数据库约束统一命名，例如主键叫 `pk_coursepilot_courses`。
- 统一命名的好处是 Alembic 生成迁移时结果稳定，不会每台机器生成不同名字。
- `Base`：后续所有 CoursePilot ORM model 都继承它。
- `Base.metadata`：Alembic 会读取这里注册过的表，然后知道哪些表需要迁移。

### 4.2 `src/coursepilot/db/session.py`

核心代码：

```python
def _build_postgres_url() -> str:
    if settings.COURSEPILOT_DATABASE_URL:
        return settings.COURSEPILOT_DATABASE_URL
```

含义：

如果你在 `.env` 里显式配置了 `COURSEPILOT_DATABASE_URL`，CoursePilot 就优先使用这个 URL。这样它可以和原 AST 使用不同数据库。

```python
required = {
    "POSTGRES_USER": settings.POSTGRES_USER,
    "POSTGRES_PASSWORD": settings.POSTGRES_PASSWORD,
    "POSTGRES_HOST": settings.POSTGRES_HOST,
    "POSTGRES_PORT": settings.POSTGRES_PORT,
    "POSTGRES_DB": settings.POSTGRES_DB,
}
missing = [key for key, value in required.items() if not value]
```

含义：

如果没有独立的 `COURSEPILOT_DATABASE_URL`，就复用原项目的 `POSTGRES_*` 配置。这里先检查配置是否齐全，避免数据库连接时报难懂的底层错误。

```python
@lru_cache
def get_coursepilot_engine() -> Engine:
    return create_engine(_build_postgres_url(), pool_pre_ping=True)
```

含义：

- SQLAlchemy `Engine` 可以理解为数据库连接工厂。
- `@lru_cache` 让它在进程里只创建一次。
- `pool_pre_ping=True` 会检查连接是否可用，减少数据库空闲断连导致的问题。

```python
def get_session() -> Generator[Session, None, None]:
    with CoursePilotSessionLocal(bind=get_coursepilot_engine()) as session:
        yield session
```

含义：

这是给 FastAPI 路由用的 dependency。每次请求拿到一个数据库 session，请求结束后自动关闭。

### 4.3 `alembic/env.py`

核心代码：

```python
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
```

含义：

Alembic 命令不是从 `src` 包内部启动的，所以默认找不到 `coursepilot` 包。这里手动把 `src` 加到 Python import 路径。

```python
import coursepilot.models
from coursepilot.db.base import Base

target_metadata = Base.metadata
```

含义：

- `import coursepilot.models` 会触发 ORM model 注册。
- `target_metadata = Base.metadata` 告诉 Alembic：迁移时请以 CoursePilot 的 metadata 为准。

```python
config.set_main_option("sqlalchemy.url", _build_postgres_url())
```

含义：

迁移命令会复用 `session.py` 里的数据库 URL 生成逻辑，避免 Alembic 和应用代码各写一套数据库配置。

## 5. 哪些东西不是 Phase 0

当前仓库已经有 Phase 1-3 的文件，所以审核时要注意边界。

以下内容不应算作 Phase 0 的业务成果：

- `src/coursepilot/api/routes_courses.py`
- `src/coursepilot/api/routes_documents.py`
- `src/coursepilot/api/routes_kb.py`
- `src/coursepilot/rag/chunker.py`
- `src/coursepilot/rag/vector_store.py`
- `src/coursepilot/rag/retriever.py`
- `src/coursepilot/schemas/course_schema.py`
- `src/coursepilot/schemas/document_schema.py`
- `src/coursepilot/schemas/lesson_schema.py`
- `src/coursepilot/exporters/lesson_docx_exporter.py`
- `src/agents/coursepilot/graphs/lesson_graph.py`
- `alembic/versions/2026_06_21_0002-create_phase1_tables.py`
- `alembic/versions/2026_06_22_0003-create_lesson_tables.py`

这些是后续阶段的实现。Phase 0 只负责为它们准备目录、配置、依赖、迁移入口。

## 6. 如何验收 Phase 0

### 6.1 检查目录是否存在

```powershell
Test-Path src\coursepilot
Test-Path src\coursepilot\db
Test-Path src\coursepilot\rag\parsers
Test-Path src\agents\coursepilot\graphs
Test-Path storage\.gitkeep
Test-Path chroma_db\.gitkeep
```

期望结果：全部输出 `True`。

### 6.2 检查 CoursePilot 配置能被读取

因为原项目导入 `core.settings` 时要求至少有一个 LLM key，所以本地检查时要临时给一个测试 key：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -c "from core.settings import Settings; s=Settings(OPENAI_API_KEY='test-key', _env_file=None); print(s.COURSEPILOT_STORAGE_DIR, s.COURSEPILOT_CHROMA_DIR, s.COURSEPILOT_MAX_REPAIR_ROUNDS, s.COURSEPILOT_DUPLICATE_THRESHOLD, s.COURSEPILOT_ENABLED)"
```

期望输出：

```text
./storage ./chroma_db 2 0.85 True
```

### 6.3 跑 Phase 0 测试

如果当前虚拟环境还没有 pytest，先安装：

```powershell
.\.venv\Scripts\python.exe -m pip install pytest pytest-asyncio pytest-env
```

然后运行：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_phase0_setup.py -q
```

期望结果：

```text
5 passed
```

### 6.4 检查原 AST 底座没有被破坏

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\service\test_service.py tests\agents\test_agent_loading.py -q
```

期望结果：测试通过。

### 6.5 启动服务并检查接口

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe src\run_service.py
```

打开浏览器或用 PowerShell 访问：

```powershell
Invoke-RestMethod http://localhost:8080/health
Invoke-RestMethod http://localhost:8080/info
```

期望：

- `/health` 返回健康状态。
- `/info` 能返回 agent 列表和模型信息。

### 6.6 验证 Alembic 空基线迁移

先启动 Postgres：

```powershell
docker compose up -d postgres
```

设置本地数据库环境变量：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
$env:POSTGRES_USER='postgres'
$env:POSTGRES_PASSWORD='postgres'
$env:POSTGRES_HOST='localhost'
$env:POSTGRES_PORT='5432'
$env:POSTGRES_DB='agent_service'
```

执行 Phase 0 空迁移：

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade 0001_initial_coursepilot_base
```

期望：

- 命令成功执行。
- 数据库里记录 Alembic 版本为 `0001_initial_coursepilot_base`。
- 因为这是 Phase 0 空迁移，所以不会创建课程、文档、chunk 等业务表。

## 7. 当前我实际验证到的状态

我先遇到过一次环境问题：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_phase0_setup.py tests\service\test_service.py tests\agents\test_agent_loading.py -q
```

当时失败原因是当前 `.venv` 没有安装 `pytest`，不是测试断言失败。随后我执行了：

```powershell
.\.venv\Scripts\python.exe -m pip install pytest pytest-asyncio pytest-env
```

然后重新验证。

我也检查过 `uv --version`，当前系统 PATH 中没有 `uv`，所以本文档里的验收命令都优先使用 `.venv\Scripts\python.exe`。

我完成了一个轻量导入检查：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -c "from core.settings import Settings; from coursepilot.db.base import Base; s=Settings(OPENAI_API_KEY='test-key', _env_file=None); print(s.COURSEPILOT_STORAGE_DIR, s.COURSEPILOT_CHROMA_DIR, s.COURSEPILOT_MAX_REPAIR_ROUNDS, s.COURSEPILOT_DUPLICATE_THRESHOLD, s.COURSEPILOT_ENABLED); print(Base.metadata.naming_convention['pk'])"
```

实际输出：

```text
./storage ./chroma_db 2 0.85 True
pk_%(table_name)s
```

这证明：

- CoursePilot 配置默认值可以读取。
- CoursePilot SQLAlchemy Base 可以导入。
- 命名约定生效。

Phase 0 专项测试已经通过：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_phase0_setup.py -q
```

实际结果：

```text
5 passed, 8 warnings
```

原 AST 底座回归测试也已经通过：

```powershell
$env:PYTHONPATH='src'
$env:OPENAI_API_KEY='sk-test'
.\.venv\Scripts\python.exe -m pytest tests\service\test_service.py tests\agents\test_agent_loading.py -q
```

实际结果：

```text
19 passed, 9 warnings
```

这些 warnings 来自 LangGraph/SWIG 的弃用或导入提示，不是 Phase 0 断言失败。

## 8. Phase 0 验收清单

你可以按下面清单逐项确认：

- `src/coursepilot/` 存在，且包含业务子目录。
- `src/agents/coursepilot/` 存在，且包含 `graphs`、`nodes`、`states`。
- `src/core/settings.py` 中有 `COURSEPILOT_*` 配置。
- `.env.example` 中有同样的 `COURSEPILOT_*` 示例。
- `src/coursepilot/db/base.py` 能导入。
- `src/coursepilot/db/session.py` 能构造数据库 URL。
- `alembic.ini` 和 `alembic/env.py` 存在。
- `0001_initial_coursepilot_base.py` 是空基线迁移。
- `compose.yaml` 挂载了 `storage` 和 `chroma_db`。
- `.gitignore` 忽略了 `storage/*` 和 `chroma_db/*`，但保留 `.gitkeep`。
- 原 `/info`、`/health` 仍然可访问。

如果这些都满足，Phase 0 就达到了“底座保护和初始化”的验收标准。
