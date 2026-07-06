"""
CoursePilot 的 HTTP 客户端封装，提供统一的请求方法和错误处理。
"""
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
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.timeout = timeout

    def create_course(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/courses", json=payload)

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

    def build_kb(self, document_id: str) -> dict[str, Any]:
        return self._request("POST", f"/documents/{document_id}/build-kb", timeout=300)

    def search_kb(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/courses/{course_id}/kb/search", json=payload, timeout=60)

    def generate_lesson(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/courses/{course_id}/lessons/generate", json=payload, timeout=180)

    def revise_lesson(self, lesson_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/lessons/{lesson_id}/revise", json=payload, timeout=180)

    def export_lesson(self, lesson_id: str) -> dict[str, Any]:
        return self._request("POST", f"/lessons/{lesson_id}/export", timeout=120)

    def create_exam_blueprint(self, course_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/courses/{course_id}/exams/blueprint", json=payload, timeout=180)

    def confirm_exam_blueprint(self, blueprint_id: str) -> dict[str, Any]:
        return self._request("POST", f"/exams/{blueprint_id}/confirm")

    def generate_questions(self, blueprint_id: str) -> dict[str, Any]:
        return self._request("POST", f"/exams/{blueprint_id}/generate", timeout=240)

    def list_questions(self, blueprint_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/exams/{blueprint_id}/questions")

    def export_exam(self, blueprint_id: str) -> dict[str, Any]:
        return self._request("POST", f"/exams/{blueprint_id}/export", timeout=120)

    def generate_ppt_outline(self, lesson_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", f"/lessons/{lesson_id}/ppt/generate", json=payload, timeout=180)

    def export_ppt(self, outline_id: str) -> dict[str, Any]:
        return self._request("POST", f"/ppt/{outline_id}/export", timeout=120)

    def create_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/reviews", json=payload)

    def write_back_review(self, review_id: str) -> dict[str, Any]:
        return self._request("POST", f"/reviews/{review_id}/write-back", timeout=120)

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """发送请求并处理响应，统一错误处理"""
        timeout = kwargs.pop("timeout", self.timeout)
        try:
            # 发送 HTTP 请求
            response = httpx.request(
                method,
                f"{self.base_url}/api/coursepilot{path}",
                headers=self.headers,
                timeout=timeout,
                **kwargs,
            )
            # 检查响应状态码，非 2xx 抛出异常
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentClientError(f"CoursePilot API error: {exc}") from exc
        return response.json()

