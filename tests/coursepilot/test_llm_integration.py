import json
import os

import pytest
from pydantic import SecretStr

from core.settings import settings
from coursepilot.llm import (
    collect_coursepilot_llm_metadata,
    generate_structured,
    get_coursepilot_llm,
)
from coursepilot.rag.knowledge_points import KnowledgePointList


def _configured_for_real_llm() -> bool:
    return bool(
        os.getenv("COURSEPILOT_RUN_LLM_INTEGRATION") == "1"
        and (os.getenv("COMPATIBLE_BASE_URL") or settings.COMPATIBLE_BASE_URL)
        and (os.getenv("COMPATIBLE_MODEL") or settings.COMPATIBLE_MODEL)
        and (os.getenv("COMPATIBLE_API_KEY") or settings.COMPATIBLE_API_KEY)
    )


@pytest.mark.llm_integration
@pytest.mark.skipif(
    not _configured_for_real_llm(),
    reason="set COURSEPILOT_RUN_LLM_INTEGRATION=1 and COMPATIBLE_* to run",
)
def test_real_coursepilot_llm_structured_output(monkeypatch):
    monkeypatch.setattr(settings, "COURSEPILOT_GENERATION_MODE", "llm")
    if os.getenv("COMPATIBLE_BASE_URL"):
        monkeypatch.setattr(settings, "COMPATIBLE_BASE_URL", os.environ["COMPATIBLE_BASE_URL"])
    if os.getenv("COMPATIBLE_MODEL"):
        monkeypatch.setattr(settings, "COMPATIBLE_MODEL", os.environ["COMPATIBLE_MODEL"])
    if os.getenv("COMPATIBLE_API_KEY"):
        monkeypatch.setattr(
            settings,
            "COMPATIBLE_API_KEY",
            SecretStr(os.environ["COMPATIBLE_API_KEY"]),
        )
    get_coursepilot_llm.cache_clear()

    try:
        with collect_coursepilot_llm_metadata(thread_id="real-llm-integration") as collector:
            result = generate_structured(
                prompt_name="rag/extract_knowledge_points",
                output_schema=KnowledgePointList,
                payload={
                    "content": "状态空间搜索、启发式函数和路径代价是人工智能搜索算法的核心概念。",
                    "max_points": 3,
                },
                fallback=lambda: KnowledgePointList(knowledge_points=[]),
            )
        metadata = collector.to_task_metadata()
        print(json.dumps(metadata["llm_usage_summary"], ensure_ascii=False, indent=2))

        assert result.knowledge_points
        assert metadata["llm_invocations"][0]["fallback_used"] is False
    finally:
        get_coursepilot_llm.cache_clear()
