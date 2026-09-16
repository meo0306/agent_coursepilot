from __future__ import annotations

import hashlib
import json

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr


class RewriteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rewrites: tuple[str, ...] = Field(max_length=3)


class OpenAICompatibleRewriteProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: SecretStr,
        model: str,
        supports_thinking_toggle: bool,
        timeout_seconds: float = 120,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.supports_thinking_toggle = supports_thinking_toggle
        self.timeout_seconds = timeout_seconds
        self.client = client or httpx.Client(timeout=timeout_seconds)
        self.total_tokens = 0
        self.response_hashes: list[str] = []

    def rewrite(self, query: str, *, max_rewrites: int) -> tuple[str, ...]:
        payload: dict[str, object] = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 300,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return JSON {rewrites:[...]}. Produce at most three retrieval rewrites. "
                        "Preserve explicit filters and technical terms; do not answer the question."
                    ),
                },
                {"role": "user", "content": query},
            ],
        }
        if self.supports_thinking_toggle:
            payload["thinking"] = {"type": "disabled"}
        response = self.client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key.get_secret_value()}"},
            json=payload,
        )
        response.raise_for_status()
        self.response_hashes.append(hashlib.sha256(response.content).hexdigest())
        body = response.json()
        content = body["choices"][0]["message"]["content"]
        parsed = RewriteResponse.model_validate_json(content)
        usage = body.get("usage") or {}
        self.total_tokens += int(usage.get("total_tokens", 0))
        return tuple(parsed.rewrites[:max_rewrites])


def rewrite_cache_key(query: str, *, model: str, profile_sha256: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {"query": query, "model": model, "profile_sha256": profile_sha256},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
