"""
Helpers for persisting CoursePilot workflow trace and LLM metadata.
统一把 graph invoke 和 LLM 调用统计写入 GenerationTask.intermediate_outputs_json
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import TracebackType
from typing import Any

from coursepilot.llm import LLMWorkflowCollector, summarize_llm_invocations

logger = logging.getLogger(__name__)


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def start_graph_invocation(
    *,
    task_outputs: dict | None,
    namespace: str,
    thread_id: str,
) -> dict[str, Any]:
    """记录 workflow graph invoke 的开始状态，返回更新后的 task_outputs"""
    # 读取历史 outputs
    outputs = dict(task_outputs or {})
    # 读取历史 invocations
    invocations = list(outputs.get("graph_invocations", []))
    # 记录运行状态
    invocations.append(
        {
            "namespace": namespace,
            "thread_id": thread_id,
            "status": "running",
            "started_at": utc_iso(),
            "finished_at": None,
            "error_message": None,
        }
    )
    outputs["graph_invocations"] = invocations
    logger.info("CoursePilot graph invoke started namespace=%s thread_id=%s", namespace, thread_id)
    return outputs


def finish_graph_invocation(
    *,
    task_outputs: dict | None,
    thread_id: str,
    status: str,
    error_message: str | None = None,
    exc_info: BaseException
    | bool
    | tuple[type[BaseException], BaseException, TracebackType | None]
    | None = None,
) -> dict[str, Any]:
    """记录 workflow graph invoke 的结束状态，返回更新后的 task_outputs"""
    outputs = dict(task_outputs or {})
    invocations = list(outputs.get("graph_invocations", []))
    # 只更新当前 thread_id 且仍处于 running 的那条记录。
    # 这样不会误改同一个 task 上其他阶段的 graph_invocations。
    for invocation in reversed(invocations):
        if invocation.get("thread_id") == thread_id and invocation.get("status") == "running":
            invocation["status"] = status
            invocation["finished_at"] = utc_iso()
            invocation["error_message"] = error_message
            break
    outputs["graph_invocations"] = invocations
    if status == "success":
        logger.info(
            "CoursePilot graph invoke finished status=%s thread_id=%s error=%s",
            status,
            thread_id,
            error_message,
        )
    else:
        logger.error(
            "CoursePilot graph invoke finished status=%s thread_id=%s error=%s",
            status,
            thread_id,
            error_message,
            exc_info=_normalize_exc_info(exc_info),
        )
    return outputs


def merge_llm_metadata(
    task_outputs: dict | None,
    collector: LLMWorkflowCollector,
) -> dict[str, Any]:
    """workflow 完成后把 LLM collector 中的数据合并进 task JSON"""
    outputs = dict(task_outputs or {})
    metadata = collector.to_task_metadata()
    # prompt hash 按 prompt_name 合并，后一次同名 prompt 会覆盖旧 hash。
    prompt_hashes = dict(outputs.get("prompt_hashes", {}))
    prompt_hashes.update(metadata["prompt_hashes"])
    outputs["prompt_hashes"] = prompt_hashes
    # llm_invocations 是调用流水，必须追加而不是覆盖。
    all_invocations = list(outputs.get("llm_invocations", [])) + metadata["llm_invocations"]
    outputs["llm_invocations"] = all_invocations
    # summary 使用同一个 task 的全部 llm_invocations 重新计算，覆盖 exam 等多阶段流程。
    cumulative_summary = summarize_llm_invocations(all_invocations)
    outputs["llm_usage_summary"] = cumulative_summary

    logger.info(
        "CoursePilot LLM usage summary thread_id=%s summary=%s cumulative_summary=%s",
        collector.thread_id,
        metadata["llm_usage_summary"],
        cumulative_summary,
    )
    return outputs


def _normalize_exc_info(
    exc_info: BaseException
    | bool
    | tuple[type[BaseException], BaseException, TracebackType | None]
    | None,
) -> bool | tuple[type[BaseException], BaseException, TracebackType | None]:
    if isinstance(exc_info, BaseException):
        return (type(exc_info), exc_info, exc_info.__traceback__)
    if exc_info is None:
        return False
    return exc_info
