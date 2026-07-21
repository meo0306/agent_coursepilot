"""
知识点提取器
"""

import re

from pydantic import BaseModel, Field

from core.settings import settings
from coursepilot.llm import generate_structured


class KnowledgePointList(BaseModel):
    knowledge_points: list[str] = Field(default_factory=list)


class KnowledgePointExtractor:
    def extract(self, content: str, *, max_points: int = 10) -> list[str]:
        """优先 LLM 抽取知识点，未配置模型或测试环境自动走 deterministic fallback"""
        mode = settings.COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE.lower()
        if mode == "deterministic":
            return extract_keywords_deterministic(content, max_points=max_points)
        if mode not in {"auto", "llm"}:
            raise ValueError(
                "COURSEPILOT_RAG_KNOWLEDGE_POINTS_MODE must be one of: auto, llm, deterministic."
            )
        return generate_structured(
            prompt_name="rag/extract_knowledge_points",
            output_schema=KnowledgePointList,
            payload={"content": content[:6000], "max_points": max_points},
            fallback=lambda: KnowledgePointList(
                knowledge_points=extract_keywords_deterministic(content, max_points=max_points)
            ),
        ).knowledge_points[:max_points]


def extract_keywords_deterministic(content: str, *, max_points: int = 10) -> list[str]:
    """使用正则表达式从文本中提取知识点，作为 LLM 抽取的 fallback"""
    candidates = re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_-]{2,20}", content)
    seen: set[str] = set()
    keywords: list[str] = []
    for candidate in candidates:
        normalized = candidate.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keywords.append(normalized)
        if len(keywords) >= max_points:
            break
    return keywords
