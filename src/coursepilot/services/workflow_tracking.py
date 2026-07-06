"""Helpers for persisting CoursePilot workflow trace and LLM metadata."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from coursepilot.llm import LLMWorkflowCollector

logger = logging.getLogger(__name__)


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def start_graph_invocation(
    *,
    task_outputs: dict | None,
    namespace: str,
    thread_id: str,
) -> dict[str, Any]:
    outputs = dict(task_outputs or {})
    invocations = list(outputs.get("graph_invocations", []))
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
) -> dict[str, Any]:
    outputs = dict(task_outputs or {})
    invocations = list(outputs.get("graph_invocations", []))
    for invocation in reversed(invocations):
        if invocation.get("thread_id") == thread_id and invocation.get("status") == "running":
            invocation["status"] = status
            invocation["finished_at"] = utc_iso()
            invocation["error_message"] = error_message
            break
    outputs["graph_invocations"] = invocations
    log_method = logger.info if status == "success" else logger.error
    log_method(
        "CoursePilot graph invoke finished status=%s thread_id=%s error=%s",
        status,
        thread_id,
        error_message,
    )
    return outputs


def merge_llm_metadata(
    task_outputs: dict | None,
    collector: LLMWorkflowCollector,
) -> dict[str, Any]:
    outputs = dict(task_outputs or {})
    metadata = collector.to_task_metadata()
    prompt_hashes = dict(outputs.get("prompt_hashes", {}))
    prompt_hashes.update(metadata["prompt_hashes"])
    outputs["prompt_hashes"] = prompt_hashes
    outputs["llm_invocations"] = list(outputs.get("llm_invocations", [])) + metadata[
        "llm_invocations"
    ]
    outputs["llm_usage_summary"] = metadata["llm_usage_summary"]
    logger.info(
        "CoursePilot LLM usage summary thread_id=%s summary=%s",
        collector.thread_id,
        metadata["llm_usage_summary"],
    )
    return outputs
