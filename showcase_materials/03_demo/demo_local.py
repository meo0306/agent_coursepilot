"""Run the deterministic local CoursePilot -> CourseRAG portfolio journey."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from typing import Any


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    merged = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        merged["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=merged, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: HTTP {exc.code}: {detail}") from exc


def wait_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return request_json("GET", url, timeout=3)
        except Exception as exc:  # service startup polling
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Service did not become ready: {url}: {last_error}")


def run(*, base_url: str, timeout_seconds: float) -> dict[str, Any]:
    base = base_url.rstrip("/")
    health = wait_json(f"{base}/health", timeout_seconds=timeout_seconds)
    course = request_json(
        "POST",
        f"{base}/api/coursepilot/courses",
        payload={
            "course_name": "Evidence-driven AI Course (Portfolio Demo)",
            "course_type": "portfolio_demo",
            "student_level": "undergraduate",
            "description": "Deterministic local demo; no paid provider or private textbook.",
        },
        headers={"Idempotency-Key": "portfolio-demo-course-v1"},
    )
    accepted = request_json(
        "POST",
        f"{base}/api/coursepilot/courses/{course['id']}/lessons/generate",
        payload={
            "chapter_range": "Evidence-first lesson planning",
            "total_sessions": 1,
            "session_duration": 45,
            "teaching_template": "standard",
        },
        headers={"Idempotency-Key": "portfolio-demo-lesson-v1"},
    )
    deadline = time.monotonic() + timeout_seconds
    task: dict[str, Any] = {}
    while time.monotonic() < deadline:
        task = request_json("GET", f"{base}{accepted['status_url']}")
        if task["status"] in {"completed", "needs_review", "failed"}:
            break
        time.sleep(1)
    if task.get("status") not in {"completed", "needs_review"}:
        raise RuntimeError(f"Demo lesson task did not complete: {task}")
    result = task.get("result") or {}
    return {
        "coursepilot_health": health,
        "course_id": course["id"],
        "task_id": task["task_id"],
        "task_status": task["status"],
        "lesson_id": result.get("lesson_id"),
        "remote_courserag_mode": True,
        "paid_provider_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    print(json.dumps(run(base_url=args.base_url, timeout_seconds=args.timeout_seconds), indent=2))


if __name__ == "__main__":
    main()
