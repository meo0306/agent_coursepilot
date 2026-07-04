"""
本地、确定性的 embedding 实现
不依赖 OpenAI、Qwen 或其他在线 embedding API
"""
import hashlib
import math
import re

from langchain_core.embeddings import Embeddings


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

