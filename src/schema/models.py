from enum import StrEnum, auto
from typing import TypeAlias


class Provider(StrEnum):
    OPENAI = auto()
    OPENAI_COMPATIBLE = auto()
    DEEPSEEK = auto()
    FAKE = auto()


class OpenAIModelName(StrEnum):
    """https://platform.openai.com/docs/models/gpt-4o"""

    GPT_5_NANO = "gpt-5-nano"
    GPT_5_MINI = "gpt-5-mini"
    GPT_5_1 = "gpt-5.1"


class DeepseekModelName(StrEnum):
    """https://api-docs.deepseek.com/quick_start/pricing"""

    DEEPSEEK_CHAT = "deepseek-chat"


class OpenAICompatibleName(StrEnum):
    """https://platform.openai.com/docs/guides/text-generation"""

    OPENAI_COMPATIBLE = "openai-compatible"


class FakeModelName(StrEnum):
    """Fake model for testing."""

    FAKE = "fake"


AllModelEnum: TypeAlias = OpenAIModelName | OpenAICompatibleName | DeepseekModelName | FakeModelName
