# CoursePilot LLM 工程化改造说明 v0.1

本文档解释本次 CoursePilot LLM 工程化改造做了什么、为什么这样做、涉及哪些新增/修改文件，以及如何运行命令检查修改效果。

参考文件：

- `待改进.md` 中关于 RAG + LLM + LangGraph workflow 的工程化改造要求
- `CoursePilot_markdown_docs/CoursePilot_PRD_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Development_Plan_v0.2.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`
- `CoursePilot_markdown_docs/phase_audit/CoursePilot_Phase0_Audit_v0.1.md`

## 1. 本次改造的核心目标

MVP 阶段的 CoursePilot 已经具备课程、资料、知识库、教学设计、试题、PPT、审核写回等基础闭环，但关键生成逻辑仍偏“规则化 MVP”：service 层直接拼出教学设计、试题、PPT 大纲，LLM 与 prompt 没有成为稳定的工程边界。

本次改造把它升级成更接近真实可部署 Agent 的形态：

```text
课程资料入库
  -> 文档解析与 chunk
  -> embedding 写入 Chroma
  -> RAG 检索课程私有知识库
  -> LangGraph 编排任务
  -> LLM 生成结构化 JSON
  -> Pydantic schema 校验
  -> repair prompt 或 deterministic fallback 修复
  -> service 持久化 graph 输出
  -> exporter 渲染 DOCX/PPTX
  -> 教师审核
  -> verified 内容写回知识库
```

这对应 PRD 的三个重点：

- PRD 7 产品总体流程：从资料上传、知识库构建、Agent 生成、人工审核到知识库更新。
- PRD 9 核心功能需求：资料入库、教学设计、PPT、试卷、审核写回。
- PRD 12 Agent Workflow：教学设计、PPT、试卷都由 workflow 节点完成，而不是 service 层直接拼结果。

## 2. 总体架构变化

### 2.1 改造前

改造前的关键路径大致是：

```text
API route
  -> LessonService / ExamService / PPTService
  -> service 内部私有 builder 拼 deterministic JSON
  -> validator 校验
  -> 数据库保存
```

问题是：

- 生成逻辑和业务事务混在一起，service 既负责数据库事务，又负责“像 LLM 一样生成内容”。
- prompt 不集中，后续接真实模型时不好维护。
- RAG 检索、知识点抽取、生成、校验、repair 没有形成清晰 workflow。
- 测试虽然稳定，但生产路径不是真实 LLM Agent。

### 2.2 改造后

改造后的关键路径变为：

```text
API route
  -> Service 创建任务/处理事务
  -> 调用 CoursePilot LangGraph agent
  -> Graph 节点执行 retrieve / generate / validate / repair / export
  -> Service 持久化 graph 输出
  -> API 返回结构化结果
```

service 层现在主要做：

- 参数接收与业务对象查询；
- 创建 `GenerationTask`；
- 调用对应 graph；
- 把 graph 输出转换为 Pydantic schema；
- 写入数据库；
- 捕获错误并更新任务状态。

graph 层现在主要做：

- RAG 检索；
- 知识点抽取；
- LLM 结构化生成；
- schema/数量/引用/重复度校验；
- repair 重试；
- PPTX 构建等 workflow 内部动作。

## 3. 新增文件清单

### 3.1 LLM 与 prompt 基础设施

新增：

```text
src/coursepilot/llm.py
src/coursepilot/prompts/loader.py
```

动机：

- `llm.py` 是 CoursePilot 专属 LLM 调用入口，避免业务代码到处直接 new `ChatOpenAI`。
- `loader.py` 统一从 `src/coursepilot/prompts` 读取 prompt，避免 prompt 散落在 Python 字符串里。
- 所有 LLM 输出都尽量经过 Pydantic schema 约束，便于 validator、repair、数据库持久化统一处理。

### 3.2 新增 prompt 文件

新增：

```text
src/coursepilot/prompts/rag/extract_knowledge_points.md
src/coursepilot/prompts/lesson/extract_knowledge_points.md
src/coursepilot/prompts/lesson/plan_sessions.md
src/coursepilot/prompts/lesson/generate_lesson_design.md
src/coursepilot/prompts/lesson/revise_lesson_design.md
src/coursepilot/prompts/repair/fix_json.md
```

同时修改：

```text
src/coursepilot/prompts/exam/plan_exam_blueprint.md
src/coursepilot/prompts/ppt/generate_slide_outline.md
```

动机：

- RAG 阶段需要从 chunk 中抽知识点。
- lesson workflow 需要分成知识点抽取、课时规划、教案生成、局部修订。
- repair 阶段需要专门 prompt 修复结构化 JSON，而不是简单重新生成。
- exam/ppt prompt 需要明确输出结构和引用要求。

### 3.3 新增 RAG 知识点抽取器

新增：

```text
src/coursepilot/rag/knowledge_points.py
```

动机：

- 原先 chunk 里的知识点更像正则关键词。
- 现在提供 `KnowledgePointExtractor`：生产环境优先 LLM 抽取，未配置模型或测试环境自动走 deterministic fallback。

### 3.4 新增 CoursePilot API client

新增：

```text
src/client/coursepilot_client.py
```

动机：

- Streamlit 页面之前散落了很多 `httpx` 请求。
- 新增 `CoursePilotClient` 后，UI 只调用业务方法，例如 `create_course()`、`generate_lesson()`、`write_back_review()`。
- 这样 API 路径集中管理，后续调整超时、鉴权、错误处理时不需要改 UI 多处代码。

### 3.5 新增测试

新增：

```text
tests/coursepilot/test_llm_infra.py
tests/client/test_coursepilot_client.py
```

动机：

- 验证 prompt loader 能读取 prompt。
- 验证 embedding 工厂默认 fallback 为本地 hashing。
- 验证 OpenAI-compatible embedding 参数可以正确传入。
- 验证 `CoursePilotClient` 封装的 REST 路径、上传文件和异常处理。

## 4. 修改文件清单

### 4.1 配置与部署相关

修改：

```text
.env.example
README.md
README.zh-CN.md
src/core/settings.py
src/core/llm.py
```

主要变化：

- 新增 CoursePilot generation/embedding 配置。
- README 增加真实模型、embedding、Docker、fallback 说明。
- `FakeToolModel.bind_tools()` 支持 `**kwargs`，兼容 LangChain 的 structured output/tool choice 调用。

### 4.2 RAG 与 embedding 相关

修改：

```text
src/coursepilot/rag/chunker.py
src/coursepilot/rag/embeddings.py
src/coursepilot/rag/vector_store.py
src/coursepilot/validators/duplicate_detector.py
src/coursepilot/services/document_service.py
```

主要变化：

- embedding 从硬编码 hashing 改为工厂。
- Chroma 和重复度检测支持 embedding 注入。
- chunk 知识点抽取走 `KnowledgePointExtractor`。
- `.doc` 上传在入口明确拒绝，提示转换成 `.docx`。

### 4.3 Agent workflow 相关

修改：

```text
src/agents/coursepilot/graphs/lesson_graph.py
src/agents/coursepilot/graphs/exam_graph.py
src/agents/coursepilot/graphs/ppt_graph.py
src/agents/coursepilot/nodes/retrieve_nodes.py
src/agents/coursepilot/nodes/lesson_nodes.py
src/agents/coursepilot/nodes/exam_nodes.py
src/agents/coursepilot/nodes/ppt_nodes.py
src/agents/coursepilot/nodes/repair_nodes.py
src/agents/coursepilot/nodes/validation_nodes.py
src/agents/coursepilot/states/lesson_state.py
src/agents/coursepilot/states/exam_state.py
src/agents/coursepilot/states/ppt_state.py
```

主要变化：

- lesson graph 真正执行 retrieve -> extract -> plan -> generate -> validate -> repair。
- exam graph 拆成 blueprint 和 questions 两个阶段。
- ppt graph 增加 build_pptx 和 save_export_file 节点。
- repair 次数统一受 `COURSEPILOT_MAX_REPAIR_ROUNDS` 控制。
- state 增加 `course_id`、`workflow_phase`、`blueprint_id`、`pptx_output_path` 等运行字段。

### 4.4 Service/API/UI 相关

修改：

```text
src/coursepilot/services/lesson_service.py
src/coursepilot/services/exam_service.py
src/coursepilot/services/ppt_service.py
src/coursepilot/services/review_service.py
src/coursepilot/api/routes_exams.py
src/coursepilot/ui/knowledge_base_page.py
src/client/__init__.py
```

主要变化：

- lesson/exam/ppt service 改成调用 graph，不再直接拼规则化结果。
- 试卷题目生成前强制要求 blueprint confirmed。
- blueprint 未 confirmed 时 API 返回 409。
- review write-back 支持 `ppt_outline`、`lesson_design`、`question`。
- Streamlit 页面改用 `CoursePilotClient`。

### 4.5 测试相关

修改/新增：

```text
tests/coursepilot/test_exam_api.py
tests/coursepilot/test_phase0_setup.py
tests/coursepilot/test_retriever.py
tests/coursepilot/test_write_back.py
tests/coursepilot/test_llm_infra.py
tests/client/test_coursepilot_client.py
tests/app/test_streamlit_app.py
```

主要变化：

- 验证 unconfirmed blueprint 生成试题返回 409。
- 验证新配置字段存在。
- 验证 `.doc` 上传明确失败。
- 验证审核写回后可通过 `verified_only=true` 检索。
- 验证 UI 通过 client 层访问 CoursePilot API。

## 5. 配置层改造说明

### 5.1 `src/core/settings.py`

新增配置：

```python
# CoursePilot 独立数据库 URL；不配置时复用原 POSTGRES_*。
COURSEPILOT_DATABASE_URL: str | None = None

# 上传文件、导出 DOCX/PPTX 的本地目录。
COURSEPILOT_STORAGE_DIR: str = "./storage"

# Chroma 向量库持久化目录。
COURSEPILOT_CHROMA_DIR: str = "./chroma_db"

# LLM 输出未通过校验时最多 repair 几轮。
COURSEPILOT_MAX_REPAIR_ROUNDS: int = 2

# 题目重复度检测阈值。
COURSEPILOT_DUPLICATE_THRESHOLD: float = 0.85

# CoursePilot 功能开关。
COURSEPILOT_ENABLED: bool = True

# auto：有真实模型配置就用 LLM，否则 fallback；
# llm：强制使用 LLM，没有配置则报错；
# deterministic：强制使用本地 deterministic 逻辑，适合测试/CI。
COURSEPILOT_GENERATION_MODE: str = "auto"

# auto：有 embedding 配置就用 OpenAI-compatible，否则 hashing；
# openai-compatible：强制真实 embedding；
# hashing：强制本地 hashing embedding。
COURSEPILOT_EMBEDDING_PROVIDER: str = "auto"
COURSEPILOT_EMBEDDING_MODEL: str | None = None
COURSEPILOT_EMBEDDING_BASE_URL: str | None = None
COURSEPILOT_EMBEDDING_API_KEY: SecretStr | None = None
```

动机：

- 生产环境可以接 Qwen、DeepSeek 兼容接口或自建 OpenAI-compatible 网关。
- 默认 `auto` 不破坏本地测试：没有 key 时仍能跑 deterministic/hash fallback。
- LLM 与 embedding 分开配置，因为有些环境会使用不同模型或不同服务网关。

### 5.2 `.env.example`

新增示例：

```text
COURSEPILOT_GENERATION_MODE=auto
COURSEPILOT_EMBEDDING_PROVIDER=auto
COURSEPILOT_EMBEDDING_MODEL=
COURSEPILOT_EMBEDDING_BASE_URL=
COURSEPILOT_EMBEDDING_API_KEY=
```

使用方式：

```powershell
Copy-Item .env.example .env
```

如果只想跑本地测试，不需要配置真实 key。

如果要接真实模型，至少需要配置：

```text
MODEL=openai-compatible
COMPATIBLE_MODEL=你的聊天模型名
COMPATIBLE_BASE_URL=https://你的兼容接口/v1
COMPATIBLE_API_KEY=你的 API key

COURSEPILOT_GENERATION_MODE=llm
COURSEPILOT_EMBEDDING_PROVIDER=openai-compatible
COURSEPILOT_EMBEDDING_MODEL=你的 embedding 模型名
COURSEPILOT_EMBEDDING_BASE_URL=https://你的兼容接口/v1
COURSEPILOT_EMBEDDING_API_KEY=你的 API key
```

## 6. LLM 与 prompt 层说明

### 6.1 `src/coursepilot/llm.py`

这个文件是 CoursePilot 调用 LLM 的统一入口。

关键代码注释式理解：

```python
def use_coursepilot_llm() -> bool:
    # 读取配置：auto / llm / deterministic。
    mode = settings.COURSEPILOT_GENERATION_MODE.lower()

    # deterministic 表示强制不外呼模型。
    # 用于 CI、本地无 key 测试、可重复回归。
    if mode == "deterministic":
        return False

    # llm 表示强制真实模型。
    # 如果没配置 COMPATIBLE_*，这里会直接报错，让部署问题尽早暴露。
    if mode == "llm":
        _require_compatible_llm_config()
        return True

    # auto 表示有真实配置就用 LLM，没有就 fallback。
    return _has_compatible_llm_config()
```

```python
@cache
def get_coursepilot_llm() -> ChatOpenAI:
    # 只创建一次 ChatOpenAI 实例，避免每个节点重复初始化客户端。
    _require_compatible_llm_config()

    # 使用 OpenAI-compatible 参数；
    # 可以接 OpenAI、Qwen、DeepSeek 兼容接口或自建网关。
    return ChatOpenAI(
        model=settings.COMPATIBLE_MODEL,
        temperature=0.2,
        streaming=False,
        base_url=settings.COMPATIBLE_BASE_URL,
        api_key=settings.COMPATIBLE_API_KEY.get_secret_value(),
    )
```

```python
def generate_structured(...):
    # 如果当前环境不使用 LLM，直接执行 fallback。
    # 这是测试稳定性的关键：CI 不依赖外部模型。
    if not use_coursepilot_llm():
        return fallback()

    # 从 prompts 目录加载 prompt。
    prompt = load_prompt(prompt_name)

    # 把业务输入和目标 schema 一起发给模型。
    # schema 来自 Pydantic，能明确告诉模型必须返回什么结构。
    human_payload = {
        "input": payload,
        "schema": output_schema.model_json_schema(),
    }

    # LangChain 的 with_structured_output 会把模型输出约束到 Pydantic schema。
    runnable = get_coursepilot_llm().with_structured_output(output_schema)

    # 最终统一返回 Pydantic 对象。
    result = runnable.invoke([...])
    return output_schema.model_validate(result)
```

为什么这样做：

- 调用模型的代码集中在一个文件，便于后续更换 provider。
- 每个节点只需要声明 prompt、schema、payload、fallback。
- 测试路径和生产路径共用同一套函数，只是配置不同。

### 6.2 `src/coursepilot/prompts/loader.py`

关键代码注释式理解：

```python
PROMPT_ROOT = Path(__file__).resolve().parent

@cache
def load_prompt(name: str) -> str:
    # 支持传入 lesson/generate_lesson_design 或 lesson/generate_lesson_design.md。
    normalized = name.removesuffix(".md")

    # 所有 prompt 都必须在 PROMPT_ROOT 下，防止路径穿越。
    path = (PROMPT_ROOT / f"{normalized}.md").resolve()
    if PROMPT_ROOT not in path.parents:
        raise ValueError(...)

    # prompt 不存在时尽早失败，避免运行到 LLM 调用才发现。
    if not path.exists():
        raise FileNotFoundError(...)

    # prompt 文件统一用 UTF-8，支持中文教学场景。
    return path.read_text(encoding="utf-8").strip()
```

为什么这样做：

- prompt 有版本化文件，便于 review 和调参。
- loader 带 cache，重复调用不会反复读磁盘。
- 路径限制保证不会误读 prompts 目录之外的文件。

### 6.3 `src/core/llm.py`

修改：

```python
class FakeToolModel(FakeListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self
```

动机：

- LangChain 的 structured output/tool 调用可能传入 `tool_choice` 等额外参数。
- 原 fake model 如果只接受 `tools`，测试替身会因为签名不兼容失败。
- 加 `**kwargs` 后，不影响真实模型，同时让测试替身兼容更多 LangChain 调用方式。

## 7. RAG 与 embedding 改造说明

### 7.1 `src/coursepilot/rag/embeddings.py`

核心变化是新增 `get_coursepilot_embeddings()`。

关键代码注释式理解：

```python
def get_coursepilot_embeddings() -> Embeddings:
    provider = settings.COURSEPILOT_EMBEDDING_PROVIDER.lower()

    # 明确指定 hashing 时，使用本地 deterministic embedding。
    # 它不适合生产质量，但适合测试和离线 demo。
    if provider == "hashing":
        return HashingEmbeddings()

    # embedding 可以使用 CoursePilot 专属配置；
    # 如果没配置专属项，也可以复用 COMPATIBLE_*。
    base_url = settings.COURSEPILOT_EMBEDDING_BASE_URL or settings.COMPATIBLE_BASE_URL
    api_key = settings.COURSEPILOT_EMBEDDING_API_KEY or settings.COMPATIBLE_API_KEY
    model = settings.COURSEPILOT_EMBEDDING_MODEL

    # openai-compatible：强制真实 embedding；
    # auto：只有 base_url/api_key/model 都齐全时才用真实 embedding。
    if provider == "openai-compatible" or (provider == "auto" and base_url and api_key and model):
        if not base_url or not api_key or not model:
            raise ValueError(...)
        return OpenAIEmbeddings(model=model, base_url=base_url, api_key=...)

    # 默认兜底：不外呼网络，保证本地测试能跑。
    return HashingEmbeddings()
```

为什么这样做：

- 生产环境需要真实 embedding，RAG 检索质量才可用。
- 测试环境不能依赖外部 key，所以保留 hashing fallback。
- `auto` 模式降低本地开发门槛，`openai-compatible` 模式让生产配置错误尽早暴露。

### 7.2 `src/coursepilot/rag/knowledge_points.py`

新增 `KnowledgePointExtractor`。

关键代码注释式理解：

```python
class KnowledgePointExtractor:
    def extract(self, content: str, *, max_points: int = 10) -> list[str]:
        return generate_structured(
            # 生产路径：用 prompt 让 LLM 从 chunk 中抽知识点。
            prompt_name="rag/extract_knowledge_points",
            output_schema=KnowledgePointList,
            payload={"content": content[:6000], "max_points": max_points},

            # 测试/无 key 路径：用 deterministic 正则关键词兜底。
            fallback=lambda: KnowledgePointList(
                knowledge_points=extract_keywords_deterministic(content, max_points=max_points)
            ),
        ).knowledge_points[:max_points]
```

为什么这样做：

- chunk 的知识点是后续教学设计、试题、PPT 生成的重要输入。
- LLM 抽取更贴近教学语义。
- fallback 保证测试稳定、无网络。

### 7.3 `src/coursepilot/rag/chunker.py`

修改点：

```python
class Chunker:
    def __init__(self, chunk_size: int = 1000, overlap: int = 150):
        self.knowledge_point_extractor = KnowledgePointExtractor()

    def _extract_keywords(self, content: str) -> list[str]:
        # 原先这里是正则关键词；
        # 现在统一交给 KnowledgePointExtractor。
        return self.knowledge_point_extractor.extract(content, max_points=10)
```

动机：

- chunker 仍然负责文本切分和 metadata。
- 知识点抽取成为独立策略，后续可以替换 prompt 或模型，不需要改 chunk 逻辑。

### 7.4 `src/coursepilot/rag/vector_store.py`

核心变化：

```python
class ChromaVectorStore:
    def __init__(self, persist_directory: str | None = None, embeddings: Embeddings | None = None):
        # 支持外部注入 embeddings；
        # 测试可以注入 fake，生产默认使用 get_coursepilot_embeddings()。
        self.embeddings = embeddings or get_coursepilot_embeddings()
```

```python
def add_verified_texts(...):
    # 审核通过的内容写回 Chroma 时统一打 verified=True。
    normalized = {
        "course_id": course_id,
        "verified": True,
        "chroma_collection": collection_name,
        **metadata,
    }
```

```python
def search(...):
    # 使用 similarity_search_with_score 取回 Chroma 距离。
    docs_with_distances = self.collection_for_course(course_id).similarity_search_with_score(...)

    # 把距离转成 0-1 方向的相似度分数；
    # 距离越小，1/(1+distance) 越接近 1。
    return [(doc, 1.0 / (1.0 + max(float(distance), 0.0))) for doc, distance in docs_with_distances]
```

为什么这样做：

- embedding 工厂/注入解除 Chroma 对 hashing 的硬编码依赖。
- `verified_only=true` 检索依赖 metadata，因此写回时必须统一打 `verified=True`。
- Chroma 返回的 score 常是距离，不直接等价于相似度；转换后更适合展示与测试断言。

### 7.5 `src/coursepilot/validators/duplicate_detector.py`

修改点：

```python
class DuplicateDetector:
    def __init__(self, threshold: float = 0.85, embeddings: Embeddings | None = None):
        # 不再硬编码 HashingEmbeddings；
        # 使用真实 embedding 时，重复题检测也能共享同一语义空间。
        self.embeddings = embeddings or get_coursepilot_embeddings()
```

动机：

- 题目重复度检测属于 harness engineering。
- 生产环境应使用真实 embedding，测试环境使用 hashing fallback。

### 7.6 `src/coursepilot/services/document_service.py`

修改点：

```python
SUPPORTED_UPLOAD_SUFFIXES = {".pdf", ".docx", ".txt", ".md", ".markdown", ".xlsx"}

if suffix == ".doc":
    raise ValueError("Unsupported legacy .doc file. Please convert it to .docx before upload.")
```

为什么这样做：

- `.doc` 是旧二进制格式，解析依赖复杂，容易到构建知识库阶段才失败。
- 入口直接拒绝，错误信息更明确：请转 `.docx`。

## 8. Lesson workflow 说明

### 8.1 LangGraph 编排

文件：

```text
src/agents/coursepilot/graphs/lesson_graph.py
```

当前 workflow：

```text
route
  -> retrieve_course_context
  -> extract_knowledge_points
  -> plan_sessions
  -> generate_lesson_design
  -> validate_lesson_design
  -> reflect_and_revise
  -> validate_lesson_design
  -> END
```

如果没有 `lesson_params`，graph 走 `chat_response`，提示用户使用产品 API。

关键代码注释式理解：

```python
def should_repair(state):
    report = state.get("validation_report", {})

    # 只有 schema、课时数、时间分配、必填字段、知识覆盖、引用全部通过，
    # 才认为教学设计通过。
    passed = all(report.get(key, False) for key in [...])

    # repair 次数受 settings 控制，避免无限循环。
    if not passed and repair_attempts < settings.COURSEPILOT_MAX_REPAIR_ROUNDS:
        return "repair"
    return "done"
```

### 8.2 节点职责

文件：

```text
src/agents/coursepilot/nodes/retrieve_nodes.py
src/agents/coursepilot/nodes/lesson_nodes.py
src/agents/coursepilot/nodes/validation_nodes.py
src/agents/coursepilot/nodes/repair_nodes.py
```

节点说明：

- `retrieve_course_context`：根据 `course_id` 和章节/教学重点检索课程知识库。
- `extract_knowledge_points`：从检索上下文中抽知识点。
- `plan_sessions`：根据知识点和参数规划每个课时。
- `generate_lesson_design`：生成完整 `LessonDesignContent`。
- `validate_lesson_design`：用 `LessonValidator` 做 schema、课时数、时间、引用等校验。
- `reflect_and_revise`：校验失败时调用 repair prompt 修复。

关键代码注释式理解：

```python
def extract_knowledge_points(state):
    contexts = state.get("retrieved_contexts", [])

    # 把检索到的 chunk 内容合并，作为知识点抽取材料。
    content = "\n\n".join(context["content"] for context in contexts)

    result = generate_structured(
        prompt_name="lesson/extract_knowledge_points",
        output_schema=KnowledgePointList,
        payload={
            "lesson_params": state.get("lesson_params", {}),
            "retrieved_contexts": contexts,
            "max_points": 12,
        },
        # 无 LLM 时用正则关键词 fallback。
        fallback=lambda: KnowledgePointList(...)
    )
```

```python
def generate_lesson_design(state):
    # 这里不再手写拼接教学设计；
    # LLM 输出必须符合 LessonDesignContent。
    design = generate_structured(
        prompt_name="lesson/generate_lesson_design",
        output_schema=LessonDesignContent,
        payload={
            "lesson_params": ...,
            "retrieved_contexts": ...,
            "knowledge_points": ...,
            "session_plan": ...,
        },
        fallback=lambda: _deterministic_lesson_design(state),
    )
```

```python
def reflect_and_revise(state):
    # repair 不是简单重跑 generate，
    # 而是把校验报告、原教案、参数、检索上下文交给 fix_json prompt。
    repaired = generate_structured(
        prompt_name="repair/fix_json",
        output_schema=LessonDesignContent,
        payload={
            "target_schema": "LessonDesignContent",
            "validation_report": report,
            "lesson_design": state.get("lesson_design", {}),
            "lesson_params": state.get("lesson_params", {}),
            "retrieved_contexts": state.get("retrieved_contexts", []),
        },
        fallback=lambda: _deterministic_repair(state),
    )
```

### 8.3 Service 层变化

文件：

```text
src/coursepilot/services/lesson_service.py
```

关键变化：

```python
result = coursepilot_lesson_agent.invoke(
    {
        "course_id": course_id,
        "lesson_params": {
            **params.model_dump(mode="json"),
            "course_name": course.course_name,
        },
    }
)
```

动机：

- service 不再直接拼教学设计。
- 它只负责创建任务、调用 graph、校验 graph 输出、持久化结果。

持久化内容：

- `LessonDesign.content_json`：完整教学设计 JSON。
- `LessonDesign.validation_report_json`：校验报告。
- `GenerationTask.intermediate_outputs_json`：检索上下文、知识点、课时规划。

这让后续教师审核时能追溯“生成依据是什么”。

### 8.4 局部修订

文件：

```text
src/coursepilot/services/lesson_service.py
src/coursepilot/prompts/lesson/revise_lesson_design.md
```

修改点：

```python
content = generate_structured(
    prompt_name="lesson/revise_lesson_design",
    output_schema=LessonDesignContent,
    payload={
        "lesson_design": content.model_dump(mode="json"),
        "target_scope": request.target_scope,
        "feedback_text": request.feedback_text,
        "keep_unchanged_parts": request.keep_unchanged_parts,
        "retrieved_contexts": [...],
    },
    fallback=lambda: self._revise_lesson_deterministically(content, request),
)
```

动机：

- 局部修订也进入 LLM 结构化输出路径。
- fallback 只作为测试兜底。

## 9. Exam workflow 说明

### 9.1 LangGraph 编排

文件：

```text
src/agents/coursepilot/graphs/exam_graph.py
```

当前 workflow 被拆成两个阶段。

阶段一：生成 blueprint

```text
route
  -> retrieve_course_context
  -> plan_exam_blueprint
  -> END
```

阶段二：生成 questions

```text
route
  -> generate_exam_questions
  -> validate_exam_questions
  -> repair_exam_questions
  -> validate_exam_questions
  -> END
```

关键代码注释式理解：

```python
def route_entry(state):
    # 如果 workflow_phase=questions 且传入 exam_blueprint，
    # 表示已经有确认后的蓝图，直接进入出题阶段。
    if state.get("workflow_phase") == "questions" and "exam_blueprint" in state:
        return "questions"

    # 如果传入 exam_params，表示要创建蓝图。
    if "exam_params" in state:
        return "workflow"

    return "chat"
```

```python
def after_blueprint(state):
    # create_blueprint API 只生成蓝图，不直接出题。
    # 这给教师留下审核/确认蓝图的步骤。
    if state.get("workflow_phase") == "blueprint":
        return "done"
    return "generate"
```

### 9.2 节点职责

文件：

```text
src/agents/coursepilot/nodes/exam_nodes.py
```

节点说明：

- `plan_exam_blueprint`：根据检索上下文和考试参数生成 `ExamBlueprintContent`。
- `generate_exam_questions`：按题型 group 逐组调用 prompt，输出 `QuestionSet`。
- `validate_exam_questions`：校验题量、分值、选项、答案、解析、知识覆盖、引用、重复度。
- `repair_exam_questions`：使用 repair prompt 补齐缺失题目或修复结构。

关键代码注释式理解：

```python
for group in blueprint.question_groups:
    # 每个题型 group 单独调用 prompt。
    # 好处是题量和题型控制更清晰，repair 时也更容易定位。
    result = generate_structured(
        prompt_name=f"exam/generate_{group.question_type}",
        output_schema=QuestionSet,
        payload={
            "blueprint": blueprint.model_dump(mode="json"),
            "question_group": group.model_dump(mode="json"),
            "existing_questions": [...],
        },
        fallback=lambda: QuestionSet(...),
    )
```

### 9.3 blueprint 确认机制

文件：

```text
src/coursepilot/services/exam_service.py
src/coursepilot/api/routes_exams.py
```

核心逻辑：

```python
if blueprint.status != "confirmed":
    raise BlueprintNotConfirmedError("Exam blueprint must be confirmed before generating questions")
```

API 层：

```python
try:
    result = service.generate_questions(blueprint_id)
except BlueprintNotConfirmedError as exc:
    raise HTTPException(status_code=409, detail=str(exc))
```

为什么返回 409：

- blueprint 未确认不是参数格式错误，也不是资源不存在。
- 它表示当前资源状态不允许执行生成题目操作。
- 这符合 REST 中的 conflict 语义。

## 10. PPT workflow 说明

### 10.1 LangGraph 编排

文件：

```text
src/agents/coursepilot/graphs/ppt_graph.py
```

生成大纲 workflow：

```text
route
  -> generate_slide_outline
  -> validate_slide_outline
  -> repair_slide_outline
  -> validate_slide_outline
  -> maybe_export
  -> END
```

导出 PPTX workflow：

```text
route
  -> validate_slide_outline
  -> maybe_export
  -> build_pptx
  -> save_export_file
  -> END
```

关键代码注释式理解：

```python
def route_entry(state):
    # 如果已有 slide_outline 且提供 pptx_output_path，
    # 表示这是导出 workflow，不重新生成大纲。
    if state.get("slide_outline") and state.get("pptx_output_path"):
        return "export"

    # 如果传入 lesson_design，表示需要从教案生成 PPT 大纲。
    if "lesson_design" in state:
        return "workflow"

    return "chat"
```

```python
def should_export(state):
    # 同一个 graph 既能生成大纲，也能执行导出。
    # 是否导出由 pptx_output_path 决定。
    if state.get("pptx_output_path"):
        return "export"
    return "done"
```

### 10.2 节点职责

文件：

```text
src/agents/coursepilot/nodes/ppt_nodes.py
```

节点说明：

- `generate_slide_outline`：基于 lesson design 生成 `SlideOutlineContent`。
- `validate_slide_outline`：校验页数、类型、内容、课时来源、引用。
- `repair_slide_outline`：用 repair prompt 修复缺引用、缺内容、页数不符等问题。
- `build_pptx`：调用 `PPTXExporter` 生成实际 `.pptx` 文件。
- `save_export_file`：返回导出文件元数据，service 再写入 `ExportFile`。

关键代码注释式理解：

```python
def build_pptx(state):
    # graph 负责真正执行 PPTX 构建；
    # exporter 仍只负责把结构化 outline 渲染成文件。
    outline = SlideOutlineContent.model_validate(state.get("slide_outline", {}))
    output_path = Path(state["pptx_output_path"])
    path = PPTXExporter().export(outline, output_path)
    return {"pptx_file_path": str(path)}
```

```python
def save_export_file(state):
    # graph 不直接写数据库；
    # 它只返回导出文件元数据，由 service 负责事务持久化。
    return {
        "export_file": {
            "file_type": "pptx",
            "file_name": Path(path).name,
            "file_path": path,
            "file_role": "pptx",
        }
    }
```

### 10.3 Service 层变化

文件：

```text
src/coursepilot/services/ppt_service.py
```

关键变化：

- `generate_outline()` 调用 `coursepilot_ppt_agent.invoke()` 生成并校验大纲。
- `export_pptx()` 调用同一个 graph 的 export 路径。
- service 负责把返回的 `export_file` 元数据写入 `ExportFile` 表。

## 11. Review write-back 说明

文件：

```text
src/coursepilot/services/review_service.py
```

本次扩展支持：

```text
ppt_outline
lesson_design
question
```

核心流程：

```text
create_review
  -> 标记审核状态
  -> 如果 approved，则 write_back_status=pending

write_back
  -> 创建 review 类型的 Document 记录
  -> 把审核内容转换成 chunk
  -> 写入 Chroma，metadata verified=true
  -> 写入 coursepilot_chunks 表，verified=true
  -> 更新 write_back_status=written
```

关键代码注释式理解：

```python
review_document = self._create_review_document(review)
chunks = self._chunks_for_review(review, review_document.id)

# 向量库写入 verified 内容。
self.vector_store.add_verified_texts(
    course_id=review.course_id,
    texts=[chunk["text"] for chunk in chunks],
    ids=[chunk["id"] for chunk in chunks],
    metadatas=[chunk["metadata"] for chunk in chunks],
)

# 关系数据库也写入 KnowledgeChunk metadata。
# 这样 Chroma 和 DB 都能追踪这些审核后的知识。
for chunk in chunks:
    self.session.add(KnowledgeChunk(..., verified=True, ...))
```

为什么这样做：

- PRD 9.6 要求教师审核内容可以沉淀回课程知识库。
- 后续生成教案、试题、PPT 时，RAG 可以检索到人工确认过的内容。
- `verified_only=true` 可以专门检索已审核内容。

不同 target 的 chunk 化策略：

- `ppt_outline`：每页 slide 变成一个 chunk。
- `lesson_design`：每个课时变成一个 chunk。
- `question`：单题、答案、解析、选项合成一个 chunk。

## 12. Client 与 UI 改造说明

### 12.1 `src/client/coursepilot_client.py`

新增 client 方法：

```text
create_course
list_courses
list_documents
upload_document
build_kb
search_kb
generate_lesson
revise_lesson
export_lesson
create_exam_blueprint
confirm_exam_blueprint
generate_questions
list_questions
export_exam
generate_ppt_outline
export_ppt
create_review
write_back_review
```

关键代码注释式理解：

```python
def _request(self, method: str, path: str, **kwargs) -> Any:
    # 所有 CoursePilot API 自动加 /api/coursepilot 前缀。
    response = httpx.request(
        method,
        f"{self.base_url}/api/coursepilot{path}",
        headers=self.headers,
        timeout=timeout,
        **kwargs,
    )

    # 统一把 httpx 异常转成 AgentClientError，
    # UI 层只处理一种客户端异常。
    response.raise_for_status()
    return response.json()
```

动机：

- UI 不直接关心 URL 细节。
- 单元测试可以 mock client，而不是 mock 很多 `httpx` 调用。
- API 变动时只改 client。

### 12.2 `src/coursepilot/ui/knowledge_base_page.py`

修改点：

- 从分散 `httpx` 请求改成实例化 `CoursePilotClient`。
- 页面仍负责 Streamlit 状态、表单、按钮和展示。
- API 访问逻辑集中在 client。

动机：

- UI 更薄，业务边界更清楚。
- 更容易测试 CoursePilot 页面是否调用正确 client 方法。

## 13. Public API 行为变化

REST 路径保持不变。

新增行为：

```text
POST /api/coursepilot/exams/{blueprint_id}/generate
```

如果 blueprint 不是 `confirmed`，返回：

```text
HTTP 409 Conflict
```

动机：

- 对齐 PRD 的人工审核/确认流程。
- 防止系统在教师未确认考点与分值规划时直接出题。

其他 API 路径保持兼容，主要是内部实现从 service builder 改为 graph。

## 14. 测试说明

### 14.1 新增/修改测试覆盖点

LLM/prompt/embedding：

- `tests/coursepilot/test_llm_infra.py`
- 验证 prompt loader。
- 验证 embedding factory 默认 hashing fallback。
- 验证 OpenAI-compatible embedding 参数。

试卷蓝图确认：

- `tests/coursepilot/test_exam_api.py`
- 验证未 confirmed blueprint 生成题目返回 409。

上传格式：

- `tests/coursepilot/test_retriever.py`
- 验证 `.doc` 明确拒绝，并提示转换 `.docx`。

审核写回：

- `tests/coursepilot/test_write_back.py`
- 验证 `lesson_design` 和 `question` 写回后可以通过 `verified_only=true` 检索。

客户端：

- `tests/client/test_coursepilot_client.py`
- 验证 CoursePilotClient 的路径、上传、错误处理。

UI：

- `tests/app/test_streamlit_app.py`
- 验证 Streamlit 页面仍可加载，并通过 client 路径工作。

### 14.2 已执行过的回归命令

本次改造过程中已执行并通过：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot -q
.\.venv\Scripts\python.exe -m pytest tests\core\test_llm.py tests\core\test_settings.py -q
.\.venv\Scripts\python.exe -m pytest tests\service tests\client -q
.\.venv\Scripts\python.exe -m pytest tests\app\test_streamlit_app.py -q
.\.venv\Scripts\python.exe -m compileall -q src tests
```

也执行过组合回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot tests\client\test_coursepilot_client.py tests\app\test_streamlit_app.py -q
```

其中 `tests\service tests\client` 出现过项目已有 warning，例如 LangGraph deprecation、TestClient timeout、AsyncMock warning；这些不是本次 CoursePilot 改造引入的失败。

## 15. 如何运行检查修改效果

### 15.1 只跑本地 deterministic 测试

不配置真实 LLM key，直接运行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot -q
.\.venv\Scripts\python.exe -m pytest tests\client\test_coursepilot_client.py -q
.\.venv\Scripts\python.exe -m pytest tests\app\test_streamlit_app.py -q
```

预期：

- 不会外呼 LLM。
- embedding 默认使用 hashing fallback。
- CoursePilot graph/service/API/client/UI 测试通过。

### 15.2 检查核心配置

```powershell
.\.venv\Scripts\python.exe -m pytest tests\core\test_llm.py tests\core\test_settings.py -q
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_llm_infra.py -q
```

预期：

- settings 能识别新增 CoursePilot 配置。
- prompt loader 与 embedding factory 正常工作。

### 15.3 启动后端服务

项目已有入口是：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

如果需要先执行数据库迁移：

```powershell
.\.venv\Scripts\alembic.exe upgrade head
```

后端启动后，CoursePilot API 前缀为：

```text
/api/coursepilot
```

### 15.4 启动 Streamlit 页面

另开一个 PowerShell：

```powershell
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py
```

进入页面后，可以按这个业务顺序手工验收：

```text
1. 创建课程
2. 上传 .pdf/.docx/.txt/.md/.xlsx 资料
3. 构建知识库
4. 搜索知识库
5. 生成教学设计
6. 基于教学设计生成 PPT 大纲
7. 导出 PPTX
8. 创建试卷 blueprint
9. 确认 blueprint
10. 生成试题
11. 创建审核记录
12. 写回知识库
13. 用 verified_only=true 搜索已审核内容
```

### 15.5 Docker 方式

如果使用 Docker：

```powershell
docker compose up --build
```

检查服务健康状态：

```powershell
docker compose ps
```

说明：

- 本次代码回归没有启动完整 Docker 环境。
- README 已补充 Docker 与 CoursePilot 配置说明。

### 15.6 使用真实 LLM/embedding 验收

`.env` 中配置：

```text
MODEL=openai-compatible
COMPATIBLE_MODEL=你的聊天模型名
COMPATIBLE_BASE_URL=https://你的兼容接口/v1
COMPATIBLE_API_KEY=你的 API key

COURSEPILOT_GENERATION_MODE=llm
COURSEPILOT_EMBEDDING_PROVIDER=openai-compatible
COURSEPILOT_EMBEDDING_MODEL=你的 embedding 模型名
COURSEPILOT_EMBEDDING_BASE_URL=https://你的兼容接口/v1
COURSEPILOT_EMBEDDING_API_KEY=你的 API key
```

然后重新启动服务：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
```

建议真实模型验收顺序：

```text
1. 上传一份课程资料并构建知识库。
2. 搜索章节关键词，确认能检索到相关 chunk。
3. 生成教学设计，检查引用 chunk_id 是否存在。
4. 生成试卷 blueprint，人工确认。
5. 生成试题，检查题量、分值、答案、解析、引用。
6. 生成 PPT 大纲并导出 PPTX。
7. 审核通过一条 lesson/question/ppt 内容并写回。
8. 使用 verified_only=true 检索写回内容。
```

## 16. 你需要重点理解的工程细节

### 16.1 LLM 不直接生成文件

LLM 只生成结构化 JSON。

```text
LLM -> LessonDesignContent / QuestionSet / SlideOutlineContent
Exporter -> DOCX / PPTX
```

这样做的好处：

- 文件生成稳定，不依赖模型直接输出二进制。
- JSON 可校验、可 repair、可持久化、可审核。
- exporter 可独立测试。

### 16.2 deterministic fallback 不是生产能力

fallback 的目的：

- 保证 CI 不外呼；
- 保证本地无 key 可以跑通；
- 保证 graph/service/API 测试可重复。

生产质量依赖真实 LLM 和真实 embedding。

### 16.3 service 和 graph 的边界

建议记住这条边界：

```text
service 管事务和数据库；
graph 管智能体流程；
node 管一个具体步骤；
prompt 管模型行为；
schema 管输入输出契约；
validator 管质量门禁；
exporter 管文件渲染。
```

这个边界是本次工程化的核心。

### 16.4 repair 是 harness engineering 的一部分

repair 不是“多试几次”这么简单。

当前做法：

- validator 先产出明确失败报告；
- repair prompt 接收失败报告和原始 JSON；
- 修复结果再次进入 validator；
- 超过 `COURSEPILOT_MAX_REPAIR_ROUNDS` 后停止。

这对应 PRD 13 中的 schema 校验、引用校验、数量校验、异常重试。

### 16.5 verified write-back 是长期记忆入口

审核写回不是简单改状态，而是把教师确认过的内容重新写入 RAG 知识库。

后续系统会更偏向检索到：

- 人工确认的教学设计；
- 人工确认的题目；
- 人工确认的 PPT 大纲。

这会让 CoursePilot 随着使用逐步积累课程知识资产。

## 17. 与 PRD 的对齐关系

| PRD 要求 | 本次对应实现 |
| --- | --- |
| 7.1 主流程 | 保留课程资料入库、知识库构建、Agent 生成、导出、审核、写回闭环 |
| 7.2 Agent 架构原则 | lesson/exam/ppt 改为 LangGraph workflow |
| FR-002 上传课程资料 | `.doc` 明确拒绝，避免构建阶段才失败 |
| FR-003 文档解析与 chunk 切分 | chunker 接入 KnowledgePointExtractor |
| FR-004 构建私有课程知识库 | Chroma 使用 embedding 工厂，支持真实 embedding |
| FR-006 课程资料检索与知识点抽取 | retrieve 节点 + LLM 知识点抽取 |
| FR-007 生成课时规划 | `plan_sessions` prompt + `SessionPlanSet` |
| FR-008 生成完整教学设计 | `generate_lesson_design` prompt + `LessonDesignContent` |
| FR-009 教学设计质量校验 | `LessonValidator` + repair loop |
| FR-010 教学设计局部修改 | `revise_lesson_design` prompt |
| FR-012 生成 PPT 大纲 | `generate_slide_outline` prompt + `SlideOutlineContent` |
| FR-013 生成 PPTX 文件 | PPT graph 增加 `build_pptx` 与 `save_export_file` |
| FR-015 生成考点与分值规划 | exam blueprint phase |
| FR-016 按题型生成题目 | exam questions phase，按题型 group 生成 |
| FR-017 题目质量校验 | `QuestionValidator` + duplicate detector + repair |
| FR-019 教师审核生成内容 | ReviewService 更新目标状态 |
| FR-020 已审核内容写回知识库 | `write_back()` 写入 Chroma 与 `KnowledgeChunk`，metadata `verified=true` |
| 12.2 教学设计 Workflow | retrieve -> extract -> plan -> generate -> validate -> repair |
| 12.3 PPT 生成 Workflow | generate outline -> validate -> repair -> export |
| 12.4 作业/试卷生成 Workflow | blueprint -> confirm -> questions -> validate -> repair |

## 18. 后续建议

短期建议：

- 增加可选的真实 LLM integration test，默认跳过，只有配置 key 时运行。
- 增加 prompt 版本号或 prompt hash，写入 `GenerationTask.intermediate_outputs_json`。
- 给每次 graph invoke 记录 trace id，方便生产排障。
- 生产代码里为 `COURSEPILOT_GENERATION_MODE=llm` 增加启动时健康检查， 给需要调用LLM API服务的地方加 retry/fallback/logging，专门处理 choices is None、超时、解析失败、生成中断等意外情况，确保有兜底方案。
- 调用LLM返回的内容中英混杂，希望在 prompt 里明确要求输出主体内容为中文（除了代码、常用术语等必须使用英文的内容）。
- 我希望会在前端UI显示的各类名称是可以通过自然语言理解的，而不仅仅是使用生成的随机UUID，比如导出的文件名等。



中期建议：

- 增加模型质量评估集，覆盖不同课程类型。
- 对 verified 内容做权重提升或单独检索策略。
- 增加导出文件下载历史页面。
- 增加教师对 prompt 输出质量的评分反馈，并沉淀到 eval 数据。

## 19. 快速检查清单

如果你只想快速确认这次改造是否生效，按顺序执行：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_llm_infra.py -q
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_exam_api.py -q
.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_write_back.py -q
.\.venv\Scripts\python.exe -m pytest tests\client\test_coursepilot_client.py -q
.\.venv\Scripts\python.exe -m compileall -q src tests
```

然后启动：

```powershell
.\.venv\Scripts\python.exe src\run_service.py
.\.venv\Scripts\streamlit.exe run src\streamlit_app.py
```

用页面走一遍：

```text
创建课程 -> 上传资料 -> 构建知识库 -> 生成教案 -> 生成/导出 PPT -> 生成 blueprint -> 确认 blueprint -> 生成题目 -> 审核写回 -> verified_only 检索
```
