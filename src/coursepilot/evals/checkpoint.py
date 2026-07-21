from __future__ import annotations

import hashlib
import json
import os
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

CHECKPOINT_SCHEMA_VERSION = 1
ATOMIC_REPLACE_MAX_ATTEMPTS = 10
ATOMIC_REPLACE_BASE_DELAY_SECONDS = 0.025
ATOMIC_REPLACE_MAX_DELAY_SECONDS = 0.5


def utc_iso() -> str:
    return datetime.now(UTC).isoformat()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def _replace_with_retry(source: Path, destination: Path) -> None:
    """Handle transient Windows reader/antivirus locks without losing atomicity."""
    for attempt in range(ATOMIC_REPLACE_MAX_ATTEMPTS):
        try:
            os.replace(source, destination)
            return
        except PermissionError:
            if attempt + 1 >= ATOMIC_REPLACE_MAX_ATTEMPTS:
                raise
            delay = min(
                ATOMIC_REPLACE_BASE_DELAY_SECONDS * (2**attempt),
                ATOMIC_REPLACE_MAX_DELAY_SECONDS,
            )
            time.sleep(delay)


class EvalCheckpointRunner:
    def __init__(
        self,
        *,
        checkpoint_path: Path,
        output_path: Path,
        fingerprint: str,
        metadata: dict[str, Any],
        resume: bool = False,
        force_resume: bool = False,
        overwrite: bool = False,
    ) -> None:
        self.checkpoint_path = checkpoint_path
        self.output_path = output_path
        self.resume = resume
        if resume:
            self.state = self._load_checkpoint()
            saved_fingerprint = self.state.get("fingerprint")
            if saved_fingerprint != fingerprint and not force_resume:
                raise ValueError(
                    "Evaluation checkpoint does not match the current configuration or sample "
                    "files. Use --force-resume only after reviewing the differences."
                )
            if saved_fingerprint != fingerprint:
                self.state.setdefault("resume_warnings", []).append(
                    {
                        "at": utc_iso(),
                        "message": "Fingerprint mismatch was overridden with --force-resume.",
                        "previous_fingerprint": saved_fingerprint,
                        "current_fingerprint": fingerprint,
                    }
                )
            self.state["status"] = "running"
            self.state["current_fingerprint"] = fingerprint
            self.state["resumed_at"] = utc_iso()
        else:
            if self.checkpoint_path.exists() and not overwrite:
                raise FileExistsError(
                    f"Evaluation checkpoint already exists: {self.checkpoint_path}. "
                    "Use --resume to continue it or --overwrite-checkpoint to start over."
                )
            self.state = {
                "schema_version": CHECKPOINT_SCHEMA_VERSION,
                "run_id": f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}",
                "status": "running",
                "started_at": utc_iso(),
                "updated_at": utc_iso(),
                "completed_at": None,
                "fingerprint": fingerprint,
                "metadata": metadata,
                "context": {},
                "steps": {},
                "error": None,
            }
        self._persist_partial()

    @property
    def run_id(self) -> str:
        return str(self.state["run_id"])

    def idempotency_key(self, step_id: str) -> str:
        step_digest = hashlib.sha256(step_id.encode("utf-8")).hexdigest()[:32]
        return f"coursepilot-eval:{self.run_id}:{step_digest}"

    @property
    def total_step_latency_ms(self) -> int:
        return sum(
            int(step.get("latency_ms") or 0)
            for step in self.state.get("steps", {}).values()
            if step.get("status") == "succeeded"
        )

    def call(
        self,
        step_id: str,
        display_name: str,
        fn: Callable[[], Any],
    ) -> dict[str, Any]:
        existing = self.state["steps"].get(step_id)
        if self.resume and existing and existing.get("status") == "succeeded":
            print(f"[resume] skipped succeeded step: {display_name}")
            return dict(existing["result"])

        attempt = int((existing or {}).get("attempt") or 0) + 1
        history = list((existing or {}).get("history", []))
        if existing and existing.get("status") != "succeeded":
            history.append(
                {
                    key: existing.get(key)
                    for key in (
                        "attempt",
                        "status",
                        "started_at",
                        "finished_at",
                        "latency_ms",
                        "error",
                    )
                }
            )
        step = {
            "id": step_id,
            "name": display_name,
            "status": "running",
            "attempt": attempt,
            "started_at": utc_iso(),
            "finished_at": None,
            "latency_ms": None,
            "result": None,
            "error": None,
            "history": history,
        }
        self.state["steps"][step_id] = step
        self.state["status"] = "running"
        self.state["current_step"] = step_id
        self._persist_partial()

        started = time.perf_counter()
        try:
            result = fn()
        except BaseException as exc:
            step["status"] = "failed"
            step["finished_at"] = utc_iso()
            step["latency_ms"] = _elapsed_ms(started)
            step["error"] = _error_payload(exc)
            self.state["status"] = "failed"
            self.state["error"] = step["error"]
            self.state.pop("current_step", None)
            self._persist_partial()
            raise

        wrapped_result = {
            "name": display_name,
            "latency_ms": _elapsed_ms(started),
            "result": result,
        }
        step["status"] = "succeeded"
        step["finished_at"] = utc_iso()
        step["latency_ms"] = wrapped_result["latency_ms"]
        step["result"] = wrapped_result
        self.state["error"] = None
        self.state.pop("current_step", None)
        self._persist_partial()
        return wrapped_result

    def update_context(self, **values: Any) -> None:
        self.state["context"].update(values)
        self._persist_partial()

    def fail(self, exc: BaseException) -> None:
        self.state["status"] = "failed"
        self.state["error"] = _error_payload(exc)
        self.state.pop("current_step", None)
        self._persist_partial()

    def complete(self, report: dict[str, Any], *, status: str = "completed") -> None:
        self.state["status"] = status
        self.state["completed_at"] = utc_iso()
        self.state["error"] = None
        self.state.pop("current_step", None)
        self._persist_checkpoint()
        report["run"] = {
            "run_id": self.run_id,
            "status": status,
            "checkpoint_path": str(self.checkpoint_path),
            "resumed": self.resume,
        }
        report["steps"] = self.state["steps"]
        atomic_write_json(self.output_path, report)

    def _load_checkpoint(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            raise FileNotFoundError(f"Evaluation checkpoint not found: {self.checkpoint_path}")
        state = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if state.get("schema_version") != CHECKPOINT_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported checkpoint schema version: {state.get('schema_version')}"
            )
        return state

    def _persist_partial(self) -> None:
        self._persist_checkpoint()
        partial_report = {
            "generated_at": utc_iso(),
            "partial": True,
            "run": {
                "run_id": self.run_id,
                "status": self.state["status"],
                "checkpoint_path": str(self.checkpoint_path),
                "resumed": self.resume,
            },
            "metadata": self.state.get("metadata", {}),
            "context": self.state.get("context", {}),
            "steps": self.state.get("steps", {}),
            "error": self.state.get("error"),
        }
        atomic_write_json(self.output_path, partial_report)

    def _persist_checkpoint(self) -> None:
        self.state["updated_at"] = utc_iso()
        atomic_write_json(self.checkpoint_path, self.state)


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _error_payload(exc: BaseException) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc(),
    }
