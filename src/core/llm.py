from functools import cache
from typing import TypeAlias

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_openai import ChatOpenAI

from core.settings import settings
from schema.models import (
    AllModelEnum,
    DeepseekModelName,
    FakeModelName,
    OpenAICompatibleName,
    OpenAIModelName,
)

_MODEL_TABLE = (
    {model: model.value for model in OpenAIModelName}
    | {model: model.value for model in OpenAICompatibleName}
    | {model: model.value for model in DeepseekModelName}
    | {model: model.value for model in FakeModelName}
)


class FakeToolModel(FakeListChatModel):
    def __init__(self, responses: list[str]):
        super().__init__(responses=responses)

    def bind_tools(self, tools, **kwargs):
        return self


ModelT: TypeAlias = ChatOpenAI | FakeToolModel


@cache
def get_model(model_name: AllModelEnum, /) -> ModelT:
    api_model_name = _MODEL_TABLE.get(model_name)
    if not api_model_name:
        raise ValueError(f"Unsupported model: {model_name}")

    if model_name in OpenAIModelName:
        return ChatOpenAI(model=api_model_name, streaming=True)
    if model_name in OpenAICompatibleName:
        if not settings.COMPATIBLE_BASE_URL or not settings.COMPATIBLE_MODEL:
            raise ValueError("OpenAI-compatible base url and model must be configured")
        return ChatOpenAI(
            model=settings.COMPATIBLE_MODEL,
            temperature=0.5,
            streaming=True,
            openai_api_base=settings.COMPATIBLE_BASE_URL,
            openai_api_key=settings.COMPATIBLE_API_KEY,
        )
    if model_name in DeepseekModelName:
        return ChatOpenAI(
            model=api_model_name,
            temperature=0.5,
            streaming=True,
            openai_api_base="https://api.deepseek.com",
            openai_api_key=settings.DEEPSEEK_API_KEY,
        )
    if model_name in FakeModelName:
        return FakeToolModel(responses=["This is a test response from the fake model."])

    raise ValueError(f"Unsupported model: {model_name}")
