"""Token usage estimation helpers for CoursePilot LLM calls."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any

from tokenizers import Tokenizer

from core.settings import settings

USAGE_SOURCE_PROVIDER = "provider"
USAGE_SOURCE_DEEPSEEK_TOKENIZER = "deepseek_v3_tokenizer"
USAGE_SOURCE_UNAVAILABLE = "unavailable"

logger = logging.getLogger(__name__)


def estimate_token_usage(
    input_messages: Iterable[Any],
    output_content: Any | None,
) -> dict[str, Any]:
    """Estimate token usage with the bundled DeepSeek V3 tokenizer."""
    tokenizer = get_deepseek_tokenizer()
    if tokenizer is None:
        return {
            "input_tokens": None,
            "output_tokens": None,
            "total_tokens": None,
            "usage_source": USAGE_SOURCE_UNAVAILABLE,
            "usage_estimated": True,
        }

    input_text = _messages_to_text(input_messages)
    output_text = _content_to_text(output_content)
    input_tokens = len(tokenizer.encode(input_text).ids) if input_text else 0
    output_tokens = len(tokenizer.encode(output_text).ids) if output_text else 0
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
        "usage_source": USAGE_SOURCE_DEEPSEEK_TOKENIZER,
        "usage_estimated": True,
    }


@cache
def get_deepseek_tokenizer() -> Tokenizer | None:
    """Load the configured DeepSeek tokenizer once per process."""
    path = Path(settings.COURSEPILOT_TOKENIZER_PATH).expanduser()
    if not path.exists():
        logger.warning("CoursePilot tokenizer file not found path=%s", path)
        return None
    try:
        return Tokenizer.from_file(str(path))
    except Exception as exc:
        logger.warning("CoursePilot tokenizer load failed path=%s error=%s", path, exc)
        return None


def _messages_to_text(messages: Iterable[Any]) -> str:
    parts: list[str] = []
    for message in messages:
        role = getattr(message, "type", message.__class__.__name__)
        content = _content_to_text(getattr(message, "content", message))
        parts.append(f"{role}: {content}")
    return "\n".join(parts)


def _content_to_text(content: Any | None) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, default=str)
