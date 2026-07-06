"""
CoursePilot 专属 LLM 调用入口
"""
import json
from collections.abc import Callable
from functools import cache
from typing import TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from core.settings import settings
from coursepilot.prompts.loader import load_prompt

T = TypeVar("T", bound=BaseModel)


def use_coursepilot_llm() -> bool:
    """返回是否有可用的 CoursePilot LLM 配置，且当前模式为 LLM 模式"""
    mode = settings.COURSEPILOT_GENERATION_MODE.lower()
    if mode == "deterministic":
        return False
    if mode == "llm":
        _require_compatible_llm_config()
        return True
    # auto mode: use LLM if compatible config is present, otherwise fallback to deterministic
    return _has_compatible_llm_config()


@cache
def get_coursepilot_llm() -> ChatOpenAI:
    """
    获取 CoursePilot LLM 实例
    只创建一次 ChatOpenAI 实例，避免每个节点重复初始化客户端。
    """
    _require_compatible_llm_config()
    api_key = settings.COMPATIBLE_API_KEY
    return ChatOpenAI(
        model=settings.COMPATIBLE_MODEL,
        temperature=0.2,
        streaming=False,    # CoursePilot LLM 不支持流式输出
        base_url=settings.COMPATIBLE_BASE_URL,
        api_key=api_key.get_secret_value() if api_key else None,
    )


def generate_structured(
    *,
    prompt_name: str,
    output_schema: type[T],
    payload: dict,
    fallback: Callable[[], T],
) -> T:
    """
    核心调用：通过 LLM 结构化生成 Pydantic 对象，带有确定性回退。
    """
    # 如果没有可用的 CoursePilot LLM 配置，或者当前模式为确定性模式，则使用回退函数
    if not use_coursepilot_llm():
        return fallback()

    # 输入和模型准备
    # 加载提示词
    prompt = load_prompt(prompt_name)
    # 构造human消息的payload，包含业务输入和输出schema
    human_payload = {
        "input": payload,
        "schema": output_schema.model_json_schema(),
    }
    # 构建可调用的 LLM 实例（可生成结构化输出）
    runnable = get_coursepilot_llm().with_structured_output(output_schema)
    
    # 输入系统消息和human消息，调用LLM生成结构化输出result
    result = runnable.invoke(
        [
            SystemMessage(content=prompt),
            HumanMessage(content=json.dumps(human_payload, ensure_ascii=False, default=str)),
        ]
    )

    # 如果返回结果已经是output_schema类型，则直接返回，否则使用model_validate进行验证和转换
    if isinstance(result, output_schema):
        return result
    return output_schema.model_validate(result)


def _has_compatible_llm_config() -> bool:
    return bool(
        settings.COMPATIBLE_BASE_URL
        and settings.COMPATIBLE_MODEL
        and settings.COMPATIBLE_API_KEY
    )


def _require_compatible_llm_config() -> None:
    if not _has_compatible_llm_config():
        raise ValueError(
            "CoursePilot LLM mode requires COMPATIBLE_BASE_URL, COMPATIBLE_MODEL, "
            "and COMPATIBLE_API_KEY."
        )

