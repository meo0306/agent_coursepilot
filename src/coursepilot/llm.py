"""CoursePilot-specific LLM entrypoint with tracing and deterministic fallback."""

import json
import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import Any, TypeVar

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from core.settings import settings
from coursepilot.models_gateway import GatewayMode, ModelGateway
from coursepilot.prompts.loader import load_prompt
from coursepilot.token_usage import (
    USAGE_SOURCE_PROVIDER,
    estimate_token_usage,
)

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

# 固定异常分类
ERROR_CHOICES_NONE = "choices_none"
ERROR_TIMEOUT = "timeout"
ERROR_STRUCTURED_PARSE = "structured_parse_error"
ERROR_PYDANTIC_VALIDATION = "pydantic_validation_error"
ERROR_GENERATION_INTERRUPTED = "generation_interrupted"
ERROR_PROVIDER = "llm_provider_error"
ERROR_DETERMINISTIC_FALLBACK_DISABLED = "deterministic_fallback_disabled"
ERROR_UNKNOWN = "unknown_llm_error"

_LANGUAGE_POLICY = """
Language policy:
- 输出中面向教师或学生展示的主体内容必须使用中文。
- 代码、API 名称、模型名称、文件名、通用技术术语和原始引用标题可以保留英文。
- 不要因为输入材料包含英文就把主体说明写成英文。
""".strip()

# 用 ContextVar 保存 collector，可以让任何 graph node 内部的 generate_structured() 自动记录到当前 workflow。
_current_collector: ContextVar["LLMWorkflowCollector | None"] = ContextVar(
    "coursepilot_llm_workflow_collector",
    default=None,
)


class CoursePilotLLMCallError(RuntimeError):
    """
    Internal wrapper carrying a stable CoursePilot LLM error category.
    单次 LangGraph workflow 中可能有多个节点调用 LLM。
    这些调用发生在 graph 内部，service 层不能直接看到每一次调用。
    """

    def __init__(
        self,
        category: str,
        message: str,
        *,
        raw: BaseMessage | None = None,
        original: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.raw = raw
        self.original = original


@dataclass
class LLMWorkflowCollector:
    """Collect LLM metadata for one CoursePilot workflow invocation."""

    thread_id: str | None = None
    invocations: list[dict[str, Any]] = field(default_factory=list)
    prompt_hashes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def record(self, invocation: dict[str, Any]) -> None:
        self.invocations.append(invocation)
        prompt_name = str(invocation["prompt_name"])
        self.prompt_hashes[prompt_name] = {
            "prompt_name": prompt_name,
            "prompt_sha256": invocation["prompt_sha256"],
            "schema": invocation["schema"],
            "language_policy": "zh_main_content",
        }

    def to_task_metadata(self) -> dict[str, Any]:
        return {
            "prompt_hashes": self.prompt_hashes,
            "llm_invocations": self.invocations,
            "llm_usage_summary": summarize_llm_invocations(self.invocations),
        }


@contextmanager
def collect_coursepilot_llm_metadata(
    *,
    thread_id: str | None = None,
) -> Generator[LLMWorkflowCollector, None, None]:
    """Collect generate_structured metadata within a graph invocation."""
    # 每次 service 调用 graph 前创建一个 collector
    collector = LLMWorkflowCollector(thread_id=thread_id)
    # ContextVar 让 graph 内部任意 generate_structured() 都能找到当前 collector
    token = _current_collector.set(collector)
    try:
        yield collector
    finally:
        # graph invoke 结束后恢复上下文，避免串到下一次请求
        _current_collector.reset(token)


def use_coursepilot_llm() -> bool:
    """Return whether CoursePilot generation should call a real LLM."""
    mode = settings.COURSEPILOT_GENERATION_MODE.lower()
    if mode == "deterministic":
        return False
    if mode == "llm":
        _require_compatible_llm_config()
        return True
    return _has_compatible_llm_config()


@cache
def get_coursepilot_llm() -> ChatOpenAI:
    """Return the capability-aware legacy-compatible ChatOpenAI instance."""
    _require_compatible_llm_config()
    gateway = _configured_model_gateway()
    route = gateway.resolve("generator_main")
    api_key = settings.COURSEPILOT_MAIN_API_KEY or settings.COMPATIBLE_API_KEY
    parameters = dict(route.request_parameters)
    thinking = parameters.pop("thinking", None)
    parameters.pop("timeout", None)
    kwargs: dict[str, Any] = {
        "model": route.model,
        "temperature": parameters.pop("temperature"),
        "streaming": False,
        "base_url": route.base_url,
        "api_key": api_key.get_secret_value() if api_key else None,
        "timeout": settings.COURSEPILOT_LLM_TIMEOUT_SECONDS,
        "max_retries": 0,
        "max_tokens": parameters.pop("max_tokens"),
        **parameters,
    }
    if thinking is not None:
        kwargs["extra_body"] = {"thinking": thinking}
    # Keep provider retries disabled so CoursePilot can classify every failed attempt.
    return ChatOpenAI(**kwargs)


@cache
def _configured_model_gateway() -> ModelGateway:
    main_model = settings.COURSEPILOT_MAIN_MODEL or settings.COMPATIBLE_MODEL
    main_base_url = settings.COURSEPILOT_MAIN_BASE_URL or settings.COMPATIBLE_BASE_URL
    light_model = settings.COURSEPILOT_LIGHT_MODEL or main_model
    light_base_url = settings.COURSEPILOT_LIGHT_BASE_URL or main_base_url
    if main_model is None or main_base_url is None or light_model is None or light_base_url is None:
        raise ValueError("CoursePilot model gateway configuration is incomplete")
    return ModelGateway.from_files(
        profile_path=Path(settings.COURSEPILOT_MODEL_PROFILE_PATH),
        capability_path=Path(settings.COURSEPILOT_PROVIDER_CAPABILITY_PATH),
        main_config=(settings.COURSEPILOT_MAIN_PROVIDER, main_model, main_base_url),
        light_config=(settings.COURSEPILOT_LIGHT_PROVIDER, light_model, light_base_url),
        mode=GatewayMode(settings.COURSEPILOT_MODEL_GATEWAY_MODE),
    )


def generate_structured(
    *,
    prompt_name: str,
    output_schema: type[T],
    payload: dict,
    fallback: Callable[[], T],
) -> T:
    """Generate a Pydantic object through LLM structured output, with traced fallback."""
    # 准备record
    started = time.perf_counter()
    # 1. 加载 prompt，追加中文 policy，计算 prompt hash
    raw_prompt = load_prompt(prompt_name)
    system_prompt = build_coursepilot_system_prompt(raw_prompt)
    prompt_hash = hash_prompt(system_prompt)
    # 其他元数据
    mode = settings.COURSEPILOT_GENERATION_MODE.lower()
    collector = _current_collector.get()
    thread_id = collector.thread_id if collector else None
    # 2. 初始化本次调用元数据。
    record: dict[str, Any] = {
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
        "status": "running",
        "latency_ms": None,
        "usage": None,
    }
    # 3. 构造 LLM 消息，包含系统 prompt 和人类 payload。
    human_payload = {
        "input": payload,
        "schema": output_schema.model_json_schema(),
    }
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(human_payload, ensure_ascii=False, default=str)),
    ]

    # 4. 判断是否调用 LLM
    try:
        should_use_llm = use_coursepilot_llm()
    except Exception as exc:
        record.update(
            {
                "status": "failed",
                "error_category": _classify_exception(exc),
                "latency_ms": _elapsed_ms(started),
            }
        )
        _record_invocation(record)
        raise
    # 如果不使用 LLM，直接调用 fallback()，并记录 fallback_used。
    if not should_use_llm:
        if deterministic_fallback_disabled():
            record.update(
                {
                    "status": "failed",
                    "error_category": ERROR_DETERMINISTIC_FALLBACK_DISABLED,
                    "latency_ms": _elapsed_ms(started),
                }
            )
            _record_invocation(record)
            raise CoursePilotLLMCallError(
                ERROR_DETERMINISTIC_FALLBACK_DISABLED,
                "Deterministic fallback is disabled, but CoursePilot is not using a real LLM.",
            )
        result = _validate_fallback_result(output_schema, fallback())
        record.update(
            {
                "status": "fallback",
                "fallback_used": True,
                "fallback_reason": "generation_mode_disabled",
                "latency_ms": _elapsed_ms(started),
            }
        )
        _record_invocation(record)
        return result
    # 5. 循环调用 LLM，直到成功或达到最大尝试次数。
    max_attempts = _max_llm_attempts()
    last_category: str | None = None
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        attempt_started = time.perf_counter()
        try:
            runnable = get_coursepilot_llm().with_structured_output(
                output_schema,
                method="json_mode",
                # 能读取 usage、response metadata、finish_reason
                include_raw=True,
            )
            raw_result = runnable.invoke(messages)
            parsed, raw_message = _parse_structured_result(raw_result, output_schema)
            usage = resolve_token_usage(raw_message, messages)
            record["attempts"].append(
                {
                    "attempt": attempt,
                    "status": "success",
                    "latency_ms": _elapsed_ms(attempt_started),
                    "usage": usage,
                }
            )
            record.update(
                {
                    "status": "success",
                    "attempt_count": attempt,
                    "latency_ms": _elapsed_ms(started),
                    "usage": usage,
                }
            )
            _record_invocation(record)
            return parsed
        # 捕获所有异常，分类记录，并在达到最大尝试次数后使用 fallback。
        except Exception as exc:
            category = _classify_exception(exc)
            last_category = category
            last_error = exc
            raw_for_usage = exc.raw if isinstance(exc, CoursePilotLLMCallError) else None
            usage = resolve_token_usage(raw_for_usage, messages)
            attempt_record = {
                "attempt": attempt,
                "status": "failed",
                "latency_ms": _elapsed_ms(attempt_started),
                "error_category": category,
                "error_message": str(exc),
                "usage": usage,
            }
            record["attempts"].append(attempt_record)
            logger.warning(
                "CoursePilot LLM attempt failed prompt=%s schema=%s thread_id=%s "
                "attempt=%s/%s category=%s error=%s",
                prompt_name,
                output_schema.__name__,
                thread_id,
                attempt,
                max_attempts,
                category,
                exc,
            )
    if deterministic_fallback_disabled():
        record.update(
            {
                "status": "failed",
                "attempt_count": max_attempts,
                "error_category": last_category,
                "latency_ms": _elapsed_ms(started),
            }
        )
        _record_invocation(record)
        logger.warning(
            "CoursePilot LLM failed with deterministic fallback disabled prompt=%s "
            "schema=%s thread_id=%s reason=%s attempts=%s last_error=%s",
            prompt_name,
            output_schema.__name__,
            thread_id,
            last_category,
            max_attempts,
            last_error,
        )
        raise CoursePilotLLMCallError(
            last_category or ERROR_UNKNOWN,
            "CoursePilot LLM attempts failed and deterministic fallback is disabled.",
            original=last_error,
        ) from last_error
    # 重试耗尽后调用 deterministic fallback
    result = _validate_fallback_result(output_schema, fallback())
    record.update(
        {
            "status": "fallback",
            "attempt_count": max_attempts,
            "fallback_used": True,
            "fallback_reason": last_category,
            "error_category": last_category,
            "latency_ms": _elapsed_ms(started),
        }
    )
    _record_invocation(record)
    logger.warning(
        "CoursePilot LLM fallback used prompt=%s schema=%s thread_id=%s reason=%s "
        "attempts=%s last_error=%s",
        prompt_name,
        output_schema.__name__,
        thread_id,
        last_category,
        max_attempts,
        last_error,
    )
    return result


class _HealthCheckOutput(BaseModel):
    """Minimal schema for LLM health check structured output."""

    ok: bool = Field(description="Whether the health check passed.")
    message: str = Field(description="Short health check message.")


def check_coursepilot_llm_health() -> None:
    """Fail fast at service startup when forced LLM mode cannot reach the provider."""
    # 当且仅当 COURSEPILOT_GENERATION_MODE=llm 时执行真实 LLM health check
    if settings.COURSEPILOT_GENERATION_MODE.lower() != "llm":
        return
    # 检查 LLM 配置是否兼容
    _require_compatible_llm_config()
    mode = settings.COURSEPILOT_LLM_HEALTH_CHECK_MODE.lower()
    if mode == "config":
        logger.info("CoursePilot LLM health check passed mode=config")
        return
    if mode == "http":
        _check_coursepilot_llm_http_health()
        return
    if mode == "chat":
        _check_coursepilot_llm_chat_health()
        return
    raise ValueError("COURSEPILOT_LLM_HEALTH_CHECK_MODE must be one of: config, http, chat")


def _check_coursepilot_llm_http_health() -> None:
    """Probe the OpenAI-compatible models endpoint without generating tokens."""
    api_key = settings.COMPATIBLE_API_KEY
    models_url = f"{str(settings.COMPATIBLE_BASE_URL).rstrip('/')}/models"
    headers = (
        {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
        }
        if api_key
        else {}
    )
    try:
        response = httpx.get(
            models_url,
            headers=headers,
            timeout=settings.COURSEPILOT_LLM_HEALTH_CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        raise RuntimeError(
            f"CoursePilot LLM HTTP health check failed url={models_url}: {exc}"
        ) from exc

    status_code = response.status_code
    if 200 <= status_code < 300:
        logger.info(
            "CoursePilot LLM health check passed mode=http status=%s url=%s",
            status_code,
            models_url,
        )
        return
    if status_code in {404, 405, 501}:
        logger.warning(
            "CoursePilot LLM /models health endpoint unsupported status=%s url=%s; "
            "passing config-level health check",
            status_code,
            models_url,
        )
        return
    raise RuntimeError(
        f"CoursePilot LLM HTTP health check failed status={status_code} url={models_url}"
    )


def _check_coursepilot_llm_chat_health() -> None:
    """Run a minimal structured output call when explicit chat health is requested."""

    # 用最小 schema _HealthCheckOutput 做一次 structured output
    system_prompt = "You are CoursePilot's startup health check. Return JSON only."
    human_payload = {
        "input": {"task": "Return ok=true and a short Chinese message."},
        "schema": _HealthCheckOutput.model_json_schema(),
    }
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(human_payload, ensure_ascii=False)),
    ]
    max_attempts = _max_llm_attempts()
    last_error: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            runnable = get_coursepilot_llm().with_structured_output(
                _HealthCheckOutput,
                method="json_mode",
                include_raw=True,
            )
            raw_result = runnable.invoke(messages)
            parsed, raw_message = _parse_structured_result(raw_result, _HealthCheckOutput)
            if not parsed.ok:
                raise RuntimeError(parsed.message)
            logger.info(
                "CoursePilot LLM health check passed model=%s usage=%s",
                settings.COMPATIBLE_MODEL,
                resolve_token_usage(raw_message, messages),
            )
            return
        except Exception as exc:
            last_error = exc
            logger.warning(
                "CoursePilot LLM health check attempt failed attempt=%s/%s category=%s error=%s",
                attempt,
                max_attempts,
                _classify_exception(exc),
                exc,
            )
    raise RuntimeError(f"CoursePilot LLM health check failed: {last_error}") from last_error


def build_coursepilot_system_prompt(prompt: str) -> str:
    """Append CoursePilot's global language policy to a loaded prompt."""
    return f"{prompt.strip()}\n\n{_LANGUAGE_POLICY}"


def hash_prompt(prompt: str) -> str:
    return sha256(prompt.encode("utf-8")).hexdigest()


def summarize_llm_invocations(invocations: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize a list of LLM invocation records into a usage summary."""
    # 初始化 summary 结构
    summary: dict[str, Any] = {
        "call_count": len(invocations),
        "successful_call_count": 0,
        "failed_call_count": 0,
        "failed_attempt_count": 0,
        "fallback_count": 0,
        "latency_ms": 0,
        "input_tokens": None,
        "output_tokens": None,
        "total_tokens": None,
        "usage_source_counts": {},
        "by_prompt": {},
    }
    # 初始化 token 总计
    token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    saw_usage = False
    # 遍历每次调用，统计成功/失败/回退次数、延迟、token 使用量，并按 prompt 分类
    for invocation in invocations:
        prompt_name = str(invocation.get("prompt_name", "unknown"))
        prompt_stats: dict[str, Any] = summary["by_prompt"].setdefault(
            prompt_name,
            {
                "call_count": 0,
                "successful_call_count": 0,
                "failed_call_count": 0,
                "failed_attempt_count": 0,
                "fallback_count": 0,
                "latency_ms": 0,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
                "usage_source_counts": {},
            },
        )
        prompt_stats["call_count"] += 1
        latency_ms = int(invocation.get("latency_ms") or 0)
        summary["latency_ms"] += latency_ms
        prompt_stats["latency_ms"] += latency_ms
        invocation_status = invocation.get("status")
        if invocation_status == "failed":
            summary["failed_call_count"] += 1
            prompt_stats["failed_call_count"] += 1
        elif invocation.get("fallback_used"):
            summary["fallback_count"] += 1
            prompt_stats["fallback_count"] += 1
        else:
            summary["successful_call_count"] += 1
            prompt_stats["successful_call_count"] += 1

        failed_attempts = sum(
            1 for item in invocation.get("attempts", []) if item.get("status") == "failed"
        )
        summary["failed_attempt_count"] += failed_attempts
        prompt_stats["failed_attempt_count"] += failed_attempts

        usage = invocation.get("usage")
        if usage:
            source = str(usage.get("usage_source") or "unknown")
            summary["usage_source_counts"][source] = (
                summary["usage_source_counts"].get(source, 0) + 1
            )
            prompt_stats["usage_source_counts"][source] = (
                prompt_stats["usage_source_counts"].get(source, 0) + 1
            )
            if _has_token_counts(usage):
                saw_usage = True
                _add_usage(token_totals, usage)
                _add_usage_to_prompt(prompt_stats, usage)
    # 如果至少有一次调用返回了 usage，就把总计写入 summary，否则保持 None
    if saw_usage:
        summary.update(token_totals)
        for prompt_stats in summary["by_prompt"].values():
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                if prompt_stats[key] is None:
                    prompt_stats[key] = 0
    return summary


def resolve_token_usage(
    raw_message: BaseMessage | None,
    input_messages: list[BaseMessage],
) -> dict[str, Any]:
    """Return provider token usage, or estimate it from the request/response text."""
    provider_usage = extract_token_usage(raw_message)
    if provider_usage is not None:
        return provider_usage
    output_content = getattr(raw_message, "content", None) if raw_message is not None else None
    return estimate_token_usage(input_messages, output_content)


def extract_token_usage(raw_message: BaseMessage | None) -> dict[str, Any] | None:
    """Extract token usage from a raw LLM message, if available."""
    if raw_message is None:
        return None
    # 优先读取 LangChain 标准 usage_metadata
    usage = getattr(raw_message, "usage_metadata", None)
    # 如果没有，再兼容 OpenAI-like response_metadata
    if usage is None:
        response_metadata = getattr(raw_message, "response_metadata", None) or {}
        usage = response_metadata.get("token_usage") or response_metadata.get("usage")
    # provider 不返回 usage 时返回 None，不估算
    if not usage:
        return None

    input_tokens = _usage_int(usage, "input_tokens", "prompt_tokens")
    output_tokens = _usage_int(usage, "output_tokens", "completion_tokens")
    total_tokens = _usage_int(usage, "total_tokens")
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens or 0,
        "output_tokens": output_tokens or 0,
        "total_tokens": total_tokens or 0,
        "usage_source": USAGE_SOURCE_PROVIDER,
        "usage_estimated": False,
    }


def _parse_structured_result(
    raw_result: Any,
    output_schema: type[T],
) -> tuple[T, BaseMessage | None]:
    """Parse the raw result from LLM structured output into a Pydantic object."""
    # include_raw=True 时，LangChain 返回 dict:
    # {"raw": ..., "parsed": ..., "parsing_error": ...}
    if not isinstance(raw_result, dict) or not {
        "raw",
        "parsed",
        "parsing_error",
    } <= set(raw_result):
        # 兼容测试替身或旧行为：如果不是 include_raw 格式，就直接尝试 Pydantic 校验
        try:
            return _coerce_schema(output_schema, raw_result), None
        except ValidationError as exc:
            raise CoursePilotLLMCallError(
                ERROR_PYDANTIC_VALIDATION,
                str(exc),
                original=exc,
            ) from exc

    raw_message = raw_result.get("raw")
    parsed = raw_result.get("parsed")
    parsing_error = raw_result.get("parsing_error")
    # raw 为空通常对应 provider choices is None 或类似异常返回
    if raw_message is None:
        raise CoursePilotLLMCallError(
            ERROR_CHOICES_NONE,
            "LLM response did not include a raw message; provider choices may be None.",
        )
    # 检查 finish_reason，如果不是 stop/end_turn/tool_calls，就认为疑似生成中断
    interruption_reason = _generation_interruption_reason(raw_message)
    if interruption_reason:
        raise CoursePilotLLMCallError(
            ERROR_GENERATION_INTERRUPTED,
            interruption_reason,
            raw=raw_message,
        )
    # LangChain structured parser 报错时归入 structured_parse_error
    if parsing_error is not None:
        wrapped = CoursePilotLLMCallError(
            ERROR_STRUCTURED_PARSE,
            str(parsing_error),
            raw=raw_message,
            original=parsing_error if isinstance(parsing_error, BaseException) else None,
        )
        if isinstance(parsing_error, BaseException):
            raise wrapped from parsing_error
        raise wrapped
    # parser 没报错但 parsed 是 None，也视为结构化解析失败
    if parsed is None:
        raise CoursePilotLLMCallError(
            ERROR_STRUCTURED_PARSE,
            "LLM structured output parser returned None.",
            raw=raw_message,
        )
    # 用 Pydantic model_validate，防止结构看似成功但 schema 不合格
    try:
        return _coerce_schema(output_schema, parsed), raw_message
    except ValidationError as exc:
        raise CoursePilotLLMCallError(
            ERROR_PYDANTIC_VALIDATION,
            str(exc),
            raw=raw_message,
            original=exc,
        ) from exc


def _coerce_schema(output_schema: type[T], value: Any) -> T:
    """Coerce a value into the given Pydantic schema, or raise ValidationError."""
    if isinstance(value, output_schema):
        return value
    return output_schema.model_validate(value)


def _validate_fallback_result(output_schema: type[T], value: Any) -> T:
    return _coerce_schema(output_schema, value)


def _generation_interruption_reason(raw_message: BaseMessage) -> str | None:
    """Return a human-readable reason if the LLM generation was interrupted."""
    response_metadata = getattr(raw_message, "response_metadata", None) or {}
    finish_reason = (
        response_metadata.get("finish_reason")
        or response_metadata.get("stop_reason")
        or response_metadata.get("finishReason")
    )
    # 如果不是 stop/end_turn/tool_calls，就认为疑似生成中断
    if finish_reason and str(finish_reason).lower() not in {"stop", "end_turn", "tool_calls"}:
        return f"LLM generation ended with finish_reason={finish_reason}"
    return None


def _classify_exception(exc: BaseException) -> str:
    """Classify a CoursePilot LLM exception into a stable category string."""
    # 如果前面已经包装成 CoursePilotLLMCallError，直接使用内部 category
    if isinstance(exc, CoursePilotLLMCallError):
        return exc.category
    # Python 原生 TimeoutError 和消息里包含 timeout/timed out 的异常都归为 timeout
    if isinstance(exc, TimeoutError):
        return ERROR_TIMEOUT
    name = exc.__class__.__name__.lower()
    module = exc.__class__.__module__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message or "timed out" in message:
        return ERROR_TIMEOUT
    # provider 有时会把 choices is None 包在普通异常消息里
    if "choices" in message and "none" in message:
        return ERROR_CHOICES_NONE
    # Pydantic schema 校验失败单独归类，和 JSON parse 错误区分
    if isinstance(exc, ValidationError):
        return ERROR_PYDANTIC_VALIDATION
    # JSON 解析、structured parser 错误归为 structured_parse_error
    if "parsing" in name or "parse" in message or "json" in message:
        return ERROR_STRUCTURED_PARSE
    # finish_reason 异常、content_filter、incomplete 等归为生成中断
    if any(
        token in message
        for token in ["finish_reason", "interrupted", "content_filter", "incomplete"]
    ):
        return ERROR_GENERATION_INTERRUPTED
    # OpenAI-compatible provider、rate limit、API 类错误归为 provider error
    if "openai" in module or "api" in name or "rate" in name:
        return ERROR_PROVIDER
    return ERROR_UNKNOWN


def _record_invocation(invocation: dict[str, Any]) -> None:
    collector = _current_collector.get()
    if collector is not None:
        collector.record(invocation)


def deterministic_fallback_disabled() -> bool:
    return bool(settings.COURSEPILOT_DISABLE_DETERMINISTIC_FALLBACK)


def _max_llm_attempts() -> int:
    return 1 + max(0, int(settings.COURSEPILOT_LLM_MAX_RETRIES))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _usage_int(usage: Any, *keys: str) -> int | None:
    """Extract an integer token usage value from a usage dict or object, trying multiple keys."""
    for key in keys:
        value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        if value is not None:
            return int(value)
    return None


def _has_token_counts(usage: dict[str, Any]) -> bool:
    return any(
        usage.get(key) is not None for key in ("input_tokens", "output_tokens", "total_tokens")
    )


def _add_usage(total: dict[str, int], usage: dict[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        total[key] += int(usage.get(key) or 0)


def _add_usage_to_prompt(prompt_stats: dict[str, Any], usage: dict[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        prompt_stats[key] = int(prompt_stats[key] or 0) + int(usage.get(key) or 0)


def _has_compatible_llm_config() -> bool:
    return bool(
        (settings.COURSEPILOT_MAIN_BASE_URL or settings.COMPATIBLE_BASE_URL)
        and (settings.COURSEPILOT_MAIN_MODEL or settings.COMPATIBLE_MODEL)
        and (settings.COURSEPILOT_MAIN_API_KEY or settings.COMPATIBLE_API_KEY)
    )


def _require_compatible_llm_config() -> None:
    """Raise ValueError if the required LLM config is not set."""
    if not _has_compatible_llm_config():
        raise ValueError(
            "CoursePilot LLM mode requires COURSEPILOT_MAIN_* or inherited COMPATIBLE_* "
            "base URL, model and API key."
        )
