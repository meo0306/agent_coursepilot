"""
CoursePilot 的 HTTP 客户端封装，提供统一的请求方法和错误处理。
"""

import time
from typing import Any

import httpx

from client.client import AgentClientError


class CoursePilotClient:
    """Client wrapper for `/api/coursepilot/*` product endpoints."""

    def __init__(
        self,
        base_url: str = "http://0.0.0.0",
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        trust_env: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout
        self.trust_env = trust_env

    def create_course(
        self,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request("POST", "/courses", json=payload, idempotency_key=idempotency_key)

    def list_courses(self) -> list[dict[str, Any]]:
        return self._request("GET", "/courses")

    def list_documents(self, course_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/courses/{course_id}/documents")

    def upload_document(
        self,
        course_id: str,
        *,
        filename: str,
        content: bytes,
        source_type: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/courses/{course_id}/documents/upload",
            files={"file": (filename, content)},
            data={"source_type": source_type},
            timeout=120,
        )

    def build_kb(
        self,
        document_id: str,
        *,
        timeout: float = 300,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        accepted = self.enqueue_build_kb(
            document_id,
            idempotency_key=idempotency_key,
        )
        return self.wait_for_task(accepted["task_id"], timeout=timeout)

    def enqueue_build_kb(
        self,
        document_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/documents/{document_id}/build-kb",
            timeout=30,
            idempotency_key=idempotency_key,
        )

    def search_kb(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/courses/{course_id}/kb/search", json=payload, timeout=60)

    def generate_lesson(
        self,
        course_id: str,
        payload: dict[str, Any],
        *,
        timeout: float = 180,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        accepted = self.enqueue_lesson(
            course_id,
            payload,
            idempotency_key=idempotency_key,
        )
        return self.wait_for_task(accepted["task_id"], timeout=timeout)

    def enqueue_lesson(
        self,
        course_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/courses/{course_id}/lessons/generate",
            json=payload,
            timeout=30,
            idempotency_key=idempotency_key,
        )

    def revise_lesson(self, lesson_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/lessons/{lesson_id}/revise", json=payload, timeout=180)

    def export_lesson(self, lesson_id: str) -> dict[str, Any]:
        return self._request("POST", f"/lessons/{lesson_id}/export", timeout=120)

    def create_exam_blueprint(
        self,
        course_id: str,
        payload: dict[str, Any],
        *,
        timeout: float = 180,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        accepted = self.enqueue_exam_blueprint(
            course_id,
            payload,
            idempotency_key=idempotency_key,
        )
        return self.wait_for_task(accepted["task_id"], timeout=timeout)

    def enqueue_exam_blueprint(
        self,
        course_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/courses/{course_id}/exams/blueprint",
            json=payload,
            timeout=30,
            idempotency_key=idempotency_key,
        )

    def confirm_exam_blueprint(self, blueprint_id: str) -> dict[str, Any]:
        return self._request("POST", f"/exams/{blueprint_id}/confirm")

    def generate_questions(
        self,
        blueprint_id: str,
        *,
        timeout: float = 240,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        accepted = self.enqueue_questions(
            blueprint_id,
            idempotency_key=idempotency_key,
        )
        return self.wait_for_task(accepted["task_id"], timeout=timeout)

    def enqueue_questions(
        self,
        blueprint_id: str,
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/exams/{blueprint_id}/generate",
            timeout=30,
            idempotency_key=idempotency_key,
        )

    def list_questions(self, blueprint_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/exams/{blueprint_id}/questions")

    def export_exam(self, blueprint_id: str) -> dict[str, Any]:
        return self._request("POST", f"/exams/{blueprint_id}/export", timeout=120)

    def generate_ppt_outline(
        self,
        lesson_id: str,
        payload: dict[str, Any],
        *,
        timeout: float = 180,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        accepted = self.enqueue_ppt_outline(
            lesson_id,
            payload,
            idempotency_key=idempotency_key,
        )
        return self.wait_for_task(accepted["task_id"], timeout=timeout)

    def enqueue_ppt_outline(
        self,
        lesson_id: str,
        payload: dict[str, Any],
        *,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/lessons/{lesson_id}/ppt/generate",
            json=payload,
            timeout=30,
            idempotency_key=idempotency_key,
        )

    def get_task(self, task_id: str, *, timeout: float = 30) -> dict[str, Any]:
        return self._request("GET", f"/tasks/{task_id}", timeout=timeout)

    def wait_for_task(
        self,
        task_id: str,
        *,
        timeout: float,
        poll_interval: float = 1.0,
    ) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AgentClientError(f"CoursePilot task timed out after {timeout:g}s: {task_id}")
            task = self.get_task(task_id, timeout=min(30, remaining))
            task_status = str(task.get("status", ""))
            if task_status in {"completed", "needs_review"}:
                result = task.get("result")
                if not isinstance(result, dict):
                    raise AgentClientError(
                        f"CoursePilot task completed without a result: {task_id}"
                    )
                return result
            if task_status == "failed":
                detail = task.get("error_message") or "unknown task error"
                raise AgentClientError(f"CoursePilot task failed: {task_id} - {detail}")
            time.sleep(min(poll_interval, max(0.0, remaining)))

    def export_ppt(self, outline_id: str) -> dict[str, Any]:
        return self._request("POST", f"/ppt/{outline_id}/export", timeout=120)

    def create_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/reviews", json=payload)

    def write_back_review(self, review_id: str) -> dict[str, Any]:
        return self._request("POST", f"/reviews/{review_id}/write-back", timeout=120)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """发送请求并处理响应，统一错误处理"""
        timeout = kwargs.pop("timeout", self.timeout)
        idempotency_key = kwargs.pop("idempotency_key", None)
        request_headers = {**self.headers, **kwargs.pop("headers", {})}
        if idempotency_key is not None:
            request_headers["Idempotency-Key"] = idempotency_key
        try:
            # 发送 HTTP 请求
            response = httpx.request(
                method,
                f"{self.base_url}/api/coursepilot{path}",
                headers=request_headers,
                timeout=timeout,
                trust_env=self.trust_env,
                **kwargs,
            )
            # 检查响应状态码，非 2xx 抛出异常
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = _response_detail(exc.response)
            message = f"CoursePilot API error: {exc}"
            if detail:
                message = f"{message} - {detail}"
            raise AgentClientError(message) from exc
        except httpx.HTTPError as exc:
            raise AgentClientError(f"CoursePilot API error: {exc}") from exc
        return response.json()


def _response_detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return response.text or None
    if isinstance(payload, dict):
        detail = payload.get("detail")
        return str(detail) if detail is not None else None
    return None
