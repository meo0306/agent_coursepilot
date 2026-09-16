"""Fail-closed local tokenizer abstraction used by versioned Chunk Profiles."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from tokenizers import Tokenizer


class TokenCounter(Protocol):
    @property
    def tokenizer_id(self) -> str: ...

    @property
    def tokenizer_sha256(self) -> str: ...

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]: ...

    def token_ids(self, text: str) -> tuple[int | str, ...]: ...

    def count(self, text: str) -> int:
        return len(self.token_spans(text))


class LocalTokenizer:
    def __init__(
        self,
        path: Path,
        *,
        tokenizer_id: str,
        expected_sha256: str,
    ) -> None:
        resolved = path.resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Chunk tokenizer file not found: {resolved}")
        digest = _sha256_file(resolved)
        if digest != expected_sha256:
            raise ValueError("Chunk tokenizer SHA-256 differs from the frozen Profile")
        self._tokenizer = Tokenizer.from_file(str(resolved))
        self._tokenizer_id = tokenizer_id
        self._tokenizer_sha256 = digest

    @property
    def tokenizer_id(self) -> str:
        return self._tokenizer_id

    @property
    def tokenizer_sha256(self) -> str:
        return self._tokenizer_sha256

    def token_spans(self, text: str) -> tuple[tuple[int, int], ...]:
        if not text:
            return ()
        encoding = self._tokenizer.encode(text, add_special_tokens=False)
        return tuple((start, end) for start, end in encoding.offsets if end > start)

    def token_ids(self, text: str) -> tuple[int | str, ...]:
        return tuple(self._tokenizer.encode(text, add_special_tokens=False).ids)

    def count(self, text: str) -> int:
        return len(self.token_spans(text))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
