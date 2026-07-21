"""
embedding模型设置
"""

import asyncio
import hashlib
import logging
import math
import re
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings
from openai import RateLimitError

from core.settings import settings

logger = logging.getLogger(__name__)
T = TypeVar("T")


class HashingEmbeddings(Embeddings):
    """Deterministic local embeddings for CoursePilot Phase 1 smoke tests and demos."""

    def __init__(self, dimensions: int = 256):
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_]+", text.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


class RateLimitRetryEmbeddings(Embeddings):
    """Retry only provider 429 responses with a bounded long backoff."""

    def __init__(
        self,
        backend: Embeddings,
        *,
        max_retries: int,
        base_delay_seconds: float,
        max_delay_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.backend = backend
        self.max_retries = max_retries
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self._sleep = sleep

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._run_with_retry("embed_documents", lambda: self.backend.embed_documents(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._run_with_retry("embed_query", lambda: self.backend.embed_query(text))

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._run_with_retry_async(
            "aembed_documents",
            lambda: self.backend.aembed_documents(texts),
        )

    async def aembed_query(self, text: str) -> list[float]:
        return await self._run_with_retry_async(
            "aembed_query",
            lambda: self.backend.aembed_query(text),
        )

    def _run_with_retry(self, operation: str, call: Callable[[], T]) -> T:
        for retry_index in range(self.max_retries + 1):
            try:
                return call()
            except RateLimitError as exc:
                if retry_index >= self.max_retries:
                    raise
                delay = self._retry_delay(exc, retry_index)
                self._log_retry(operation, retry_index, delay)
                self._sleep(delay)
        raise RuntimeError("unreachable embedding retry state")

    async def _run_with_retry_async(
        self,
        operation: str,
        call: Callable[[], Awaitable[T]],
    ) -> T:
        for retry_index in range(self.max_retries + 1):
            try:
                return await call()
            except RateLimitError as exc:
                if retry_index >= self.max_retries:
                    raise
                delay = self._retry_delay(exc, retry_index)
                self._log_retry(operation, retry_index, delay)
                await asyncio.sleep(delay)
        raise RuntimeError("unreachable embedding retry state")

    def _retry_delay(self, exc: RateLimitError, retry_index: int) -> float:
        exponential_delay = self.base_delay_seconds * (2**retry_index)
        retry_after = _retry_after_seconds(exc)
        requested_delay = max(exponential_delay, retry_after or 0.0)
        return min(requested_delay, self.max_delay_seconds)

    def _log_retry(self, operation: str, retry_index: int, delay: float) -> None:
        logger.warning(
            "CoursePilot embedding rate limited operation=%s retry=%s/%s delay_seconds=%s",
            operation,
            retry_index + 1,
            self.max_retries,
            delay,
        )


def _retry_after_seconds(exc: RateLimitError) -> float | None:
    value = exc.response.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def get_coursepilot_embeddings() -> Embeddings:
    """获取 CoursePilot 的 embedding 实例"""
    provider = settings.COURSEPILOT_EMBEDDING_PROVIDER.lower()
    # 明确指定 hashing 时，使用本地 deterministic embedding
    if provider == "hashing":
        return HashingEmbeddings()

    # 读取配置中的 base_url、api_key 和 model
    base_url = settings.COURSEPILOT_EMBEDDING_BASE_URL or settings.COMPATIBLE_BASE_URL
    api_key = settings.COURSEPILOT_EMBEDDING_API_KEY or settings.COMPATIBLE_API_KEY
    model = settings.COURSEPILOT_EMBEDDING_MODEL

    if provider == "openai-compatible" or (provider == "auto" and base_url and api_key and model):
        # openai-compatible：强制真实 embedding；
        # auto：只有 base_url/api_key/model 都齐全时才用真实 embedding
        # 如果缺少任何一个配置，则抛出异常
        if not base_url or not api_key or not model:
            raise ValueError(
                "OpenAI-compatible embeddings require COURSEPILOT_EMBEDDING_BASE_URL, "
                "COURSEPILOT_EMBEDDING_API_KEY, and COURSEPILOT_EMBEDDING_MODEL."
            )
        backend = OpenAIEmbeddings(  # type: ignore[call-arg]
            model=model,
            base_url=base_url,
            api_key=api_key.get_secret_value() if hasattr(api_key, "get_secret_value") else api_key,
            max_retries=0,
        )
        return RateLimitRetryEmbeddings(
            backend,
            max_retries=settings.COURSEPILOT_EMBEDDING_MAX_RETRIES,
            base_delay_seconds=settings.COURSEPILOT_EMBEDDING_RETRY_BASE_SECONDS,
            max_delay_seconds=settings.COURSEPILOT_EMBEDDING_RETRY_MAX_SECONDS,
        )
    # 默认兜底
    return HashingEmbeddings()
