import json
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import httpx

from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    ServiceMetadata,
    StreamInput,
    UserInput,
)


class AgentClientError(Exception):
    pass


class AgentClient:
    """Minimal client for CoursePilot prompt-entry agent endpoints."""

    def __init__(
        self,
        base_url: str = "http://0.0.0.0",
        agent: str | None = None,
        timeout: float | None = None,
        get_info: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_secret = os.getenv("AUTH_SECRET")
        self.timeout = timeout
        self.info: ServiceMetadata | None = None
        self.agent: str | None = None
        if get_info:
            self.retrieve_info()
        if agent:
            self.update_agent(agent)

    @property
    def _headers(self) -> dict[str, str]:
        if not self.auth_secret:
            return {}
        return {"Authorization": f"Bearer {self.auth_secret}"}

    def retrieve_info(self) -> None:
        try:
            response = httpx.get(
                f"{self.base_url}/info",
                headers=self._headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentClientError(f"Error getting service info: {exc}") from exc

        self.info = ServiceMetadata.model_validate(response.json())
        if not self.agent or self.agent not in [agent.key for agent in self.info.agents]:
            self.agent = self.info.default_agent

    def update_agent(self, agent: str, verify: bool = True) -> None:
        if verify:
            if not self.info:
                self.retrieve_info()
            agent_keys = [agent_info.key for agent_info in self.info.agents]  # type: ignore[union-attr]
            if agent not in agent_keys:
                raise AgentClientError(
                    f"Agent {agent} not found in available agents: {', '.join(agent_keys)}"
                )
        self.agent = agent

    def _request_payload(
        self,
        message: str,
        *,
        model: Any | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool | None = None,
    ) -> UserInput | StreamInput:
        payload: UserInput | StreamInput
        if stream_tokens is None:
            payload = UserInput(message=message)
        else:
            payload = StreamInput(message=message, stream_tokens=stream_tokens)
        if thread_id:
            payload.thread_id = thread_id
        if user_id:
            payload.user_id = user_id
        if model:
            payload.model = model
        if agent_config:
            payload.agent_config = agent_config
        return payload

    def _agent_path(self, suffix: str) -> str:
        if not self.agent:
            raise AgentClientError("No agent selected. Use update_agent() to select an agent.")
        return f"{self.base_url}/{self.agent}/{suffix}"

    async def ainvoke(
        self,
        message: str,
        model: Any | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        request = self._request_payload(
            message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config,
        )
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    self._agent_path("invoke"),
                    json=request.model_dump(),
                    headers=self._headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise AgentClientError(f"Error: {exc}") from exc
        return ChatMessage.model_validate(response.json())

    def invoke(
        self,
        message: str,
        model: Any | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
    ) -> ChatMessage:
        request = self._request_payload(
            message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config,
        )
        try:
            response = httpx.post(
                self._agent_path("invoke"),
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentClientError(f"Error: {exc}") from exc
        return ChatMessage.model_validate(response.json())

    def _parse_stream_line(self, line: str) -> ChatMessage | str | None:
        line = line.strip()
        if not line.startswith("data: "):
            return None
        data = line[6:]
        if data == "[DONE]":
            return None
        parsed = json.loads(data)
        match parsed["type"]:
            case "message":
                return ChatMessage.model_validate(parsed["content"])
            case "token":
                return parsed["content"]
            case "error":
                return ChatMessage(type="ai", content="Error: " + str(parsed["content"]))
        return None

    def stream(
        self,
        message: str,
        model: Any | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool = True,
    ) -> Generator[ChatMessage | str, None, None]:
        request = self._request_payload(
            message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config,
            stream_tokens=stream_tokens,
        )
        try:
            with httpx.stream(
                "POST",
                self._agent_path("stream"),
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    parsed = self._parse_stream_line(line)
                    if parsed is None:
                        break
                    yield parsed
        except httpx.HTTPError as exc:
            raise AgentClientError(f"Error: {exc}") from exc

    async def astream(
        self,
        message: str,
        model: Any | None = None,
        thread_id: str | None = None,
        user_id: str | None = None,
        agent_config: dict[str, Any] | None = None,
        stream_tokens: bool = True,
    ) -> AsyncGenerator[ChatMessage | str, None]:
        request = self._request_payload(
            message,
            model=model,
            thread_id=thread_id,
            user_id=user_id,
            agent_config=agent_config,
            stream_tokens=stream_tokens,
        )
        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    self._agent_path("stream"),
                    json=request.model_dump(),
                    headers=self._headers,
                    timeout=self.timeout,
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        parsed = self._parse_stream_line(line)
                        if parsed is None:
                            break
                        if parsed != "":
                            yield parsed
            except httpx.HTTPError as exc:
                raise AgentClientError(f"Error: {exc}") from exc

    def get_history(self, thread_id: str) -> ChatHistory:
        request = ChatHistoryInput(thread_id=thread_id)
        try:
            response = httpx.post(
                f"{self.base_url}/history",
                json=request.model_dump(),
                headers=self._headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise AgentClientError(f"Error: {exc}") from exc
        return ChatHistory.model_validate(response.json())
