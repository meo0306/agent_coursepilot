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
from typing import Any, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field, ValidationError

from core.settings import settings
from coursepilot.prompts.loader import load_prompt

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

ERROR_CHOICES_NONE = "choices_none"
ERROR_TIMEOUT = "timeout"
ERROR_STRUCTURED_PARSE = "structured_parse_error"
ERROR_PYDANTIC_VALIDATION = "pydantic_validation_error"
ERROR_GENERATION_INTERRUPTED = "generation_interrupted"
ERROR_PROVIDER = "llm_provider_error"
ERROR_UNKNOWN = "unknown_llm_error"

_LANGUAGE_POLICY = """
Language policy:
- 输出中面向教师或学生展示的主体内容必须使用中文。
- 代码、API 名称、模型名称、文件名、通用技术术语和原始引用标题可以保留英文。
- 不要因为输入材料包含英文就把主体说明写成英文。
""".strip()

_current_collector: ContextVar["LLMWorkflowCollector | None"] = ContextVar(
    "coursepilot_llm_workflow_collector",
    default=None,
)


class CoursePilotLLMCallError(RuntimeError):
    """Internal wrapper carrying a stable CoursePilot LLM error category."""

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
    collector = LLMWorkflowCollector(thread_id=thread_id)
    token = _current_collector.set(collector)
    try:
        yield collector
    finally:
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
    """Return the cached OpenAI-compatible ChatOpenAI instance for CoursePilot."""
    _require_compatible_llm_config()
    api_key = settings.COMPATIBLE_API_KEY
    return ChatOpenAI(
        model=settings.COMPATIBLE_MODEL,
        temperature=0.2,
        streaming=False,
        base_url=settings.COMPATIBLE_BASE_URL,
        api_key=api_key.get_secret_value() if api_key else None,
        timeout=settings.COURSEPILOT_LLM_TIMEOUT_SECONDS,
        max_retries=0,
        reasoning_effort="high",
        extra_body={"thinking": {"type": "enabled"}},
    )


def generate_structured(
    *,
    prompt_name: str,
    output_schema: type[T],
    payload: dict,
    fallback: Callable[[], T],
) -> T:
    """Generate a Pydantic object through LLM structured output, with traced fallback."""
    started = time.perf_counter()
    raw_prompt = load_prompt(prompt_name)
    system_prompt = build_coursepilot_system_prompt(raw_prompt)
    prompt_hash = hash_prompt(system_prompt)
    mode = settings.COURSEPILOT_GENERATION_MODE.lower()
    collector = _current_collector.get()
    thread_id = collector.thread_id if collector else None
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
        "latency_ms": None,
        "usage": None,
    }

    human_payload = {
        "input": payload,
        "schema": output_schema.model_json_schema(),
    }
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=json.dumps(human_payload, ensure_ascii=False, default=str)),
    ]

    try:
        should_use_llm = use_coursepilot_llm()
    except Exception:
        record["latency_ms"] = _elapsed_ms(started)
        _record_invocation(record)
        raise

    if not should_use_llm:
        result = _validate_fallback_result(output_schema, fallback())
        record.update(
            {
                "fallback_used": True,
                "fallback_reason": "generation_mode_disabled",
                "latency_ms": _elapsed_ms(started),
            }
        )
        _record_invocation(record)
        return result

    max_attempts = _max_llm_attempts()
    last_category: str | None = None
    last_error: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        attempt_started = time.perf_counter()
        try:
            runnable = get_coursepilot_llm().with_structured_output(
                output_schema,
                method="json_mode",
                include_raw=True,
            )
            raw_result = runnable.invoke(messages)
            parsed, raw_message = _parse_structured_result(raw_result, output_schema)
            usage = extract_token_usage(raw_message)
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
                    "attempt_count": attempt,
                    "latency_ms": _elapsed_ms(started),
                    "usage": usage,
                }
            )
            _record_invocation(record)
            return parsed
        except Exception as exc:
            category = _classify_exception(exc)
            last_category = category
            last_error = exc
            usage = (
                extract_token_usage(exc.raw)
                if isinstance(exc, CoursePilotLLMCallError)
                else None
            )
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

    result = _validate_fallback_result(output_schema, fallback())
    record.update(
        {
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
    ok: bool = Field(description="Whether the health check passed.")
    message: str = Field(description="Short health check message.")


def check_coursepilot_llm_health() -> None:
    """Fail fast at service startup when forced LLM mode cannot call the provider."""
    if settings.COURSEPILOT_GENERATION_MODE.lower() != "llm":
        return

    _require_compatible_llm_config()
    system_prompt = build_coursepilot_system_prompt(
        "You are CoursePilot's startup health check. Return JSON only."
    )
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
                extract_token_usage(raw_message),
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
    token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    saw_usage = False

    for invocation in invocations:
        prompt_name = str(invocation.get("prompt_name", "unknown"))
        prompt_stats = summary["by_prompt"].setdefault(
            prompt_name,
            {
                "call_count": 0,
                "successful_call_count": 0,
                "failed_attempt_count": 0,
                "fallback_count": 0,
                "latency_ms": 0,
                "input_tokens": None,
                "output_tokens": None,
                "total_tokens": None,
            },
        )
        prompt_stats["call_count"] += 1
        latency_ms = int(invocation.get("latency_ms") or 0)
        summary["latency_ms"] += latency_ms
        prompt_stats["latency_ms"] += latency_ms
        if invocation.get("fallback_used"):
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
            saw_usage = True
            _add_usage(token_totals, usage)
            _add_usage_to_prompt(prompt_stats, usage)

    if saw_usage:
        summary.update(token_totals)
        for prompt_stats in summary["by_prompt"].values():
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                if prompt_stats[key] is None:
                    prompt_stats[key] = 0
    return summary


def extract_token_usage(raw_message: BaseMessage | None) -> dict[str, int] | None:
    if raw_message is None:
        return None
    usage = getattr(raw_message, "usage_metadata", None)
    if usage is None:
        response_metadata = getattr(raw_message, "response_metadata", None) or {}
        usage = response_metadata.get("token_usage") or response_metadata.get("usage")
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
    }


def _parse_structured_result(
    raw_result: Any,
    output_schema: type[T],
) -> tuple[T, BaseMessage | None]:
    if not isinstance(raw_result, dict) or not {
        "raw",
        "parsed",
        "parsing_error",
    } <= set(raw_result):
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
    if raw_message is None:
        raise CoursePilotLLMCallError(
            ERROR_CHOICES_NONE,
            "LLM response did not include a raw message; provider choices may be None.",
        )
    interruption_reason = _generation_interruption_reason(raw_message)
    if interruption_reason:
        raise CoursePilotLLMCallError(
            ERROR_GENERATION_INTERRUPTED,
            interruption_reason,
            raw=raw_message,
        )
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
    if parsed is None:
        raise CoursePilotLLMCallError(
            ERROR_STRUCTURED_PARSE,
            "LLM structured output parser returned None.",
            raw=raw_message,
        )
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
    if isinstance(value, output_schema):
        return value
    return output_schema.model_validate(value)


def _validate_fallback_result(output_schema: type[T], value: Any) -> T:
    return _coerce_schema(output_schema, value)


def _generation_interruption_reason(raw_message: BaseMessage) -> str | None:
    response_metadata = getattr(raw_message, "response_metadata", None) or {}
    finish_reason = (
        response_metadata.get("finish_reason")
        or response_metadata.get("stop_reason")
        or response_metadata.get("finishReason")
    )
    if finish_reason and str(finish_reason).lower() not in {"stop", "end_turn", "tool_calls"}:
        return f"LLM generation ended with finish_reason={finish_reason}"
    return None


def _classify_exception(exc: BaseException) -> str:
    if isinstance(exc, CoursePilotLLMCallError):
        return exc.category
    if isinstance(exc, TimeoutError):
        return ERROR_TIMEOUT
    name = exc.__class__.__name__.lower()
    module = exc.__class__.__module__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message or "timed out" in message:
        return ERROR_TIMEOUT
    if "choices" in message and "none" in message:
        return ERROR_CHOICES_NONE
    if isinstance(exc, ValidationError):
        return ERROR_PYDANTIC_VALIDATION
    if "parsing" in name or "parse" in message or "json" in message:
        return ERROR_STRUCTURED_PARSE
    if any(
        token in message
        for token in ["finish_reason", "interrupted", "content_filter", "incomplete"]
    ):
        return ERROR_GENERATION_INTERRUPTED
    if "openai" in module or "api" in name or "rate" in name:
        return ERROR_PROVIDER
    return ERROR_UNKNOWN


def _record_invocation(invocation: dict[str, Any]) -> None:
    collector = _current_collector.get()
    if collector is not None:
        collector.record(invocation)


def _max_llm_attempts() -> int:
    return 1 + max(0, int(settings.COURSEPILOT_LLM_MAX_RETRIES))


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _usage_int(usage: Any, *keys: str) -> int | None:
    for key in keys:
        value = usage.get(key) if isinstance(usage, dict) else getattr(usage, key, None)
        if value is not None:
            return int(value)
    return None


def _add_usage(total: dict[str, int], usage: dict[str, int]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        total[key] += int(usage.get(key) or 0)


def _add_usage_to_prompt(prompt_stats: dict[str, Any], usage: dict[str, int]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        prompt_stats[key] = int(prompt_stats[key] or 0) + int(usage.get(key) or 0)


def _has_compatible_llm_config() -> bool:
    return bool(
        settings.COMPATIBLE_BASE_URL
        and settings.COMPATIBLE_MODEL
        and settings.COMPATIBLE_API_KEY
    )


def _require_compatible_llm_config() -> None:
    if not _has_compatible_llm_config():
        raise ValueError(
            "CoursePilot LLM mode requires COMPATIBLE_BASE_URL, COMPATIBLE_MODEL, "
            "and COMPATIBLE_API_KEY."
        )
