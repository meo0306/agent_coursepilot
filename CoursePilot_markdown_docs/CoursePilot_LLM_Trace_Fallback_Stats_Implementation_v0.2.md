# CoursePilot LLM 追踪、兜底与统计实现说明 v0.2

本文说明本次 CoursePilot LLM 工程化补强具体做了哪些改动、为什么这样做、每个新增/修改文件承担什么职责，以及如何运行命令验证效果。

参考文档：

- `CoursePilot_markdown_docs/phase_audit/CoursePilot_Phase0_Audit_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_LLM_Engineering_Refactor_Explanation_v0.1.md`
- `CoursePilot_markdown_docs/CoursePilot_Technical_Architecture_v0.2.md`

## 1. 本次实现的核心目标

这次不是重做 CoursePilot 架构，而是在原有 LLM + LangGraph + service 持久化路径上补齐生产可观测性和失败兜底。

对应目标可以拆成 6 件事：

1. 真实 LLM integration test 默认跳过，只有显式配置 key 和开关时运行。
2. 每次 LLM 调用记录 prompt hash 和调用元数据，并写入 `GenerationTask.intermediate_outputs_json`。
3. 复用 LangGraph 已有 `thread_id` 作为本次 graph invoke 的 trace id，不再新增并行概念。
4. `COURSEPILOT_GENERATION_MODE=llm` 时启动阶段做 LLM 健康检查，运行时失败则分类、重试、最终 fallback。
5. 所有 prompt 自动追加中文输出约束，减少中英混杂。
6. 导出文件名改成可读名称，UUID 只保留短后缀作为去重标识。

本次刻意没有做的事：

- 没有新增数据库迁移。
- 没有修改 API 返回结构的必填字段。
- 没有新增独立 `trace_id` 字段，因为现有 `thread_id` 已经能承担同一职责。
- 没有估算费用金额，只统计 token、调用次数、失败次数、fallback 次数和耗时。

## 2. 整体数据流

改造后的完整生成链路如下：

```text
Service 创建 GenerationTask
  -> new_workflow_config() 生成 thread_id
  -> start_graph_invocation() 写入 graph_invocations.running
  -> collect_coursepilot_llm_metadata(thread_id)
  -> LangGraph invoke
  -> graph node 调用 generate_structured()
  -> generate_structured() 记录 prompt hash / attempts / usage / fallback
  -> finish_graph_invocation() 标记 success 或 failed
  -> merge_llm_metadata() 合并 prompt_hashes / llm_invocations / llm_usage_summary
  -> GenerationTask.intermediate_outputs_json 落库
```

最终一个 task 的 `intermediate_outputs_json` 会多出这些字段：

```json
{
  "graph_invocations": [
    {
      "namespace": "lesson",
      "thread_id": "coursepilot-lesson-a1ca18ad-b4cf-4bd0-8859-0013c852e77a",
      "status": "success",
      "started_at": "2026-07-06T...",
      "finished_at": "2026-07-06T...",
      "error_message": null
    }
  ],
  "prompt_hashes": {
    "lesson/generate_lesson_design": {
      "prompt_name": "lesson/generate_lesson_design",
      "prompt_sha256": "64位 sha256",
      "schema": "LessonDesignContent",
      "language_policy": "zh_main_content"
    }
  },
  "llm_invocations": [
    {
      "prompt_name": "lesson/generate_lesson_design",
      "attempt_count": 1,
      "fallback_used": false,
      "fallback_reason": null,
      "error_category": null,
      "latency_ms": 2313,
      "usage": {
        "input_tokens": 265,
        "output_tokens": 83,
        "total_tokens": 348
      }
    }
  ],
  "llm_usage_summary": {
    "call_count": 1,
    "successful_call_count": 1,
    "failed_attempt_count": 0,
    "fallback_count": 0,
    "latency_ms": 2313,
    "input_tokens": 265,
    "output_tokens": 83,
    "total_tokens": 348,
    "by_prompt": {
      "lesson/generate_lesson_design": {
        "call_count": 1,
        "successful_call_count": 1,
        "failed_attempt_count": 0,
        "fallback_count": 0,
        "latency_ms": 2313,
        "input_tokens": 265,
        "output_tokens": 83,
        "total_tokens": 348
      }
    }
  }
}
```

其中 token 统计来自 provider 返回的 `raw.usage_metadata` 或 `raw.response_metadata["token_usage"]`。如果 provider 不返回 usage，则 usage 为 `null`，汇总 token 字段也保持 `null`，不会自己估算费用。

## 3. 新增文件

### 3.1 `src/coursepilot/services/workflow_tracking.py`

职责：统一把 graph invoke 和 LLM 调用统计写入 `GenerationTask.intermediate_outputs_json`，避免 lesson/exam/ppt 三个 service 各写一套重复逻辑。

新增动机：

- 每次 graph invoke 都要记录开始、结束、状态、错误和 `thread_id`。
- 每次 workflow 完成后都要把 LLM collector 中的数据合并进 task JSON。
- 这些逻辑横跨 lesson、exam、ppt，适合放在小工具模块里。

代码注释式理解：

```python
def start_graph_invocation(*, task_outputs, namespace, thread_id):
    # task_outputs 是数据库里已有的 intermediate_outputs_json。
    # 这里先复制一份，避免直接修改 SQLAlchemy 已持有的旧 dict。
    outputs = dict(task_outputs or {})

    # graph_invocations 是数组，因为同一个任务可能被追加执行多个阶段。
    # 例如 exam blueprint 先生成蓝图，之后 generate_questions 会追加第二次 graph invoke。
    invocations = list(outputs.get("graph_invocations", []))

    # 记录 running 状态。即使后续 graph 抛错，service 的 except 分支也能把它改成 failed。
    invocations.append({
        "namespace": namespace,
        "thread_id": thread_id,
        "status": "running",
        "started_at": utc_iso(),
        "finished_at": None,
        "error_message": None,
    })
```

```python
def finish_graph_invocation(*, task_outputs, thread_id, status, error_message=None):
    # 只更新当前 thread_id 且仍处于 running 的那条记录。
    # 这样不会误改同一个 task 上其他阶段的 graph_invocations。
    for invocation in reversed(invocations):
        if invocation.get("thread_id") == thread_id and invocation.get("status") == "running":
            invocation["status"] = status
            invocation["finished_at"] = utc_iso()
            invocation["error_message"] = error_message
            break
```

```python
def merge_llm_metadata(task_outputs, collector):
    # collector.to_task_metadata() 会返回：
    # prompt_hashes、llm_invocations、llm_usage_summary。
    metadata = collector.to_task_metadata()

    # prompt hash 按 prompt_name 合并，后一次同名 prompt 会覆盖旧 hash。
    # 这符合需求：我们关心当前版本 prompt 最终是什么。
    prompt_hashes.update(metadata["prompt_hashes"])

    # llm_invocations 是调用流水，必须追加而不是覆盖。
    outputs["llm_invocations"] = existing + metadata["llm_invocations"]

    # summary 是本次 collector 汇总结果。
    # 如果同一个 task 追加多阶段，后续可以继续扩展为跨阶段累计。
    outputs["llm_usage_summary"] = metadata["llm_usage_summary"]
```

### 3.2 `src/coursepilot/services/file_naming.py`

职责：生成可读的导出文件名，只把 UUID 作为短后缀保留。

新增动机：

- 原来导出文件名主要依赖随机 UUID，不适合前端 UI 展示。
- 新命名仍然保留短 id，避免同名课程、同章节、同类型导出时文件冲突。
- 不改数据库字段，不改下载 API 结构，只改变 `file_name` 和实际保存路径的文件名。

代码注释式理解：

```python
def readable_export_filename(*, course_name, topic, role, unique_id, extension):
    # course_name: 课程名，例如 AI Search。
    # topic: 章节/主题，例如 Chapter 1。
    # role: 文件用途，例如 lesson_design、student_exam、ppt_outline。
    parts = [_slug(course_name), _slug(topic), _slug(role)]

    # 过滤空值后用下划线拼接。
    # 如果课程名和主题都缺失，至少保留 role。
    stem = "_".join(part for part in parts if part) or _slug(role)

    # UUID 不再作为主体文件名，只截取前 8 位作为短后缀。
    short_id = _slug(unique_id)[:8] or "export"

    # extension 可以传 ".docx" 或 "docx"，最终统一成 docx。
    ext = extension.removeprefix(".")
    return f"{stem}_{short_id}.{ext}"
```

示例：

```text
AI_Search_lesson_design_ab12cd34.docx
AI_Search_student_exam_ab12cd34.docx
AI_Search_ppt_outline_ab12cd34.pptx
```

### 3.3 `tests/coursepilot/test_llm_integration.py`

职责：新增真实 LLM integration test，但默认跳过。

新增动机：

- CI 和本地无 key 环境不能强依赖真实 LLM。
- 但需要保留一条可以主动验证 OpenAI-compatible provider、json mode、structured output、usage summary 的路径。

运行条件：

```text
COURSEPILOT_RUN_LLM_INTEGRATION=1
MODEL=openai-compatible
COMPATIBLE_MODEL=...
COMPATIBLE_BASE_URL=...
COMPATIBLE_API_KEY=...
```

测试内容：

- 调用一次最小 structured output。
- 断言能拿到 Pydantic parsed result。
- 打印 `llm_usage_summary`，方便观察 token 和耗时。

### 3.4 `tests/coursepilot/test_workflow_metadata.py`

职责：验证完整 service workflow 后，task JSON 里确实包含 graph 和 LLM 元数据。

新增动机：

- `llm.py` 的单元测试只能证明调用包装器正确。
- 本测试用 fake lesson graph + SQLite session 验证 service 层真的把 metadata 写入 `GenerationTask.intermediate_outputs_json`。

覆盖点：

- `new_workflow_config()` 生成的 `thread_id` 进入 metadata 和 tags。
- lesson 完整流程后有 `graph_invocations`。
- prompt hash 进入 `prompt_hashes`。
- fallback 统计进入 `llm_usage_summary`。

## 4. 修改文件详解

### 4.1 `src/core/settings.py`

新增配置：

```python
COURSEPILOT_LLM_TIMEOUT_SECONDS: float = 30.0
COURSEPILOT_LLM_MAX_RETRIES: int = 2
```

动机：

- `COURSEPILOT_LLM_TIMEOUT_SECONDS` 控制每次 LLM 请求最长等待时间。
- `COURSEPILOT_LLM_MAX_RETRIES` 控制失败后最多额外重试几次。
- 实际最大 attempt 数为 `1 + COURSEPILOT_LLM_MAX_RETRIES`，默认是 3 次。

说明：

- `COURSEPILOT_RUN_LLM_INTEGRATION` 没有放入 settings，因为它只用于 pytest integration test gate，测试里直接读取 `os.getenv()`。

### 4.2 `src/coursepilot/llm.py`

这是本次最核心的修改文件。它现在是 CoursePilot 所有结构化 LLM 调用的统一入口。

#### 4.2.1 固定异常分类

新增固定分类：

```python
ERROR_CHOICES_NONE = "choices_none"
ERROR_TIMEOUT = "timeout"
ERROR_STRUCTURED_PARSE = "structured_parse_error"
ERROR_PYDANTIC_VALIDATION = "pydantic_validation_error"
ERROR_GENERATION_INTERRUPTED = "generation_interrupted"
ERROR_PROVIDER = "llm_provider_error"
ERROR_UNKNOWN = "unknown_llm_error"
```

动机：

- 日志里不能只看到一串 provider 报错文本。
- 测试和生产排障需要稳定的分类字段。
- fallback 发生时必须能看出“因为哪类异常才 fallback”。

分类逻辑在 `_classify_exception()`：

```python
def _classify_exception(exc):
    # 如果前面已经包装成 CoursePilotLLMCallError，直接使用内部 category。
    if isinstance(exc, CoursePilotLLMCallError):
        return exc.category

    # Python 原生 TimeoutError 和消息里包含 timeout/timed out 的异常都归为 timeout。
    if isinstance(exc, TimeoutError):
        return ERROR_TIMEOUT

    # provider 有时会把 choices is None 包在普通异常消息里。
    if "choices" in message and "none" in message:
        return ERROR_CHOICES_NONE

    # Pydantic schema 校验失败单独归类，和 JSON parse 错误区分。
    if isinstance(exc, ValidationError):
        return ERROR_PYDANTIC_VALIDATION

    # JSON 解析、structured parser 错误归为 structured_parse_error。
    if "parsing" in name or "parse" in message or "json" in message:
        return ERROR_STRUCTURED_PARSE

    # finish_reason 异常、content_filter、incomplete 等归为生成中断。
    if any(token in message for token in ["finish_reason", "interrupted", "content_filter", "incomplete"]):
        return ERROR_GENERATION_INTERRUPTED

    # OpenAI-compatible provider、rate limit、API 类错误归为 provider error。
    if "openai" in module or "api" in name or "rate" in name:
        return ERROR_PROVIDER

    return ERROR_UNKNOWN
```

#### 4.2.2 中文输出约束

新增全局 language policy：

```python
_LANGUAGE_POLICY = """
Language policy:
- 输出中面向教师或学生展示的主体内容必须使用中文。
- 代码、API 名称、模型名称、文件名、通用技术术语和原始引用标题可以保留英文。
- 不要因为输入材料包含英文就把主体说明写成英文。
""".strip()
```

所有 prompt 都通过 `build_coursepilot_system_prompt()` 追加这段约束：

```python
def build_coursepilot_system_prompt(prompt: str) -> str:
    # 先保留 prompt 文件原文，再统一追加 CoursePilot 的中文主体输出要求。
    return f"{prompt.strip()}\n\n{_LANGUAGE_POLICY}"
```

动机：

- 不需要逐个 prompt 文件复制同一段中文要求。
- 后续调整输出语言策略只改一个地方。
- prompt hash 计算的是“最终 system prompt”，所以 hash 能反映这段全局约束。

#### 4.2.3 prompt hash

实现：

```python
def hash_prompt(prompt: str) -> str:
    return sha256(prompt.encode("utf-8")).hexdigest()
```

在 `generate_structured()` 开始时计算：

```python
raw_prompt = load_prompt(prompt_name)
system_prompt = build_coursepilot_system_prompt(raw_prompt)
prompt_hash = hash_prompt(system_prompt)
```

动机：

- 生产问题排查时，只看 prompt 名称不够，因为同名 prompt 可能已经修改。
- SHA-256 可以稳定标识当时实际发送给模型的 system prompt。
- hash 写入 `prompt_hashes`，不会把完整 prompt 文本落库，避免 task JSON 过大。

#### 4.2.4 LLMWorkflowCollector

新增：

```python
@dataclass
class LLMWorkflowCollector:
    thread_id: str | None = None
    invocations: list[dict[str, Any]] = field(default_factory=list)
    prompt_hashes: dict[str, dict[str, Any]] = field(default_factory=dict)
```

动机：

- 单次 LangGraph workflow 中可能有多个节点调用 LLM。
- 这些调用发生在 graph 内部，service 层不能直接看到每一次调用。
- 用 `ContextVar` 保存 collector，可以让任何 graph node 内部的 `generate_structured()` 自动记录到当前 workflow。

代码注释式理解：

```python
@contextmanager
def collect_coursepilot_llm_metadata(thread_id=None):
    # 每次 service 调用 graph 前创建一个 collector。
    collector = LLMWorkflowCollector(thread_id=thread_id)

    # ContextVar 让 graph 内部任意 generate_structured() 都能找到当前 collector。
    token = _current_collector.set(collector)
    try:
        yield collector
    finally:
        # graph invoke 结束后恢复上下文，避免串到下一次请求。
        _current_collector.reset(token)
```

#### 4.2.5 generate_structured 的新流程

核心流程：

```python
def generate_structured(*, prompt_name, output_schema, payload, fallback):
    # 1. 加载 prompt，追加中文 policy，计算 prompt hash。
    raw_prompt = load_prompt(prompt_name)
    system_prompt = build_coursepilot_system_prompt(raw_prompt)
    prompt_hash = hash_prompt(system_prompt)

    # 2. 初始化本次调用元数据。
    # 这个 record 最终会进入 llm_invocations。
    record = {
        "prompt_name": prompt_name,
        "prompt_sha256": prompt_hash,
        "schema": output_schema.__name__,
        "mode": mode,
        "thread_id": thread_id,
        "attempt_count": 0,
        "attempts": [],
        "fallback_used": False,
        "fallback_reason": None,
        "error_category": None,
        "latency_ms": None,
        "usage": None,
    }

    # 3. 如果当前配置不使用真实 LLM，直接 fallback。
    # 这不是错误，而是 deterministic / auto 无 key 场景下的预期行为。
    if not should_use_llm:
        result = _validate_fallback_result(output_schema, fallback())
        record["fallback_used"] = True
        record["fallback_reason"] = "generation_mode_disabled"
        _record_invocation(record)
        return result

    # 4. 真实 LLM 路径：手动重试，便于记录每一次失败分类。
    for attempt in range(1, max_attempts + 1):
        try:
            runnable = get_coursepilot_llm().with_structured_output(
                output_schema,
                method="json_mode",
                include_raw=True,
            )
            raw_result = runnable.invoke(messages)
            parsed, raw_message = _parse_structured_result(raw_result, output_schema)
            usage = extract_token_usage(raw_message)
            _record_invocation(record)
            return parsed
        except Exception as exc:
            # 每次失败都分类并写 warning 日志。
            category = _classify_exception(exc)
            record["attempts"].append({
                "attempt": attempt,
                "status": "failed",
                "error_category": category,
                "error_message": str(exc),
            })
            logger.warning("CoursePilot LLM attempt failed ...")

    # 5. 重试耗尽后调用 deterministic fallback。
    # 注意 fallback_reason 就是最后一次失败分类。
    result = _validate_fallback_result(output_schema, fallback())
    record["fallback_used"] = True
    record["fallback_reason"] = last_category
    record["error_category"] = last_category
    _record_invocation(record)
    logger.warning("CoursePilot LLM fallback used ...")
    return result
```

为什么用 `include_raw=True`：

- `parsed` 只告诉我们最终结构化对象是否成功。
- `raw` 才能读取 usage、response metadata、finish_reason。
- `parsing_error` 可以明确区分“模型返回了内容但结构化解析失败”。

为什么 `get_coursepilot_llm()` 设置 `max_retries=0`：

```python
return ChatOpenAI(
    ...,
    timeout=settings.COURSEPILOT_LLM_TIMEOUT_SECONDS,
    max_retries=0,
)
```

因为本次在 CoursePilot 包装层自己做 retry。这样每次失败 attempt 都能被我们分类、记录和测试，而不是被 LangChain/OpenAI client 内部吞掉。

#### 4.2.6 structured result 解析

核心逻辑在 `_parse_structured_result()`：

```python
def _parse_structured_result(raw_result, output_schema):
    # include_raw=True 时，LangChain 返回 dict:
    # {"raw": ..., "parsed": ..., "parsing_error": ...}
    if not isinstance(raw_result, dict) or not {"raw", "parsed", "parsing_error"} <= set(raw_result):
        # 兼容测试替身或旧行为：如果不是 include_raw 格式，就直接尝试 Pydantic 校验。
        return _coerce_schema(output_schema, raw_result), None

    raw_message = raw_result.get("raw")
    parsed = raw_result.get("parsed")
    parsing_error = raw_result.get("parsing_error")

    # raw 为空通常对应 provider choices is None 或类似异常返回。
    if raw_message is None:
        raise CoursePilotLLMCallError(ERROR_CHOICES_NONE, ...)

    # 检查 finish_reason，如果不是 stop/end_turn/tool_calls，就认为疑似生成中断。
    interruption_reason = _generation_interruption_reason(raw_message)
    if interruption_reason:
        raise CoursePilotLLMCallError(ERROR_GENERATION_INTERRUPTED, ...)

    # LangChain structured parser 报错时归入 structured_parse_error。
    if parsing_error is not None:
        raise CoursePilotLLMCallError(ERROR_STRUCTURED_PARSE, ...)

    # parser 没报错但 parsed 是 None，也视为结构化解析失败。
    if parsed is None:
        raise CoursePilotLLMCallError(ERROR_STRUCTURED_PARSE, ...)

    # 最后一关仍然用 Pydantic model_validate，防止结构看似成功但 schema 不合格。
    return _coerce_schema(output_schema, parsed), raw_message
```

这样区分了：

- `choices_none`
- `structured_parse_error`
- `pydantic_validation_error`
- `generation_interrupted`

#### 4.2.7 usage 统计

实现：

```python
def extract_token_usage(raw_message):
    # 优先读取 LangChain 标准 usage_metadata。
    usage = getattr(raw_message, "usage_metadata", None)

    # 如果没有，再兼容 OpenAI-like response_metadata。
    if usage is None:
        response_metadata = getattr(raw_message, "response_metadata", None) or {}
        usage = response_metadata.get("token_usage") or response_metadata.get("usage")

    # provider 不返回 usage 时返回 None，不估算。
    if not usage:
        return None
```

汇总逻辑在 `summarize_llm_invocations()`：

```python
summary = {
    "call_count": len(invocations),
    "successful_call_count": 0,
    "failed_attempt_count": 0,
    "fallback_count": 0,
    "latency_ms": 0,
    "input_tokens": None,
    "output_tokens": None,
    "total_tokens": None,
    "by_prompt": {},
}
```

统计语义：

- `call_count`：`generate_structured()` 被调用几次。
- `successful_call_count`：没有 fallback 的调用次数。
- `failed_attempt_count`：所有失败 attempt 总数。
- `fallback_count`：最终走 fallback 的调用次数。
- `latency_ms`：每次调用总耗时相加。
- `by_prompt`：按 prompt_name 分组统计。

#### 4.2.8 启动健康检查

新增：

```python
def check_coursepilot_llm_health() -> None:
    if settings.COURSEPILOT_GENERATION_MODE.lower() != "llm":
        return
```

当且仅当 `COURSEPILOT_GENERATION_MODE=llm` 时执行真实 LLM health check。

健康检查会：

- 检查 `COMPATIBLE_BASE_URL`、`COMPATIBLE_MODEL`、`COMPATIBLE_API_KEY` 是否齐全。
- 用最小 schema `_HealthCheckOutput` 做一次 structured output。
- 使用同样的 `json_mode` 和 `include_raw=True`。
- 失败时按同样分类写 warning。
- 所有 attempt 失败后抛出 RuntimeError，阻止 FastAPI 启动。

### 4.3 `src/coursepilot/services/graph_config.py`

修改点：

```python
def new_workflow_config(*, namespace: str, course_id: str | None = None) -> RunnableConfig:
    thread_id = f"coursepilot-{namespace}-{uuid4()}"
    configurable = {
        "thread_id": thread_id,
        "checkpoint_ns": namespace,
    }
```

新增 metadata 和 tags：

```python
return RunnableConfig(
    configurable=configurable,
    metadata={
        "coursepilot_thread_id": thread_id,
        "coursepilot_namespace": namespace,
        "course_id": course_id,
    },
    tags=["coursepilot", f"coursepilot:{namespace}", f"thread:{thread_id}"],
)
```

动机：

- LangGraph 已经使用 `thread_id` 做线程/检查点隔离。
- 这个 id 在业务上也足够承担 trace id，因此不新增 `trace_id`。
- 把同一个 `thread_id` 同步放入 metadata 和 tags，方便日志、LangSmith/LangFuse 或其他 tracing 工具检索。

新增 helper：

```python
def workflow_thread_id(config: RunnableConfig) -> str:
    configurable = config.get("configurable", {})
    return str(configurable["thread_id"])
```

动机：

- service 层不需要知道 RunnableConfig 的内部结构。
- 后续如果 LangChain config 结构变化，只改这里。

### 4.4 `src/coursepilot/services/lesson_service.py`

主要修改位置：`LessonService.generate_lesson()` 和 `export_lesson_docx()`。

#### generate_lesson

新增流程：

```python
config = new_workflow_config(namespace="lesson", course_id=course_id)
thread_id = workflow_thread_id(config)

# graph invoke 前先写 running 记录并 commit。
# 如果 graph 启动后立刻失败，数据库里仍然能看到 thread_id。
task.intermediate_outputs_json = start_graph_invocation(
    task_outputs=task.intermediate_outputs_json,
    namespace="lesson",
    thread_id=thread_id,
)
self.session.commit()
```

执行 graph 时包一层 collector：

```python
with collect_coursepilot_llm_metadata(thread_id=thread_id) as collector:
    result = coursepilot_lesson_agent.invoke(..., config=config)
```

成功后：

```python
outputs = finish_graph_invocation(
    task_outputs=outputs,
    thread_id=thread_id,
    status="success",
)
task.intermediate_outputs_json = merge_llm_metadata(outputs, collector)
```

失败后：

```python
except Exception as exc:
    task.status = "failed"
    task.error_message = str(exc)

    outputs = finish_graph_invocation(
        task_outputs=task.intermediate_outputs_json,
        thread_id=thread_id,
        status="failed",
        error_message=str(exc),
    )

    # 如果失败发生在 collector 创建之后，也保留已发生的 LLM 调用元数据。
    if collector is not None:
        outputs = merge_llm_metadata(outputs, collector)
```

动机：

- 成功时能看到完整 LLM usage。
- 失败时也能看到 graph invoke 到哪一步、thread_id 是什么、是否已有 LLM attempt。
- 这对生产排障比只保存一个 `error_message` 有用得多。

#### export_lesson_docx

修改：

```python
file_name = readable_export_filename(
    course_name=course.course_name if course else content.course_name,
    topic=lesson.chapter,
    role="lesson_design",
    unique_id=lesson.id,
    extension="docx",
)
```

动机：

- UI 和下载文件名从随机 UUID 变成“课程名 + 章节 + 文件用途 + 短 id”。
- `ExportFile.id` 仍然是内部主键，不影响下载接口和数据库关系。

### 4.5 `src/coursepilot/services/exam_service.py`

主要覆盖：

- `create_blueprint()`
- `generate_questions()`
- `export_exam_files()`

#### create_blueprint

关键变化：

- 先创建 `GenerationTask(status="running")`。
- 再写 `graph_invocations.running`。
- 然后 invoke exam blueprint graph。

动机：

- 原来如果 blueprint graph 在创建 task 前失败，数据库里可能没有这次失败记录。
- 现在先有 task，再 invoke；失败也能落库，且包含 thread_id 和错误。

#### generate_questions

关键变化：

- 复用 blueprint 上的 `task_id`。
- 在同一个 `GenerationTask.intermediate_outputs_json` 上追加新的 `graph_invocations`。
- 这样同一个 exam 任务可以看到 blueprint 和 questions 两个阶段的 trace。

动机：

- exam workflow 天然分两段：blueprint -> confirm -> questions。
- 这两段都需要可观测性。

#### export_exam_files

修改：

```python
file_name = readable_export_filename(
    course_name=course.course_name if course else content.course_name,
    topic=content.chapter_range,
    role=role,
    unique_id=blueprint.id,
    extension=suffix.rsplit(".", 1)[-1],
)
```

生成的文件角色包括：

```text
student_exam
teacher_answer
detailed_explanation
answer_sheet
```

### 4.6 `src/coursepilot/services/ppt_service.py`

主要覆盖：

- `generate_outline()`
- `export_pptx()`

#### generate_outline

和 lesson 一样：

- invoke 前创建 config/thread_id。
- 写入 `graph_invocations.running`。
- 用 `collect_coursepilot_llm_metadata()` 收集 graph 内部 LLM 调用。
- 成功/失败都写回 task JSON。

#### export_pptx

修改：

```python
file_name = readable_export_filename(
    course_name=lesson_content.course_name,
    topic=content.chapter,
    role="ppt_outline",
    unique_id=outline.id,
    extension="pptx",
)
```

### 4.7 `src/service/service.py`

修改位置：FastAPI lifespan。

```python
if settings.COURSEPILOT_GENERATION_MODE.lower() == "llm":
    check_coursepilot_llm_health()
```

动机：

- `llm` 模式表示用户明确要求生产路径必须使用真实 LLM。
- 如果 key、base_url、model 或 structured output 能力有问题，应该启动时直接失败。
- `auto` 和 `deterministic` 模式不做启动健康检查，保持本地开发和 CI 轻量。

### 4.8 测试文件

#### `tests/coursepilot/test_llm_infra.py`

新增/增强覆盖：

- prompt hash 稳定。
- 中文输出约束进入 system prompt。
- `generate_structured()` 使用 `method="json_mode"` 和 `include_raw=True`。
- raw response 有 usage 时能汇总 token。
- timeout 重试耗尽后 fallback。
- `choices_none`、`structured_parse_error`、`pydantic_validation_error`、`generation_interrupted` 分类记录。
- deterministic 模式也记录 prompt hash 和 `generation_mode_disabled` fallback。

#### `tests/service/test_service_lifespan.py`

新增覆盖：

- `COURSEPILOT_GENERATION_MODE=deterministic` 时不调用 health check。
- `COURSEPILOT_GENERATION_MODE=llm` 时调用一次 health check。

#### `tests/coursepilot/test_lesson_api.py`

新增断言：

- lesson 导出文件名包含 `lesson_design`。
- 文件名不再是完整 UUID。

#### `tests/coursepilot/test_exam_api.py`

新增断言：

- exam 导出文件名包含 `student_exam` 等可读 role。
- 文件名不再是完整 UUID。

#### `tests/coursepilot/test_ppt_api.py`

新增断言：

- ppt 导出文件名包含 `ppt_outline`。
- invalid export 测试改为检查导出目录没有生成 `.pptx`，避免依赖旧 UUID 文件名。

#### `tests/conftest.py`

新增 pytest marker：

```python
config.addinivalue_line("markers", "llm_integration: mark test as requiring a real LLM")
```

动机：

- 让 integration test 和普通单元测试清晰区分。
- 避免 pytest 输出 unknown marker warning。

## 5. 失败和 fallback 如何变得可见

本次实现里 fallback 可见性有三层。

### 5.1 attempt warning 日志

每一次失败 attempt 都会写日志，包含：

```text
CoursePilot LLM attempt failed
prompt=...
schema=...
thread_id=...
attempt=1/3
category=timeout
error=...
```

### 5.2 retry 耗尽后的 fallback 日志

重试耗尽后会额外写一条更明确的日志：

```text
CoursePilot LLM fallback used
prompt=...
schema=...
thread_id=...
reason=timeout
attempts=3
last_error=...
```

### 5.3 task JSON 元数据

同一信息也会写入 `GenerationTask.intermediate_outputs_json["llm_invocations"]`：

```json
{
  "attempt_count": 3,
  "attempts": [
    {
      "attempt": 1,
      "status": "failed",
      "error_category": "timeout",
      "error_message": "..."
    },
    {
      "attempt": 2,
      "status": "failed",
      "error_category": "timeout",
      "error_message": "..."
    },
    {
      "attempt": 3,
      "status": "failed",
      "error_category": "timeout",
      "error_message": "..."
    }
  ],
  "fallback_used": true,
  "fallback_reason": "timeout",
  "error_category": "timeout"
}
```

这样你在本地测试时，不需要只靠猜测就能看出 fallback 是由哪类 LLM 异常触发的。

## 6. thread_id 和 trace id 的处理

本次检查后确认：现有工程里已经有 LangGraph `thread_id`。

因此实现选择是：

```text
thread_id = trace id
```

不新增单独 `trace_id` 的原因：

- `thread_id` 已用于 LangGraph 线程和 checkpoint 隔离。
- 它在每次 workflow invoke 中唯一。
- 再新增 `trace_id` 会引入两个类似概念，排障时反而容易混淆。

最终 `thread_id` 出现的位置：

- `RunnableConfig.configurable["thread_id"]`
- `RunnableConfig.metadata["coursepilot_thread_id"]`
- `RunnableConfig.tags`
- graph start/success/failure 日志
- `GenerationTask.intermediate_outputs_json["graph_invocations"]`
- 每条 LLM invocation 的 `thread_id`

## 7. 资源消耗统计示例

我用一次完整 lesson service flow 做过验证，环境里有可用的 OpenAI-compatible 配置，因此这次实际走了真实 LLM。

示例输出：

```json
{
  "call_count": 1,
  "successful_call_count": 1,
  "failed_attempt_count": 0,
  "fallback_count": 0,
  "latency_ms": 2313,
  "input_tokens": 265,
  "output_tokens": 83,
  "total_tokens": 348,
  "by_prompt": {
    "lesson/generate_lesson_design": {
      "call_count": 1,
      "successful_call_count": 1,
      "failed_attempt_count": 0,
      "fallback_count": 0,
      "latency_ms": 2313,
      "input_tokens": 265,
      "output_tokens": 83,
      "total_tokens": 348
    }
  }
}
```

同次 workflow 的 thread id 示例：

```text
coursepilot-lesson-a1ca18ad-b4cf-4bd0-8859-0013c852e77a
```

prompt hash key 示例：

```text
lesson/generate_lesson_design
```

## 8. 如何检查修改效果

### 8.1 只跑 LLM 基础设施和 workflow metadata 测试

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\coursepilot\test_llm_infra.py `
  tests\coursepilot\test_workflow_metadata.py `
  tests\coursepilot\test_llm_integration.py `
  tests\service\test_service_lifespan.py `
  -q
```

预期：

```text
16 passed, 1 skipped
```

其中 skipped 是默认跳过的真实 LLM integration test。

### 8.2 跑 CoursePilot 全量测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot -q
```

预期：

```text
59 passed, 1 skipped
```

### 8.3 跑 service 和 settings 相关测试

```powershell
.\.venv\Scripts\python.exe -m pytest tests\service -q
.\.venv\Scripts\python.exe -m pytest tests\core\test_settings.py -q
```

预期：

```text
28 passed
20 passed
```

### 8.4 跑完整回归

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

我本次验证结果：

```text
189 passed, 3 skipped, 14 warnings
```

warnings 主要来自依赖库或既有测试环境提示，不是本次断言失败。

### 8.5 运行真实 LLM integration test

默认不会运行真实 LLM 测试。要手动运行：

```powershell
$env:COURSEPILOT_RUN_LLM_INTEGRATION='1'
$env:COURSEPILOT_GENERATION_MODE='llm'
$env:MODEL='openai-compatible'
$env:COMPATIBLE_MODEL='你的聊天模型名'
$env:COMPATIBLE_BASE_URL='https://你的兼容接口/v1'
$env:COMPATIBLE_API_KEY='你的 API key'

.\.venv\Scripts\python.exe -m pytest tests\coursepilot\test_llm_integration.py -q -s
```

加 `-s` 是为了让 pytest 打印 usage summary。

预期：

- 测试不再 skip。
- 能看到 `llm_usage_summary` JSON。
- `fallback_count` 应该为 0。
- 如果 provider 不返回 token usage，则 token 字段可能是 `null`，这属于预期兼容行为。

### 8.6 检查启动健康检查

deterministic 模式不会做真实 LLM 健康检查：

```powershell
$env:COURSEPILOT_GENERATION_MODE='deterministic'
.\.venv\Scripts\python.exe src\run_service.py
```

llm 模式会在 FastAPI lifespan 启动阶段检查：

```powershell
$env:COURSEPILOT_GENERATION_MODE='llm'
$env:MODEL='openai-compatible'
$env:COMPATIBLE_MODEL='你的聊天模型名'
$env:COMPATIBLE_BASE_URL='https://你的兼容接口/v1'
$env:COMPATIBLE_API_KEY='你的 API key'

.\.venv\Scripts\python.exe src\run_service.py
```

预期日志：

```text
CoursePilot LLM health check passed model=... usage=...
```

如果配置错误或 provider 不可用，服务会启动失败，并显示：

```text
CoursePilot LLM health check failed: ...
```

### 8.7 手工检查 task JSON

完成一次 lesson/exam/ppt 生成后，可以在数据库里查看：

```sql
SELECT
  id,
  task_type,
  status,
  intermediate_outputs_json
FROM coursepilot_generation_tasks
ORDER BY created_at DESC
LIMIT 1;
```

重点检查：

```text
intermediate_outputs_json.graph_invocations
intermediate_outputs_json.prompt_hashes
intermediate_outputs_json.llm_invocations
intermediate_outputs_json.llm_usage_summary
```

### 8.8 检查导出文件名

直接跑 API 测试：

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\coursepilot\test_lesson_api.py `
  tests\coursepilot\test_exam_api.py `
  tests\coursepilot\test_ppt_api.py `
  -q
```

预期：

```text
lesson 导出文件名包含 lesson_design
exam 导出文件名包含 student_exam / teacher_answer / detailed_explanation / answer_sheet
ppt 导出文件名包含 ppt_outline
文件名不再等于完整 UUID
```

## 9. 你需要重点掌握的细节

### 9.1 fallback 不是静默降级

本次之后，fallback 必须同时满足：

- warning 日志能看到。
- `llm_invocations` 能看到。
- `fallback_reason` 能看到。
- `llm_usage_summary.fallback_count` 能统计。

这避免了“看起来生成成功，其实模型一直失败并走本地规则”的问题。

### 9.2 prompt hash 记录的是最终 system prompt

最终 system prompt 等于：

```text
prompt 文件内容 + 全局中文输出约束
```

因此只要 prompt 文件或中文 policy 变化，hash 都会变化。

### 9.3 token usage 不保证每个 provider 都有

OpenAI-compatible provider 不一定都返回同样的 usage 字段。

当前兼容：

- `raw.usage_metadata`
- `raw.response_metadata["token_usage"]`
- `raw.response_metadata["usage"]`

如果都没有：

- 单次 invocation 的 `usage` 是 `null`。
- summary 的 token 字段保持 `null`。
- 不会估算费用。

### 9.4 retry 由 CoursePilot 自己控制

`ChatOpenAI(max_retries=0)` 是有意设置。

原因：

- 如果 provider client 内部重试，我们拿不到每次失败分类。
- 手动 retry 可以把每次 attempt 都写入 metadata。
- 测试可以稳定断言第几次失败、是否 fallback。

### 9.5 exam blueprint 失败也能落库

`create_blueprint()` 现在先创建 running task，再 invoke graph。

这点很重要，因为 blueprint 是 exam 的第一步。如果第一步失败但没有 task 记录，后续排障会缺少入口。

### 9.6 可读文件名不改变内部主键

内部仍然使用 UUID：

- `ExportFile.id`
- `LessonDesign.id`
- `ExamBlueprint.id`
- `SlideOutline.id`

改的是：

- `ExportFile.file_name`
- 实际导出路径里的文件名
- API 返回里的 `file_name`

这可以提升 UI 可读性，同时不破坏数据库关系。

## 10. 本次验证情况

已经执行并通过：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\coursepilot -q
.\.venv\Scripts\python.exe -m pytest tests\service -q
.\.venv\Scripts\python.exe -m pytest tests\core\test_settings.py -q
.\.venv\Scripts\python.exe -m pytest -q
```

完整结果：

```text
189 passed, 3 skipped, 14 warnings
```

没有执行成功的检查：

```powershell
.\.venv\Scripts\ruff.exe check ...
.\.venv\Scripts\python.exe -m ruff check ...
```

原因：

```text
当前 .venv 未安装 ruff
```

这不是代码测试失败，只是格式检查工具在当前虚拟环境不可用。

## 11. 变更文件清单

新增文件：

```text
src/coursepilot/services/file_naming.py
src/coursepilot/services/workflow_tracking.py
tests/coursepilot/test_llm_integration.py
tests/coursepilot/test_workflow_metadata.py
CoursePilot_markdown_docs/CoursePilot_LLM_Trace_Fallback_Stats_Implementation_v0.2.md
```

修改文件：

```text
src/core/settings.py
src/coursepilot/llm.py
src/coursepilot/services/exam_service.py
src/coursepilot/services/graph_config.py
src/coursepilot/services/lesson_service.py
src/coursepilot/services/ppt_service.py
src/service/service.py
tests/conftest.py
tests/coursepilot/test_exam_api.py
tests/coursepilot/test_lesson_api.py
tests/coursepilot/test_llm_infra.py
tests/coursepilot/test_ppt_api.py
tests/service/test_service_lifespan.py
```

说明：

- 工作区里 `.env.example`、`README.md` 以及若干文档/资源目录本来已有未提交变更，本次说明只覆盖这次 LLM trace/fallback/statistics 相关实现。
- 本次没有新增数据库 migration。




