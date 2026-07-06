"""
embedding模型设置
"""
import hashlib
import math
import re

from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from core.settings import settings


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
        return OpenAIEmbeddings(
            model=model,
            base_url=base_url,
            api_key=api_key.get_secret_value() if hasattr(api_key, "get_secret_value") else api_key,
        )
    # 默认兜底
    return HashingEmbeddings()
