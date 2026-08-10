from __future__ import annotations

import re
import unicodedata

import jieba

_PROTECTED = re.compile(r"A\*|[A-Za-z]+(?:\+\+|#)?(?:[-_.][A-Za-z0-9]+)*|\d+(?:\.\d+)*", re.I)
_CJK = re.compile(r"[\u3400-\u9fff]")


def search_tokens(text: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    protected = _PROTECTED.findall(normalized)
    masked = _PROTECTED.sub(" ", normalized)
    tokens = [item.strip() for item in jieba.cut_for_search(masked) if item.strip()]
    return protected + tokens


def character_bigrams(text: str) -> list[str]:
    cjk = "".join(char for char in unicodedata.normalize("NFKC", text) if _CJK.match(char))
    return [cjk[index : index + 2] for index in range(max(0, len(cjk) - 1))]
